
from datetime import date, timedelta
from pathlib import Path
from typing import Literal
import json
import math

import joblib
import numpy as np
import pandas as pd

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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

    if datos.empty:
        raise HTTPException(
            status_code=422,
            detail=f"El archivo está vacío: {ruta.name}",
        )

    if not columnas.issubset(datos.columns):
        raise HTTPException(
            status_code=422,
            detail=f"Faltan columnas en {ruta.name}",
        )

    if datos[list(columnas)].isna().any().any():
        raise HTTPException(
            status_code=422,
            detail=f"Hay valores nulos en {ruta.name}",
        )

    try:
        datos["datetime_utc"] = pd.to_datetime(
            datos["datetime_utc"],
            utc=True,
            errors="raise",
        )

    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail=f"Fechas inválidas en {ruta.name}: {error}",
        )

    if datos["datetime_utc"].isna().any():
        raise HTTPException(
            status_code=422,
            detail=f"Fechas vacías en {ruta.name}",
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
    inicio = (
        fecha + timedelta(days=1)
    ).isoformat()

    ruta = PROCESSED / (
        f"estado_baterias_{inicio}.json"
    )

    if not ruta.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"No existe el estado inicial {ruta.name}",
        )

    try:
        estado = json.loads(
            ruta.read_text(encoding="utf-8")
        )

    except (OSError, json.JSONDecodeError):
        raise HTTPException(
            status_code=422,
            detail="No se puede leer el estado de baterías",
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
            detail="La continuidad de baterías no coincide",
        )

    valores = estado.get(
        "energia_inicial_vehiculos"
    )

    if (
        not isinstance(valores, dict)
        or set(valores) != set(vehiculos)
    ):
        raise HTTPException(
            status_code=422,
            detail="Los estados iniciales están incompletos",
        )

    minimo = (
        CAPACIDAD_BATERIA_KWH * SOC_MINIMO
    )

    maximo = (
        CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO
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
                    "Batería inicial no válida para "
                    f"{vehiculo}"
                ),
            )

        if (
            not math.isfinite(energia)
            or not minimo <= energia <= maximo
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Batería inicial fuera de límites: "
                    f"{vehiculo}"
                ),
            )

        energias[vehiculo] = energia

    return energias


def calendario_operativo(plan, horas, vehiculos):
    cargadores = [
        f"C{i:02d}"
        for i in range(1, NUM_CARGADORES + 1)
    ]

    entradas = []
    previos = {}

    for hora in horas:
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
    # 2. SELECCIONAR MODELO DE PRECIOS
    # -----------------------------------------

    precios_predichos = cargar_precios(
        solicitud.modelo,
        predicciones,
        horas,
    )

    precios_opt = pd.DataFrame({
        "hora": horas,
        "price_eur_mwh": precios_predichos,
    })

    # -----------------------------------------
    # 3. SIMULAR EL CAMBIO DE DEMANDA
    # -----------------------------------------

    datos_opt = operaciones[
        [
            "vehicle_id",
            "datetime_utc",
            "disponible_carga",
            "energia_consumida_kwh",
        ]
    ].copy()

    primer_dia = (
        fecha + timedelta(days=1)
    )

    segundo_dia = (
        fecha + timedelta(days=2)
    )

    fechas_locales = (
        datos_opt["datetime_utc"]
        .dt.tz_convert(TZ)
        .dt.date
    )

    if solicitud.dia_demanda == "primero":
        filtro = (
            fechas_locales == primer_dia
        )

    elif solicitud.dia_demanda == "segundo":
        filtro = (
            fechas_locales == segundo_dia
        )

    else:
        filtro = pd.Series(
            True,
            index=datos_opt.index,
        )

    factor_demanda = (
        1 + solicitud.cambio_demanda_pct / 100
    )

    datos_opt.loc[
        filtro,
        "energia_consumida_kwh",
    ] *= factor_demanda

    datos_opt = datos_opt.rename(
        columns={
            "datetime_utc": "hora"
        }
    )

    # -----------------------------------------
    # 4. ESTADOS INICIALES Y OPTIMIZACION
    # -----------------------------------------

    energia_inicial = baterias_inicio(
        fecha,
        vehiculos,
    )

    objetivos = {
        vehiculo: (
            CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO
        )
        for vehiculo in vehiculos
    }

    horas_primer_dia = sum(
        hora.tz_convert(TZ).date() == primer_dia
        for hora in horas
    )

    try:
        resultado = optimizar_recargas(
            datos_operativos=datos_opt,
            precios_horarios=precios_opt,
            energia_final_objetivo=objetivos,
            energia_inicial_vehiculos=energia_inicial,
            tiempo_maximo_segundos=180,
            objetivo_final_flexible=True,
            penalizacion_deficit_eur_kwh=1.0,
            indice_fin_primer_dia=horas_primer_dia,
            soc_objetivo_intermedio=0.4,
            penalizacion_intermedia_eur_kwh=2.0,
        )

    except (ValueError, RuntimeError) as error:
        raise HTTPException(
            status_code=422,
            detail=f"No se pudo optimizar: {error}",
        )

    if not resultado.get(
        "factibilidad_validada"
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "El escenario no tiene una "
                "solución validada"
            ),
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
    }
