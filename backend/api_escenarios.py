
from datetime import date, timedelta
from pathlib import Path
from typing import Literal
import json
import math
from backend.escenarios_diarios import simular_48h_por_dias
import joblib
import numpy as np
import pandas as pd

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from functools import lru_cache
from backend.escenarios_diarios import simular_48h_por_dias

from backend.optimizador import (
    optimizar_recargas,
    CAPACIDAD_BATERIA_KWH,
    SOC_MINIMO,
    SOC_OBJETIVO,
    NUM_CARGADORES,
)

from backend.prediccion_48h import (
    FEATURES,
    TZ,
    build_calendar_features,
    determine_calendar_zone,
)


router = APIRouter(
    prefix="/api/escenarios",
    tags=["Escenarios"],
)

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
MODELS = ROOT / "models"


CATALOGO = {
    "baseline": (
        "Baseline semanal",
        None,
    ),
    "hgb": (
        "HistGradientBoosting",
        "modelo_precio_hgb.joblib",
    ),
    "ridge": (
        "Ridge Regression",
        "modelo_precio_ridge.joblib",
    ),
    "rf": (
        "Random Forest",
        "modelo_precio_rf.joblib",
    ),
    "xgb": (
        "XGBoost",
        "modelo_precio_xgb.joblib",
    ),
}


class SolicitudEscenario(BaseModel):
    fecha_consulta: date

    modelo: Literal[
        "baseline",
        "hgb",
        "ridge",
        "rf",
        "xgb",
    ] = "hgb"

    cambio_demanda_pct: int = Field(
        default=0,
        ge=-30,
        le=50,
    )

    dia_demanda: Literal[
        "ambos",
        "primero",
        "segundo",
    ] = "ambos"



def tabla(ruta: Path, columnas: set[str]):
    if not ruta.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"No existe {ruta.name}",
        )

    try:
        datos = pd.read_parquet(ruta)
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail=f"No se pudo leer {ruta.name}: {error}",
        )

    if datos.empty or not columnas.issubset(datos.columns):
        raise HTTPException(
            status_code=422,
            detail=f"Datos incompletos en {ruta.name}",
        )

    if datos[list(columnas)].isna().any().any():
        raise HTTPException(
            status_code=422,
            detail=f"Hay valores nulos en {ruta.name}",
        )

    datos["datetime_utc"] = pd.to_datetime(
        datos["datetime_utc"],
        utc=True,
        errors="raise",
    )

    return datos



def horas_esperadas(fecha: date):
    inicio = pd.Timestamp(
        fecha + timedelta(days=1),
        tz=TZ,
    )

    fin = pd.Timestamp(
        fecha + timedelta(days=3),
        tz=TZ,
    )

    return pd.date_range(
        inicio.tz_convert("UTC"),
        fin.tz_convert("UTC"),
        freq="h",
        inclusive="left",
    )


def verificar_horas(datos, horas, etiqueta):
    if len(datos) != len(horas):
        raise HTTPException(
            status_code=422,
            detail=f"Cobertura horaria incorrecta: {etiqueta}",
        )

    if datos["datetime_utc"].duplicated().any():
        raise HTTPException(
            status_code=422,
            detail=f"Horas duplicadas: {etiqueta}",
        )

    if set(datos["datetime_utc"]) != set(horas):
        raise HTTPException(
            status_code=422,
            detail=f"El horizonte no coincide: {etiqueta}",
        )


def cargar_precios(modelo: str, predicciones, horas):
    predicciones = (
        predicciones
        .set_index("datetime_utc")
        .reindex(horas)
    )

    if modelo == "baseline":
        pronostico = predicciones[
            "precio_baseline_eur_mwh"
        ].to_numpy(dtype=float)

    elif modelo == "hgb":
        pronostico = predicciones[
            "precio_predicho_eur_mwh"
        ].to_numpy(dtype=float)

    else:
        ruta = MODELS / CATALOGO[modelo][1]

        if not ruta.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"No existe el modelo {modelo}",
            )

        modelo_entrenado = joblib.load(ruta)

        variables = list(
            getattr(
                modelo_entrenado,
                "feature_names_in_",
                [],
            )
        )

        if variables != FEATURES:
            raise HTTPException(
                status_code=422,
                detail=f"Variables incompatibles en {modelo}",
            )

        observaciones = tabla(
            PROCESSED / "omie_precios_actualizados.parquet",
            {
                "datetime_utc",
                "price_eur_mwh",
            },
        ).sort_values("datetime_utc")

        if observaciones["datetime_utc"].duplicated().any():
            raise HTTPException(
                status_code=422,
                detail="Horas duplicadas en OMIE",
            )

        serie = (
            observaciones.loc[
                observaciones["datetime_utc"] < horas[0]
            ]
            .set_index("datetime_utc")["price_eur_mwh"]
        )

        zona = determine_calendar_zone(
            PROCESSED / "omie_ml_hourly.parquet"
        )

        entrada = build_calendar_features(
            horas,
            zona,
        )

        for retardo in (72, 168):
            fechas_retardo = (
                horas - pd.Timedelta(hours=retardo)
            )

            valores = serie.reindex(
                fechas_retardo
            )

            if valores.isna().any():
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Faltan precios históricos OMIE "
                        f"para el retardo de {retardo} horas"
                    ),
                )

            entrada[
                f"price_lag_{retardo}h"
            ] = valores.to_numpy(dtype=float)

        pronostico = np.asarray(
            modelo_entrenado.predict(
                entrada[FEATURES]
            ),
            dtype=float,
        )

    if (
        len(pronostico) != len(horas)
        or not np.isfinite(pronostico).all()
    ):
        raise HTTPException(
            status_code=422,
            detail="La predicción contiene valores no válidos",
        )

    return pronostico



def baterias_inicio(fecha: date, vehiculos: list[str]):
    
    # Recupera los estados iniciales de los vehiculos.

    from backend.optimizador import EFICIENCIA_CARGA

    inicio = (
        fecha + timedelta(days=1)
    ).isoformat()

    ruta = PROCESSED / (
        f"estado_baterias_{inicio}.json"
    )

    minimo = CAPACIDAD_BATERIA_KWH * SOC_MINIMO
    maximo = CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO

    # CASO 1: EXISTE EL JSON DE CONTINUIDAD

    if ruta.is_file():

        try:
            estado = json.loads(
                ruta.read_text(encoding="utf-8")
            )

        except (OSError, json.JSONDecodeError):
            raise HTTPException(
                status_code=422,
                detail="No se puede leer el estado de baterias",
            )

        fecha_origen = (
            fecha - timedelta(days=1)
        ).isoformat()

        if (
            estado.get("fecha_inicio_siguiente_plan") != inicio
            or estado.get("fecha_plan_origen") != fecha_origen
            or estado.get("tipo_estado") != "estimado_por_simulacion"
        ):
            raise HTTPException(
                status_code=422,
                detail="La continuidad de baterias no coincide",
            )

        valores = estado.get(
            "energia_inicial_vehiculos"
        )

    # CASO 2: FALTA EL JSON
    # Reconstruir a partir del plan oficial guardado.

    else:

        ruta_plan = PROCESSED / (
            f"planificacion_ml_48h_{fecha.isoformat()}.parquet"
        )

        if not ruta_plan.is_file():
            raise HTTPException(
                status_code=404,
                detail=(
                    "No existe el estado inicial ni el "
                    f"plan de referencia {ruta_plan.name}"
                ),
            )

        plan = pd.read_parquet(ruta_plan)

        columnas = {
            "datetime_utc",
            "vehicle_id",
            "energia_bateria_kwh",
            "energia_consumida_kwh",
            "recarga_red_kwh",
        }

        if not columnas.issubset(plan.columns):
            raise HTTPException(
                status_code=422,
                detail="Faltan columnas de bateria en el plan",
            )

        plan["datetime_utc"] = pd.to_datetime(
            plan["datetime_utc"],
            utc=True,
            errors="coerce",
        )

        plan["vehicle_id"] = (
            plan["vehicle_id"].astype(str)
        )

        hora_inicio = pd.Timestamp(
            fecha + timedelta(days=1),
            tz="Europe/Madrid",
        ).tz_convert("UTC")

        primeras = plan.loc[
            plan["datetime_utc"] == hora_inicio
        ].copy()

        if (
            len(primeras) != len(vehiculos)
            or primeras["vehicle_id"].duplicated().any()
            or set(primeras["vehicle_id"]) != set(vehiculos)
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "El plan no contiene estados "
                    "iniciales completos"
                ),
            )

        valores = {}

        for fila in primeras.itertuples(index=False):

            try:
                energia_final = float(
                    fila.energia_bateria_kwh
                )

                consumo = float(
                    fila.energia_consumida_kwh
                )

                recarga = float(
                    fila.recarga_red_kwh
                )

                # Balance de la primera hora:
                # final = inicial - consumo
                #         + recarga * eficiencia

                energia_inicial = (
                    energia_final
                    + consumo
                    - recarga * EFICIENCIA_CARGA
                )

            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Datos energeticos invalidos "
                        f"para {fila.vehicle_id}"
                    ),
                )

            if (
                not math.isfinite(energia_inicial)
                or not math.isfinite(energia_final)
                or not math.isfinite(consumo)
                or not math.isfinite(recarga)
                or consumo < 0
                or recarga < -0.002
            ):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Balance energetico invalido "
                        f"para {fila.vehicle_id}"
                    ),
                )

            valores[fila.vehicle_id] = energia_inicial

    # VALIDAR LOS 50 ESTADOS RECUPERADOS

    if (
        not isinstance(valores, dict)
        or set(valores) != set(vehiculos)
    ):
        raise HTTPException(
            status_code=422,
            detail="Los estados iniciales estan incompletos",
        )

    energias = {}

    for vehiculo in vehiculos:

        try:
            energia = float(
                valores[vehiculo]
            )

        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Bateria inicial no valida para "
                    f"{vehiculo}"
                ),
            )

        if (
            not math.isfinite(energia)
            or energia < minimo - 0.002
            or energia > maximo + 0.002
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Bateria inicial fuera de limites: "
                    f"{vehiculo}"
                ),
            )

        energias[vehiculo] = min(
            max(energia, minimo),
            maximo,
        )

    return energias



def calendario_operativo(plan, horas, vehiculos):
    cargadores = [
        f"C{i:02d}"
        for i in range(1, NUM_CARGADORES + 1)
    ]

    entradas = []
    previos = {}
    fecha_actual = None

    for hora in horas:
        fecha_de_hora = hora.tz_convert(TZ).date()

        if fecha_de_hora != fecha_actual:
            previos = {}
            fecha_actual = fecha_de_hora

        grupo = (
            plan.loc[
                plan["datetime_utc"] == hora
            ]
            .sort_values("vehicle_id")
        )

        activos = grupo.loc[
            grupo["recarga_red_kwh"] > 0.001,
            "vehicle_id",
        ].tolist()

        asignados = {}
        ocupados = set()

        # Mantener el cargador anterior cuando sea posible.

        for vehiculo in activos:
            anterior = previos.get(
                vehiculo
            )

            if (
                anterior is not None
                and anterior not in ocupados
            ):
                asignados[vehiculo] = anterior
                ocupados.add(anterior)

        libres = iter(
            cargador
            for cargador in cargadores
            if cargador not in ocupados
        )

        for vehiculo in activos:
            if vehiculo not in asignados:
                try:
                    asignados[vehiculo] = next(
                        libres
                    )

                except StopIteration:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "Hay más vehículos cargando "
                            "que cargadores disponibles"
                        ),
                    )

        for fila in grupo.itertuples(index=False):
            recargando = (
                float(fila.recarga_red_kwh) > 0.001
            )

            trabajando = not bool(
                fila.disponible_carga
            )

            if recargando:
                estado = "cargando"

            elif trabajando:
                estado = "trabajando"

            else:
                estado = "disponible"

            entradas.append({
                "vehicle_id": str(fila.vehicle_id),
                "fecha_local": (
                    hora.tz_convert(TZ).isoformat()
                ),
                "estado": estado,
                "cargador_id": asignados.get(
                    fila.vehicle_id
                ),
                "energia_red_kwh": round(
                    float(fila.recarga_red_kwh),
                    3,
                ),
                "energia_consumida_kwh": round(
                    float(fila.energia_consumida_kwh),
                    3,
                ),
                "soc_pct": round(
                    float(fila.soc_pct),
                    3,
                ),
            })

        previos = asignados

    if len(entradas) != len(horas) * len(vehiculos):
        raise HTTPException(
            status_code=422,
            detail="El calendario está incompleto",
        )

    return entradas, cargadores


# -----------------------------------------
# LIMITE AUTOMATICO DE DEMANDA VIABLE
# -----------------------------------------

MAXIMO_DEMANDA_ANALIZADO = 50


@lru_cache(maxsize=128)
def calcular_limite_ventana(
    fecha: date,
    modelo: str,
    dia_demanda: str,
) -> int:
    """
    Busca el mayor incremento porcentual entero
    que consigue resolver el simulador.

    Guarda en cache los resultados por fecha,
    modelo y dia seleccionado.
    """

    ruta_plan = PROCESSED / (
        f"planificacion_ml_48h_{fecha.isoformat()}.parquet"
    )

    if not ruta_plan.is_file():
        raise ValueError(
            f"No existe el plan {ruta_plan.name}"
        )

    vehiculos = sorted(
        pd.read_parquet(
            ruta_plan,
            columns=["vehicle_id"],
        )["vehicle_id"]
        .astype(str)
        .unique()
        .tolist()
    )

    if len(vehiculos) != 50:
        raise ValueError(
            "El plan no contiene los 50 vehiculos"
        )

    def es_viable(porcentaje: int) -> bool:

        try:
            resultado, _, _ = simular_48h_por_dias(
                fecha_consulta=fecha,
                vehiculos=vehiculos,
                modelo=modelo,
                cambio_demanda_pct=porcentaje,
                dia_demanda=dia_demanda,
                resolver_precios=cargar_precios,
            )

            return bool(
                resultado["factibilidad_validada"]
            )

        except RuntimeError as error:
            mensaje = str(error).lower()

            # Solo interpretar como falta de capacidad
            # una inviabilidad confirmada por CBC.
            # Otros problemas deben seguir siendo errores
            # tecnicos y no ocultarse como falta de carga.

            if "cbc: infeasible" in mensaje:
                return False

            raise

    # Comprobar escenario original.

    if not es_viable(0):
        raise RuntimeError(
            "El escenario base no es viable"
        )

    # Si el extremo superior es viable,
    # podemos ofrecer todo el rango.

    if es_viable(MAXIMO_DEMANDA_ANALIZADO):
        return MAXIMO_DEMANDA_ANALIZADO

    # Buscar mediante biseccion entre 0 y 50.
    # Los consumos aumentan de forma uniforme.

    inferior = 0
    superior = MAXIMO_DEMANDA_ANALIZADO

    while superior - inferior > 1:

        medio = (inferior + superior) // 2

        if es_viable(medio):
            inferior = medio
        else:
            superior = medio

    return inferior


def calcular_limite_comparable(
    fecha: date,
    modelo: str,
    dia_demanda: str,
) -> int:
    """
    Para un solo dia, respeta tambien el limite
    de la otra ventana donde aparece esa fecha.
    """

    maximo = calcular_limite_ventana(
        fecha, modelo, dia_demanda
    )

    if dia_demanda == "primero":

        fecha_otra = fecha - timedelta(days=1)
        modo_otro = "segundo"

    elif dia_demanda == "segundo":

        fecha_otra = fecha + timedelta(days=1)
        modo_otro = "primero"

    else:
        return maximo

    ruta_otra = PROCESSED / (
        f"planificacion_ml_48h_"
        f"{fecha_otra.isoformat()}.parquet"
    )

    if ruta_otra.is_file():
        maximo = min(
            maximo,
            calcular_limite_ventana(
                fecha_otra,
                modelo,
                modo_otro,
            ),
        )

    return maximo


@router.get("/limite-demanda")
def limite_demanda(
    fecha_consulta: date,
    modelo: Literal[
        "baseline", "hgb", "ridge", "rf", "xgb"
    ] = "hgb",
    dia_demanda: Literal[
        "ambos", "primero", "segundo"
    ] = "ambos",
):
    maximo = calcular_limite_comparable(
        fecha_consulta,
        modelo,
        dia_demanda,
    )

    return {
        "fecha_consulta": fecha_consulta.isoformat(),
        "modelo": modelo,
        "dia_demanda": dia_demanda,
        "minimo_pct": -30,
        "maximo_pct": maximo,
    }


@router.get("/modelos")
def modelos_disponibles():
    modelos = []

    for clave, (nombre, archivo) in CATALOGO.items():
        disponible = (
            archivo is None
            or (MODELS / archivo).is_file()
        )

        modelos.append({
            "id": clave,
            "nombre": nombre,
            "disponible": disponible,
        })

    return {
        "modelos": modelos,
        "nota": (
            "La disponibilidad indica que el archivo "
            "del modelo existe, no que sea más preciso."
        ),
    }


@router.post("/simular")
def simular(solicitud: SolicitudEscenario):
    fecha = solicitud.fecha_consulta
    fecha_texto = fecha.isoformat()


    horas = horas_esperadas(fecha)

    # -----------------------------------------
    # 1. CARGAR PREDICCIONES Y OPERACIONES
    # -----------------------------------------

    predicciones = tabla(
        PROCESSED / (
            f"prediccion_ml_48h_emitida_{fecha_texto}.parquet"
        ),
        {
            "datetime_utc",
            "precio_predicho_eur_mwh",
            "precio_baseline_eur_mwh",
        },
    )

    verificar_horas(
        predicciones,
        horas,
        "precios",
    )

    operaciones = tabla(
        PROCESSED / (
            f"prevision_operaciones_48h_emitida_{fecha_texto}.parquet"
        ),
        {
            "datetime_utc",
            "vehicle_id",
            "disponible_carga",
            "energia_consumida_kwh",
        },
    )

    vehiculos = sorted(
        operaciones["vehicle_id"]
        .astype(str)
        .unique()
        .tolist()
    )

    if (
        len(vehiculos) != 50
        or len(operaciones) != len(vehiculos) * len(horas)
    ):
        raise HTTPException(
            status_code=422,
            detail="La matriz operativa está incompleta",
        )

    if operaciones.duplicated(
        ["vehicle_id", "datetime_utc"]
    ).any():
        raise HTTPException(
            status_code=422,
            detail="Existen operaciones duplicadas",
        )

    if set(operaciones["datetime_utc"]) != set(horas):
        raise HTTPException(
            status_code=422,
            detail="El horizonte operativo no coincide",
        )

    cobertura = operaciones.groupby(
        "vehicle_id"
    )["datetime_utc"].nunique()

    if (cobertura != len(horas)).any():
        raise HTTPException(
            status_code=422,
            detail="Faltan horas de operaciones",
        )

    if not pd.api.types.is_bool_dtype(
        operaciones["disponible_carga"]
    ):
        raise HTTPException(
            status_code=422,
            detail="La disponibilidad debe ser booleana",
        )

    consumos = operaciones[
        "energia_consumida_kwh"
    ].to_numpy(dtype=float)

    if (
        not np.isfinite(consumos).all()
        or (consumos < 0).any()
    ):
        raise HTTPException(
            status_code=422,
            detail="Hay consumos negativos o no válidos",
        )

  
    # -----------------------------------------
    # 2-4. ESCENARIOS CON REFERENCIA DIARIA
    # -----------------------------------------

    try:
        resultado, datos_opt, precios_opt = (
            simular_48h_por_dias(
                fecha_consulta=fecha,
                vehiculos=vehiculos,
                modelo=solicitud.modelo,
                cambio_demanda_pct=(
                    solicitud.cambio_demanda_pct
                ),
                dia_demanda=solicitud.dia_demanda,
                resolver_precios=cargar_precios,
            )
        )

    except (ValueError, RuntimeError) as error:
        raise HTTPException(
            status_code=422,
            detail=(
                "Escenario inconsistente o inviable: "
                f"{error}"
            ),
        )

    if not resultado.get("factibilidad_validada"):
        raise HTTPException(
            status_code=422,
            detail=(
                "El escenario no tiene una "
                "solucion validada"
            ),
        )

    precios_predichos = (
        precios_opt.set_index("hora")["price_eur_mwh"]
        .reindex(horas)
        .to_numpy(dtype=float)
    )

    primer_dia = fecha + timedelta(days=1)
    segundo_dia = fecha + timedelta(days=2)

    horas_primer_dia = sum(
        hora.tz_convert(TZ).date() == primer_dia
        for hora in horas
    )
    # -----------------------------------------
    # 5. PREPARAR PLAN DE VEHICULOS
    # -----------------------------------------

    plan = resultado["recargas"].copy()

    plan["datetime_utc"] = pd.to_datetime(
        plan["hora"],
        utc=True,
    )

    plan = plan.drop(
        columns=["hora"]
    )

    plan = plan.merge(
        datos_opt.rename(
            columns={"hora": "datetime_utc"}
        ),
        on=[
            "vehicle_id",
            "datetime_utc",
        ],
        how="left",
        validate="one_to_one",
    )

    plan["recargando"] = (
        plan["recarga_red_kwh"] > 0.001
    ).astype(int)

    if plan.duplicated(
        ["vehicle_id", "datetime_utc"]
    ).any():
        raise HTTPException(
            status_code=422,
            detail=(
                "El optimizador devolvió "
                "filas duplicadas"
            ),
        )

    if plan[
        [
            "energia_consumida_kwh",
            "disponible_carga",
        ]
    ].isna().any().any():
        raise HTTPException(
            status_code=422,
            detail=(
                "La solución no cubre "
                "todas las operaciones"
            ),
        )

    if len(plan) != 50 * len(horas):
        raise HTTPException(
            status_code=422,
            detail="El plan está incompleto",
        )

    # -----------------------------------------
    # 6. RESUMEN HORARIO DE LA FLOTA
    # -----------------------------------------

    flota = (
        plan.groupby(
            "datetime_utc",
            as_index=False,
        )
        .agg(
            energia_red_kwh=(
                "recarga_red_kwh",
                "sum",
            ),
            coste_estimado_eur=(
                "coste_estimado_eur",
                "sum",
            ),
            cargadores_ocupados=(
                "recargando",
                "sum",
            ),
            soc_medio_pct=(
                "soc_pct",
                "mean",
            ),
            soc_minimo_pct=(
                "soc_pct",
                "min",
            ),
        )
        .sort_values("datetime_utc")
    )

    if (
        len(flota) != len(horas)
        or set(flota["datetime_utc"]) != set(horas)
    ):
        raise HTTPException(
            status_code=422,
            detail="Resumen horario incompleto",
        )

    # -----------------------------------------
    # 7. CONTINUIDAD INTERMEDIA DE BATERIAS
    # -----------------------------------------

    ultima_hora_primer_dia = (
        horas[horas_primer_dia - 1]
    )

    baterias_intermedias = plan.loc[
        plan["datetime_utc"]
        == ultima_hora_primer_dia
    ]

    # -----------------------------------------
    # 8. CALENDARIO DE CARGADORES Y VEHICULOS
    # -----------------------------------------

    calendario, cargadores = calendario_operativo(
        plan,
        horas,
        vehiculos,
    )

    dias = [
        primer_dia.isoformat(),
        segundo_dia.isoformat(),
    ]

    # -----------------------------------------
    # 9. PREPARAR RESPUESTA PARA EL DASHBOARD
    # -----------------------------------------

    resumen = {
        "fecha_consulta": fecha_texto,
        "inicio": (
            horas[0]
            .tz_convert(TZ)
            .isoformat()
        ),
        "fin_exclusivo": (
            (horas[-1] + pd.Timedelta(hours=1))
            .tz_convert(TZ)
            .isoformat()
        ),
        "vehiculos": len(vehiculos),
        "horas": len(horas),
        "coste_estimado_eur": round(
            float(
                flota["coste_estimado_eur"].sum()
            ),
            2,
        ),
        "energia_red_kwh": round(
            float(
                flota["energia_red_kwh"].sum()
            ),
            3,
        ),
        "estado_solver": str(
            resultado["estado"]
        ),
        "factibilidad_validada": True,
        "optimalidad_certificada": bool(
            resultado["optimalidad_certificada"]
        ),
        "continuidad": {
            "fecha": dias[1],
            "soc_medio_pct": round(
                float(
                    baterias_intermedias[
                        "soc_pct"
                    ].mean()
                ),
                2,
            ),
            "soc_minimo_pct": round(
                float(
                    baterias_intermedias[
                        "soc_pct"
                    ].min()
                ),
                2,
            ),
        },
    }

    precios_api = [
        {
            "fecha_local": (
                hora.tz_convert(TZ).isoformat()
            ),
            "precio_predicho_eur_mwh": round(
                float(precio),
                4,
            ),
        }
        for hora, precio in zip(
            horas,
            precios_predichos,
        )
    ]

    flota_api = []

    for fila in flota.itertuples(index=False):
        flota_api.append({
            "fecha_local": (
                pd.Timestamp(
                    fila.datetime_utc
                )
                .tz_convert(TZ)
                .isoformat()
            ),
            "energia_red_kwh": round(
                float(fila.energia_red_kwh),
                3,
            ),
            "coste_estimado_eur": round(
                float(fila.coste_estimado_eur),
                4,
            ),
            "cargadores_ocupados": int(
                fila.cargadores_ocupados
            ),
            "soc_medio_pct": round(
                float(fila.soc_medio_pct),
                2,
            ),
            "soc_minimo_pct": round(
                float(fila.soc_minimo_pct),
                2,
            ),
        })

    return {
        "modelo": solicitud.modelo,
        "nombre_modelo": CATALOGO[
            solicitud.modelo
        ][0],
        "cambio_demanda_pct": (
            solicitud.cambio_demanda_pct
        ),
        "dia_demanda": solicitud.dia_demanda,
        "tipo_datos": (
            "escenario_simulado_no_persistido"
        ),
        "resumen": resumen,
        "precios": {
            "registros": precios_api,
        },
        "flota": {
            "registros": flota_api,
        },
        "calendario": {
            "dias": dias,
            "vehiculos": vehiculos,
            "cargadores": cargadores,
            "registros": calendario,
            "advertencia": (
                "Plan simulado. El cambio de demanda "
                "modifica el consumo energético, "
                "pero no los turnos. Las asignaciones "
                "C01-C20 son virtuales. Los precios "
                "OMIE no representan la factura final."
            ),
        },
            "preparacion_anticipada": resultado.get(
        "preparacion_anticipada"
        ),
    }

    # Impedir solicitar demanda superior al limite
    # verificado para esta fecha y escenario.

    if solicitud.cambio_demanda_pct > 0:

        maximo_viable = calcular_limite_comparable(
            solicitud.fecha_consulta,
            solicitud.modelo,
            solicitud.dia_demanda,
        )

        if solicitud.cambio_demanda_pct > maximo_viable:
            solicitud = solicitud.model_copy(
                update={
                    "cambio_demanda_pct": maximo_viable
                }
            )
