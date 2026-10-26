
# FLOTIQ | OPTIMIZADOR CON RESERVA INTERMEDIA

import numpy as np
import pandas as pd
import pulp


CAPACIDAD_BATERIA_KWH = 60.0
SOC_MINIMO = 0.15
SOC_OBJETIVO = 0.80
SOC_INICIAL = 0.80
EFICIENCIA_CARGA = 0.90
POTENCIA_CARGADOR_KW = 11.0
POTENCIA_MAX_INSTALACION_KW = 150.0
NUM_CARGADORES = 20
INTERVALO_HORAS = 1.0
TOLERANCIA = 0.002


def optimizar_recargas(
    datos_operativos: pd.DataFrame,
    precios_horarios: pd.DataFrame,
    energia_final_objetivo: dict,
    tiempo_maximo_segundos: int = 180,
    energia_inicial_vehiculos: dict | None = None,
    objetivo_final_flexible: bool = False,
    penalizacion_deficit_eur_kwh: float = 1.0,
    indice_fin_primer_dia: int | None = None,
    soc_objetivo_intermedio: float = 0.40,
    penalizacion_intermedia_eur_kwh: float = 2.0,
    soc_objetivo_primer_dia: float | None = None,
):
    # 1. PREPARAR DATOS

    datos = datos_operativos.copy()
    precios = precios_horarios.copy()

    columnas_operativas = {
        "vehicle_id",
        "hora",
        "energia_consumida_kwh",
        "disponible_carga",
    }

    columnas_precios = {"hora", "price_eur_mwh"}

    if datos.empty or precios.empty:
        raise ValueError("No hay operaciones o precios.")

    if not columnas_operativas.issubset(datos.columns):
        raise ValueError("Faltan columnas operativas.")

    if not columnas_precios.issubset(precios.columns):
        raise ValueError("Faltan columnas de precios.")

    datos["hora"] = pd.to_datetime(
        datos["hora"], utc=True
    )
    precios["hora"] = pd.to_datetime(
        precios["hora"], utc=True
    )

    if datos["hora"].isna().any() or precios["hora"].isna().any():
        raise ValueError("Hay horas vacías.")

    # Normalización a UTC sin zona para el modelo

    datos["hora"] = datos["hora"].dt.tz_localize(None)
    precios["hora"] = precios["hora"].dt.tz_localize(None)

    if datos["vehicle_id"].isna().any():
        raise ValueError("Existen vehículos sin identificador.")

    if datos.duplicated(["vehicle_id", "hora"]).any():
        raise ValueError("Hay operaciones duplicadas.")

    if precios["hora"].duplicated().any():
        raise ValueError("Hay precios duplicados.")

    datos["energia_consumida_kwh"] = pd.to_numeric(
        datos["energia_consumida_kwh"], errors="coerce"
    )

    precios["price_eur_mwh"] = pd.to_numeric(
        precios["price_eur_mwh"], errors="coerce"
    )

    if not np.isfinite(
        datos["energia_consumida_kwh"].to_numpy()
    ).all():
        raise ValueError("Consumos no numéricos.")

    if (datos["energia_consumida_kwh"] < 0).any():
        raise ValueError("Consumos negativos.")

    if not np.isfinite(
        precios["price_eur_mwh"].to_numpy()
    ).all():
        raise ValueError("Precios no numéricos.")

    if datos["disponible_carga"].isna().any():
        raise ValueError("Disponibilidad incompleta.")

    if not pd.api.types.is_bool_dtype(
        datos["disponible_carga"]
    ):
        raise ValueError(
            "disponible_carga debe ser booleana."
        )

    precios = precios.sort_values(
        "hora"
    ).reset_index(drop=True)

    horas = precios["hora"].tolist()

    if len(horas) > 1 and not (
        precios["hora"].diff().iloc[1:]
        == pd.Timedelta(hours=1)
    ).all():
        raise ValueError(
            "El horizonte no tiene horas consecutivas."
        )

    vehiculos = sorted(
        datos["vehicle_id"].unique().tolist()
    )

    if set(energia_final_objetivo) != set(vehiculos):
        raise ValueError(
            "Faltan objetivos finales por vehículo."
        )

    if len(datos) != len(vehiculos) * len(horas):
        raise ValueError(
            "La matriz vehículo-hora está incompleta."
        )

    if set(datos["hora"]) != set(horas):
        raise ValueError(
            "Las horas de precios y operaciones no coinciden."
        )

    datos_idx = datos.set_index(
        ["vehicle_id", "hora"]
    )

    precios_idx = precios.set_index(
        "hora"
    )["price_eur_mwh"]

    energia_min = CAPACIDAD_BATERIA_KWH * SOC_MINIMO
    energia_max = CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO

    # 2. ESTADOS INICIALES Y OBJETIVOS

    if energia_inicial_vehiculos is None:
        energia_inicial_vehiculos = {
            v: CAPACIDAD_BATERIA_KWH * SOC_INICIAL
            for v in vehiculos
        }

    if set(energia_inicial_vehiculos) != set(vehiculos):
        raise ValueError(
            "Faltan estados iniciales de batería."
        )

    iniciales = {}
    objetivos = {}

    for v in vehiculos:
        inicial = float(
            energia_inicial_vehiculos[v]
        )
        objetivo = float(
            energia_final_objetivo[v]
        )

        if (
            not np.isfinite(inicial)
            or not energia_min <= inicial <= energia_max
        ):
            raise ValueError(
                f"Batería inicial inválida: {v}"
            )

        if (
            not np.isfinite(objetivo)
            or not energia_min <= objetivo <= energia_max
        ):
            raise ValueError(
                f"Objetivo final inválido: {v}"
            )

        iniciales[v] = inicial
        objetivos[v] = objetivo

    # 3. VALIDAR PENALIZACIONES

    if objetivo_final_flexible:
        if (
            not np.isfinite(penalizacion_deficit_eur_kwh)
            or penalizacion_deficit_eur_kwh <= 0
        ):
            raise ValueError(
                "Penalización final inválida."
            )

    # Solo existe una reserva intermedia.
    # Puede indicarse su índice o calcularse
    # automáticamente para el primer día local.

    if soc_objetivo_primer_dia is not None:

        if indice_fin_primer_dia is not None:
            raise ValueError(
                "No combines soc_objetivo_primer_dia "
                "e indice_fin_primer_dia."
            )

        if not (
            np.isfinite(soc_objetivo_primer_dia)
            and SOC_MINIMO
            <= soc_objetivo_primer_dia
            <= SOC_OBJETIVO
        ):
            raise ValueError(
                "SOC del primer día fuera de límites."
            )

        fechas_locales = (
            pd.DatetimeIndex(horas)
            .tz_localize("UTC")
            .tz_convert("Europe/Madrid")
            .date
        )

        if len(set(fechas_locales)) != 2:
            raise ValueError(
                "La reserva automática requiere "
                "dos días naturales locales."
            )

        primer_dia = fechas_locales[0]

        indice_fin_primer_dia = max(
            i
            for i, dia_local in enumerate(fechas_locales)
            if dia_local == primer_dia
        )

        soc_objetivo_intermedio = float(
            soc_objetivo_primer_dia
        )

    if indice_fin_primer_dia is not None:

        if (
            type(indice_fin_primer_dia) is not int
            or not 0 <= indice_fin_primer_dia < len(horas) - 1
        ):
            raise ValueError(
                "Índice intermedio fuera de rango."
            )

        if not (
            SOC_MINIMO
            <= soc_objetivo_intermedio
            <= SOC_OBJETIVO
        ):
            raise ValueError(
                "SOC intermedio fuera de límites."
            )

        if (
            not np.isfinite(penalizacion_intermedia_eur_kwh)
            or penalizacion_intermedia_eur_kwh <= 0
        ):
            raise ValueError(
                "Penalización intermedia inválida."
            )

    # 4. CREAR MODELO DE OPTIMIZACIÓN

    periodos = range(len(horas))

    indices = [
        (v, t)
        for v in vehiculos
        for t in periodos
    ]

    modelo = pulp.LpProblem(
        "FlotIQ_Recargas",
        pulp.LpMinimize,
    )

    carga = modelo.add_variable_dicts(
        "carga_red",
        indices,
        lowBound=0,
    )

    conexion = modelo.add_variable_dicts(
        "conexion",
        indices,
        cat="Binary",
    )

    bateria = modelo.add_variable_dicts(
        "bateria",
        indices,
        lowBound=energia_min,
        upBound=energia_max,
    )

    # Coste eléctrico

    funcion_objetivo = pulp.lpSum(
        carga[v, t]
        * float(precios_idx.loc[horas[t]])
        / 1000
        for v, t in indices
    )

    deficit_final = None
    deficit_intermedio = None

    objetivo_intermedio_kwh = (
        CAPACIDAD_BATERIA_KWH
        * soc_objetivo_intermedio
    )

    # Penalización por batería final insuficiente

    if objetivo_final_flexible:
        deficit_final = modelo.add_variable_dicts(
            "deficit_final",
            vehiculos,
            lowBound=0,
        )

        funcion_objetivo += (
            penalizacion_deficit_eur_kwh
            * pulp.lpSum(
                deficit_final[v]
                for v in vehiculos
            )
        )

    # Penalización por batería intermedia insuficiente

    if indice_fin_primer_dia is not None:
        deficit_intermedio = modelo.add_variable_dicts(
            "deficit_intermedio",
            vehiculos,
            lowBound=0,
        )

        funcion_objetivo += (
            penalizacion_intermedia_eur_kwh
            * pulp.lpSum(
                deficit_intermedio[v]
                for v in vehiculos
            )
        )

    modelo += funcion_objetivo

    # 5. RESTRICCIONES POR VEHÍCULO

    for v in vehiculos:

        for t in periodos:
            fila = datos_idx.loc[
                (v, horas[t])
            ]

            consumo = float(
                fila["energia_consumida_kwh"]
            )

            disponible = bool(
                fila["disponible_carga"]
            )

            if not disponible:
                modelo += conexion[v, t] == 0

            modelo += (
                carga[v, t]
                <= POTENCIA_CARGADOR_KW
                * INTERVALO_HORAS
                * conexion[v, t]
            )

            anterior = (
                iniciales[v]
                if t == 0
                else bateria[v, t - 1]
            )

            modelo += (
                bateria[v, t]
                == anterior
                - consumo
                + carga[v, t] * EFICIENCIA_CARGA
            )

        # Objetivo al finalizar las 48 horas

        if objetivo_final_flexible:
            modelo += (
                bateria[v, len(horas) - 1]
                + deficit_final[v]
                >= objetivos[v]
            )
        else:
            modelo += (
                bateria[v, len(horas) - 1]
                == objetivos[v]
            )

        # Una única reserva al finalizar el primer día

        if indice_fin_primer_dia is not None:
            modelo += (
                bateria[v, indice_fin_primer_dia]
                + deficit_intermedio[v]
                >= objetivo_intermedio_kwh
            )

    # 6. RESTRICCIONES DE LA INSTALACIÓN

    for t in periodos:
        modelo += (
            pulp.lpSum(
                conexion[v, t]
                for v in vehiculos
            )
            <= NUM_CARGADORES
        )

        modelo += (
            pulp.lpSum(
                carga[v, t]
                for v in vehiculos
            )
            <= POTENCIA_MAX_INSTALACION_KW
            * INTERVALO_HORAS
        )

    # 7. EJECUTAR CBC

    solver = pulp.COIN_CMD(
        msg=False,
        timeLimit=tiempo_maximo_segundos,
    )

    estadisticas = modelo.solve(solver)
    estado = estadisticas.status_str

    if (
        not estadisticas.has_solution
        or estado in {"Infeasible", "Unbounded"}
    ):
        raise RuntimeError(
            f"No hay solución factible. Estado CBC: {estado}"
        )

    # 8. VERIFICAR RESULTADOS

    registros = []

    conexiones_hora = {
        t: 0
        for t in periodos
    }

    carga_hora = {
        t: 0.0
        for t in periodos
    }

    deficit_final_real = 0.0
    deficit_intermedio_real = 0.0

    for v in vehiculos:
        anterior = iniciales[v]

        for t in periodos:
            valores = [
                pulp.value(carga[v, t]),
                pulp.value(bateria[v, t]),
                pulp.value(conexion[v, t]),
            ]

            if any(
                x is None or not np.isfinite(float(x))
                for x in valores
            ):
                raise RuntimeError(
                    f"Solución incompleta: {v}, hora {t}"
                )

            (
                energia_red,
                energia_bateria,
                conectado_real,
            ) = map(float, valores)

            conectado = int(
                round(conectado_real)
            )

            if (
                abs(conectado_real - conectado) > TOLERANCIA
                or conectado not in (0, 1)
            ):
                raise RuntimeError(
                    f"Conexión no binaria: {v}, hora {t}"
                )

            if (
                energia_red < -TOLERANCIA
                or energia_red
                > POTENCIA_CARGADOR_KW
                * INTERVALO_HORAS
                * conectado
                + TOLERANCIA
            ):
                raise RuntimeError(
                    f"Carga individual incorrecta: {v}, hora {t}"
                )

            fila = datos_idx.loc[
                (v, horas[t])
            ]

            if (
                not bool(fila["disponible_carga"])
                and conectado
            ):
                raise RuntimeError(
                    f"Carga fuera de disponibilidad: {v}, hora {t}"
                )

            if not (
                energia_min - TOLERANCIA
                <= energia_bateria
                <= energia_max + TOLERANCIA
            ):
                raise RuntimeError(
                    f"Batería fuera de límites: {v}, hora {t}"
                )

            calculada = (
                anterior
                - float(fila["energia_consumida_kwh"])
                + energia_red * EFICIENCIA_CARGA
            )

            if abs(
                calculada - energia_bateria
            ) > TOLERANCIA:
                raise RuntimeError(
                    f"Balance incorrecto: {v}, hora {t}"
                )

            anterior = energia_bateria

            carga_hora[t] += energia_red
            conexiones_hora[t] += conectado

            precio = float(
                precios_idx.loc[horas[t]]
            )

            registros.append({
                "vehicle_id": v,
                "hora": pd.Timestamp(horas[t]),
                "recarga_red_kwh": max(energia_red, 0.0),
                "energia_bateria_kwh": energia_bateria,
                "conexion": conectado,
                "soc_pct": (
                    energia_bateria
                    / CAPACIDAD_BATERIA_KWH
                    * 100
                ),
                "coste_estimado_eur": (
                    energia_red * precio / 1000
                ),
            })

            # Validar la reserva intermedia

            if t == indice_fin_primer_dia:
                deficit_intermedio_real += max(
                    0.0,
                    objetivo_intermedio_kwh
                    - energia_bateria,
                )

                holgura = pulp.value(
                    deficit_intermedio[v]
                )

                if (
                    holgura is None
                    or energia_bateria + float(holgura)
                    < objetivo_intermedio_kwh - TOLERANCIA
                ):
                    raise RuntimeError(
                        f"Reserva intermedia incorrecta: {v}"
                    )

        # Validar objetivo al final del horizonte

        if objetivo_final_flexible:
            holgura = pulp.value(
                deficit_final[v]
            )

            if (
                holgura is None
                or anterior + float(holgura)
                < objetivos[v] - TOLERANCIA
            ):
                raise RuntimeError(
                    f"Objetivo final flexible incorrecto: {v}"
                )

        elif abs(anterior - objetivos[v]) > TOLERANCIA:
            raise RuntimeError(
                f"Objetivo final incorrecto: {v}"
            )

        deficit_final_real += max(
            0.0,
            objetivos[v] - anterior,
        )

    # Comprobar límites globales

    for t in periodos:

        if conexiones_hora[t] > NUM_CARGADORES:
            raise RuntimeError(
                f"Cargadores excedidos, hora {t}"
            )

        if (
            carga_hora[t]
            > POTENCIA_MAX_INSTALACION_KW
            * INTERVALO_HORAS
            + TOLERANCIA
        ):
            raise RuntimeError(
                f"Potencia excedida, hora {t}"
            )

    # 9. DEVOLVER RESULTADOS

    resultado = pd.DataFrame(registros)

    return {
        "estado": estado,
        "optimalidad_certificada": estado == "Optimal",
        "factibilidad_validada": True,
        "vehiculos": len(vehiculos),
        "horas": len(horas),
        "coste_estimado_eur": round(
            float(resultado["coste_estimado_eur"].sum()),
            2,
        ),
        "energia_total_kwh": round(
            float(resultado["recarga_red_kwh"].sum()),
            2,
        ),
        "recargas": resultado,
        "objetivo_final_flexible": objetivo_final_flexible,
        "deficit_objetivo_final_kwh": round(
            deficit_final_real, 2
        ),
        "indice_fin_primer_dia": indice_fin_primer_dia,
        "soc_objetivo_intermedio": (
            soc_objetivo_intermedio
            if indice_fin_primer_dia is not None
            else None
        ),
        "deficit_objetivo_intermedio_kwh": round(
            deficit_intermedio_real, 2
        ),
    }
