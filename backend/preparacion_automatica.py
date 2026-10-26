from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import math

import pandas as pd
import pulp

from backend.optimizador import (
    CAPACIDAD_BATERIA_KWH,
    SOC_MINIMO,
    SOC_OBJETIVO,
    EFICIENCIA_CARGA,
    POTENCIA_CARGADOR_KW,
    POTENCIA_MAX_INSTALACION_KW,
    NUM_CARGADORES,
    optimizar_recargas,
)


PROCESSED = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "processed"
)

TZ = "Europe/Madrid"

MIN_BATERIA = CAPACIDAD_BATERIA_KWH * SOC_MINIMO
MAX_BATERIA = CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO

MARGEN_SEGURIDAD_KWH = 1.5


# =============================================
# 1. NORMALIZAR LAS OPERACIONES
# =============================================

def _operaciones_normalizadas(
    datos: pd.DataFrame,
) -> pd.DataFrame:

    columnas = {
        "vehicle_id",
        "hora",
        "disponible_carga",
        "energia_consumida_kwh",
    }

    if not columnas.issubset(datos.columns):
        raise ValueError(
            "Faltan columnas operativas: "
            f"{sorted(columnas - set(datos.columns))}"
        )

    df = datos[list(columnas)].copy()

    df["vehicle_id"] = df["vehicle_id"].astype(str)

    df["hora"] = pd.to_datetime(
        df["hora"],
        utc=True,
    )

    df["energia_consumida_kwh"] = pd.to_numeric(
        df["energia_consumida_kwh"],
        errors="coerce",
    )

    if (
        df["energia_consumida_kwh"].isna().any()
        or (df["energia_consumida_kwh"] < 0).any()
        or df["disponible_carga"].isna().any()
        or df.duplicated(["vehicle_id", "hora"]).any()
    ):
        raise ValueError(
            "Operaciones inválidas para el diagnóstico"
        )

    return df.sort_values(
        ["vehicle_id", "hora"]
    )


# =============================================
# 2. COMPROBAR VIABILIDAD INDIVIDUAL
# =============================================

def _viable_individual(
    grupo: pd.DataFrame,
    energia_inicial: float,
) -> bool:

    """
    Simulación optimista.

    Supone que cada vehículo puede cargar a máxima
    potencia en todas sus horas disponibles.

    No sustituye la optimización conjunta.
    """

    energia = float(energia_inicial)

    for fila in grupo.itertuples(index=False):

        consumo = float(
            fila.energia_consumida_kwh
        )

        recarga_max = (
            POTENCIA_CARGADOR_KW * EFICIENCIA_CARGA
            if bool(fila.disponible_carga)
            else 0.0
        )

        energia = min(
            MAX_BATERIA,
            energia - consumo + recarga_max,
        )

        if energia < MIN_BATERIA - 0.001:
            return False

    return True


# =============================================
# 3. DETECTAR BATERIAS QUE NECESITAN PREPARACION
# =============================================

def _necesidades_iniciales(
    operaciones: pd.DataFrame,
    energias: dict[str, float],
) -> dict[str, float]:

    ajustes: dict[str, float] = {}

    for vehiculo, grupo in operaciones.groupby(
        "vehicle_id",
        sort=True,
    ):

        if vehiculo not in energias:
            raise ValueError(
                f"Falta estado inicial de {vehiculo}"
            )

        inicial = float(energias[vehiculo])

        if (
            not math.isfinite(inicial)
            or inicial < MIN_BATERIA - 0.001
            or inicial > MAX_BATERIA + 0.001
        ):
            raise ValueError(
                f"Batería inicial inválida: {vehiculo}"
            )

        # No preparar si el vehículo ya tiene
        # suficiente energía.

        if _viable_individual(grupo, inicial):
            continue

        # Si ni al 80 % puede completar los servicios,
        # no debemos inventar una solución.

        if not _viable_individual(
            grupo,
            MAX_BATERIA,
        ):
            raise RuntimeError(
                f"{vehiculo} no puede cubrir sus servicios "
                "ni comenzando al 80 %. "
                "Es necesario reorganizar operaciones."
            )

        # Búsqueda binaria de la energía necesaria.

        bajo = inicial
        alto = MAX_BATERIA

        for _ in range(22):

            medio = (bajo + alto) / 2

            if _viable_individual(
                grupo,
                medio,
            ):
                alto = medio
            else:
                bajo = medio

        necesario = alto - inicial

        # Margen para que el modelo conjunto pueda
        # encontrar una solución con mayor facilidad.

        extra = math.ceil(
            (
                necesario + MARGEN_SEGURIDAD_KWH
            ) * 4
        ) / 4

        extra = min(
            MAX_BATERIA - inicial,
            extra,
        )

        if extra > 0.001:
            ajustes[vehiculo] = extra

    return ajustes


# =============================================
# 4. CARGAR PLANIFICACION DEL DIA ANTERIOR
# =============================================

def _plan_previo(
    fecha_consulta: date,
    vehiculos: set[str],
) -> pd.DataFrame:

    origen = fecha_consulta - timedelta(days=1)

    ruta = PROCESSED / (
        "planificacion_ml_48h_"
        f"{origen.isoformat()}.parquet"
    )

    if not ruta.is_file():
        raise RuntimeError(
            "No existe el plan previo: "
            f"{ruta.name}"
        )

    plan = pd.read_parquet(ruta)

    necesarias = {
        "datetime_utc",
        "vehicle_id",
        "recarga_red_kwh",
        "energia_bateria_kwh",
        "disponible_carga",
        "conexion",
        "precio_predicho_eur_mwh",
    }

    if not necesarias.issubset(plan.columns):
        raise RuntimeError(
            "Faltan columnas del plan anterior: "
            f"{sorted(necesarias - set(plan.columns))}"
        )

    plan = plan.copy()

    plan["datetime_utc"] = pd.to_datetime(
        plan["datetime_utc"],
        utc=True,
    )

    # Solo queremos el día inmediatamente anterior
    # al comienzo de la nueva planificación.

    plan = plan.loc[
        plan["datetime_utc"]
        .dt.tz_convert(TZ)
        .dt.date == fecha_consulta
    ].copy()

    plan["vehicle_id"] = (
        plan["vehicle_id"].astype(str)
    )

    if plan.duplicated(
        ["vehicle_id", "datetime_utc"]
    ).any():
        raise RuntimeError(
            "El plan previo tiene registros duplicados"
        )

    if set(plan["vehicle_id"]) != vehiculos:
        raise RuntimeError(
            "La flota del plan previo no coincide"
        )

    horas = sorted(
        plan["datetime_utc"].unique()
    )

    if (
        len(horas) != 24
        or len(plan) != len(vehiculos) * 24
    ):
        raise RuntimeError(
            "El plan previo no tiene 24 horas completas"
        )

    columnas_numericas = [
        "recarga_red_kwh",
        "energia_bateria_kwh",
        "conexion",
        "precio_predicho_eur_mwh",
    ]

    for columna in columnas_numericas:

        plan[columna] = pd.to_numeric(
            plan[columna],
            errors="coerce",
        )

        if plan[columna].isna().any():
            raise RuntimeError(
                f"Valores incorrectos en {columna}"
            )

    if plan["disponible_carga"].isna().any():
        raise RuntimeError(
            "Disponibilidad incompleta"
        )

    return plan.sort_values(
        ["datetime_utc", "vehicle_id"]
    ).reset_index(drop=True)


# =============================================
# 5. PROGRAMAR LA PREPARACION ANTICIPADA
# =============================================

def _programar_preparacion(
    fecha_consulta: date,
    energias: dict[str, float],
    ajustes: dict[str, float],
) -> tuple[dict[str, float], dict]:

    plan = _plan_previo(
        fecha_consulta,
        set(energias),
    )

    preparables = sorted(ajustes)

    if not preparables:
        raise RuntimeError(
            "No hay vehículos que preparar"
        )

    horas = sorted(
        plan["datetime_utc"].unique()
    )

    indice = plan.set_index(
        ["vehicle_id", "datetime_utc"]
    )

    # Confirmar continuidad del estado inicial.

    for vehiculo in preparables:

        grupo = plan.loc[
            plan["vehicle_id"] == vehiculo
        ].sort_values("datetime_utc")

        fin_previo = float(
            grupo.iloc[-1]["energia_bateria_kwh"]
        )

        if abs(
            fin_previo - energias[vehiculo]
        ) > 0.03:
            raise RuntimeError(
                f"La batería de {vehiculo} no coincide "
                "con el estado del plan anterior."
            )

    modelo = pulp.LpProblem(
        "FlotIQ_Preparacion_Automatica",
        pulp.LpMinimize,
    )

    indices = [
        (v, i)
        for v in preparables
        for i in range(len(horas))
    ]

    extra = modelo.add_variable_dicts(
        "extra_red",
        indices,
        lowBound=0,
    )

    nueva_conexion = modelo.add_variable_dicts(
        "nueva_conexion",
        indices,
        cat="Binary",
    )

    # -----------------------------------------
    # RESTRICCIONES DE CADA VEHICULO
    # -----------------------------------------

    for vehiculo in preparables:

        acumulada = 0

        for i, hora in enumerate(horas):

            fila = indice.loc[
                (vehiculo, hora)
            ]

            disponible = bool(
                fila["disponible_carga"]
            )

            conectado_original = (
                float(fila["conexion"]) > 0.5
            )

            carga_original = float(
                fila["recarga_red_kwh"]
            )

            limite = max(
                0.0,
                POTENCIA_CARGADOR_KW - carga_original,
            )

            # Nunca cargar durante un servicio.

            if not disponible:

                modelo += extra[vehiculo, i] == 0

                modelo += (
                    nueva_conexion[vehiculo, i] == 0
                )

            elif conectado_original:

                # Si ya utiliza un cargador,
                # aprovechar su capacidad restante.

                modelo += (
                    extra[vehiculo, i] <= limite
                )

                modelo += (
                    nueva_conexion[vehiculo, i] == 0
                )

            else:

                # Nueva conexión únicamente
                # cuando existe capacidad.

                modelo += (
                    extra[vehiculo, i]
                    <= limite * nueva_conexion[vehiculo, i]
                )

            acumulada += (
                EFICIENCIA_CARGA * extra[vehiculo, i]
            )

            # Respetar siempre el 80 % máximo.

            modelo += (
                float(fila["energia_bateria_kwh"])
                + acumulada
                <= MAX_BATERIA + 1e-7
            )

        # Aportar la energía requerida por vehículo.

        modelo += (
            EFICIENCIA_CARGA
            * pulp.lpSum(
                extra[vehiculo, i]
                for i in range(len(horas))
            )
            == ajustes[vehiculo]
        )

    # -----------------------------------------
    # RESTRICCIONES COMPARTIDAS
    # -----------------------------------------

    for i, hora in enumerate(horas):

        filas = plan.loc[
            plan["datetime_utc"] == hora
        ]

        base_energia = float(
            filas["recarga_red_kwh"].sum()
        )

        base_conexiones = int(
            (filas["conexion"] > 0.5).sum()
        )

        # Máximo 150 kW de instalación.

        modelo += (
            base_energia
            + pulp.lpSum(
                extra[v, i]
                for v in preparables
            )
            <= POTENCIA_MAX_INSTALACION_KW
        )

        # Máximo 20 cargadores simultáneos.

        modelo += (
            base_conexiones
            + pulp.lpSum(
                nueva_conexion[v, i]
                for v in preparables
            )
            <= NUM_CARGADORES
        )

    # -----------------------------------------
    # OBJETIVO: MINIMIZAR COSTE
    # -----------------------------------------

    modelo += pulp.lpSum(
        extra[v, i]
        * float(
            indice.loc[
                (v, hora),
                "precio_predicho_eur_mwh",
            ]
        )
        / 1000

        for v in preparables
        for i, hora in enumerate(horas)
    )

    estadisticas = modelo.solve(
        pulp.COIN_CMD(
            msg=False,
            timeLimit=30,
        )
    )

    if (
        not estadisticas.has_solution
        or estadisticas.status_str
        in {"Infeasible", "Unbounded"}
    ):
        raise RuntimeError(
            "No hay preparación anticipada factible. "
            f"Estado CBC: {estadisticas.status_str}"
        )

    # -----------------------------------------
    # RECUPERAR RESULTADOS
    # -----------------------------------------

    nuevas_energias = dict(energias)

    registros = []

    for vehiculo in preparables:

        entregada = 0.0

        for i, hora in enumerate(horas):

            red = float(
                pulp.value(extra[vehiculo, i]) or 0.0
            )

            if (
                red < -0.002
                or red > POTENCIA_CARGADOR_KW + 0.002
            ):
                raise RuntimeError(
                    "Recarga de preparación inválida"
                )

            entregada += (
                red * EFICIENCIA_CARGA
            )

            if red <= 0.001:
                continue

            precio = float(
                indice.loc[
                    (vehiculo, hora),
                    "precio_predicho_eur_mwh",
                ]
            )

            registros.append({
                "vehiculo": vehiculo,
                "fecha_local": (
                    pd.Timestamp(hora)
                    .tz_convert(TZ)
                    .isoformat()
                ),
                "energia_red_kwh": round(red, 4),
                "energia_bateria_kwh": round(
                    red * EFICIENCIA_CARGA,
                    4,
                ),
                "coste_estimado_eur": round(
                    red * precio / 1000,
                    5,
                ),
            })

        if abs(
            entregada - ajustes[vehiculo]
        ) > 0.002:
            raise RuntimeError(
                f"La preparación de {vehiculo} "
                "no cumple el objetivo energético"
            )

        nuevas_energias[vehiculo] = (
            energias[vehiculo] + entregada
        )

        if (
            nuevas_energias[vehiculo]
            > MAX_BATERIA + 0.002
        ):
            raise RuntimeError(
                f"El vehículo {vehiculo} supera el 80 %"
            )

    # -----------------------------------------
    # VALIDACION INDEPENDIENTE
    # -----------------------------------------

    for vehiculo in preparables:

        acumulada_bateria = 0.0

        for i, hora in enumerate(horas):

            fila = indice.loc[
                (vehiculo, hora)
            ]

            adicion = float(
                pulp.value(extra[vehiculo, i]) or 0.0
            )

            conexion_nueva = float(
                pulp.value(
                    nueva_conexion[vehiculo, i]
                ) or 0.0
            )

            if abs(
                conexion_nueva - round(conexion_nueva)
            ) > 0.002:
                raise RuntimeError(
                    "Conexión adicional no binaria"
                )

            if (
                adicion > 0.002
                and not bool(fila["disponible_carga"])
            ):
                raise RuntimeError(
                    "Recarga durante un servicio"
                )

            if (
                adicion
                + float(fila["recarga_red_kwh"])
                > POTENCIA_CARGADOR_KW + 0.002
            ):
                raise RuntimeError(
                    "Potencia individual excedida"
                )

            if (
                adicion > 0.002
                and float(fila["conexion"]) < 0.5
                and conexion_nueva < 0.5
            ):
                raise RuntimeError(
                    "Recarga adicional sin conexión"
                )

            acumulada_bateria += (
                adicion * EFICIENCIA_CARGA
            )

            if (
                float(fila["energia_bateria_kwh"])
                + acumulada_bateria
                > MAX_BATERIA + 0.002
            ):
                raise RuntimeError(
                    "SOC máximo excedido"
                )

    for i, hora in enumerate(horas):

        filas = plan.loc[
            plan["datetime_utc"] == hora
        ]

        aumento = sum(
            float(
                pulp.value(extra[v, i]) or 0.0
            )
            for v in preparables
        )

        nuevas = sum(
            int(
                round(
                    float(
                        pulp.value(
                            nueva_conexion[v, i]
                        ) or 0.0
                    )
                )
            )
            for v in preparables
        )

        if (
            float(filas["recarga_red_kwh"].sum())
            + aumento
            > POTENCIA_MAX_INSTALACION_KW + 0.002
        ):
            raise RuntimeError(
                "Potencia compartida superada"
            )

        if (
            int((filas["conexion"] > 0.5).sum())
            + nuevas
            > NUM_CARGADORES
        ):
            raise RuntimeError(
                "Número máximo de cargadores superado"
            )

    # -----------------------------------------
    # RESPUESTA DE PREPARACION
    # -----------------------------------------

    preparacion = {
        "aplicada": True,
        "fecha": fecha_consulta.isoformat(),
        "vehiculos": preparables,
        "energia_extra_bateria_kwh": round(
            sum(ajustes.values()),
            3,
        ),
        "energia_red_kwh": round(
            sum(
                r["energia_red_kwh"]
                for r in registros
            ),
            3,
        ),
        "coste_estimado_eur": round(
            sum(
                r["coste_estimado_eur"]
                for r in registros
            ),
            4,
        ),
        "registros": registros,
        "nota": (
            "Preparación contrafactual sobre el plan "
            "anterior. No ejecutada ni guardada. "
            "Los costes utilizan precios previstos."
        ),
    }

    return nuevas_energias, preparacion


# =============================================
# 6. OPTIMIZAR CON PREPARACION AUTOMATICA
# =============================================

def optimizar_con_preparacion(
    *,
    fecha_consulta: date,
    cambio_demanda_pct: int,
    datos_operativos: pd.DataFrame,
    precios_horarios: pd.DataFrame,
    energia_final_objetivo: dict,
    energia_inicial_vehiculos: dict,
    **opciones_optimizador,
) -> dict:

    """
    1. Intentar optimización original.
    2. Si falla por inviabilidad y aumenta la demanda,
       detectar necesidades de preparación.
    3. Programar recargas previas.
    4. Repetir optimización.
    5. Validar resultado.

    No guarda ni sobrescribe planes.
    """

    parametros = dict(
        datos_operativos=datos_operativos,
        precios_horarios=precios_horarios,
        energia_final_objetivo=energia_final_objetivo,
        energia_inicial_vehiculos=energia_inicial_vehiculos,
        **opciones_optimizador,
    )

    # PRIMER INTENTO: SIN PREPARACION

    try:

        resultado = optimizar_recargas(
            **parametros
        )

        resultado["preparacion_anticipada"] = None

        return resultado

    except RuntimeError as error:

        if (
            cambio_demanda_pct <= 0
            or "infeasible" not in str(error).lower()
        ):
            raise

        error_original = str(error)

    # DIAGNOSTICAR LAS BATERIAS

    operaciones = _operaciones_normalizadas(
        datos_operativos
    )

    ajustes = _necesidades_iniciales(
        operaciones,
        energia_inicial_vehiculos,
    )

    if not ajustes:
        raise RuntimeError(
            "El escenario es inviable, pero no se "
            "detecta un déficit individual de batería. "
            "Es posible que falten cargadores o potencia. "
            f"Error original: {error_original}"
        )

    # BUSCAR PREPARACION DEL DIA ANTERIOR

    energia_preparada, preparacion = (
        _programar_preparacion(
            fecha_consulta,
            energia_inicial_vehiculos,
            ajustes,
        )
    )

    # SEGUNDO INTENTO: CON BATERIAS PREPARADAS

    parametros["energia_inicial_vehiculos"] = (
        energia_preparada
    )

    try:

        resultado = optimizar_recargas(
            **parametros
        )

    except (RuntimeError, ValueError) as error:

        raise RuntimeError(
            "La preparación propuesta no es suficiente "
            "para obtener una planificación válida: "
            f"{error}"
        ) from error

    if not resultado.get("factibilidad_validada"):
        raise RuntimeError(
            "La planificación preparada no supera "
            "la validación"
        )

    resultado["preparacion_anticipada"] = preparacion

    return resultado
