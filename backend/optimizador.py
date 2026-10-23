# FLOTIQ | OPTIMIZADOR REUTILIZABLE DE RECARGAS

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
):
    """Optimiza la recarga de la flota con PuLP 4.x y CBC.

    Requiere operaciones con vehicle_id, hora, disponible_carga y
    energia_consumida_kwh; precios con hora y price_eur_mwh.
    Los intervalos son de una hora. Los costes son estimados y se
    calculan a partir del escenario de precios suministrado.
    """
    
    datos = datos_operativos.copy()
    precios = precios_horarios.copy()

    columnas_operativas = {
        "vehicle_id", "hora", "energia_consumida_kwh", "disponible_carga"
    }
    columnas_precios = {"hora", "price_eur_mwh"}

    if not columnas_operativas.issubset(datos.columns):
        faltan = columnas_operativas - set(datos.columns)
        raise ValueError(f"Faltan columnas operativas: {sorted(faltan)}")
    if not columnas_precios.issubset(precios.columns):
        faltan = columnas_precios - set(precios.columns)
        raise ValueError(f"Faltan columnas de precios: {sorted(faltan)}")
    if datos.empty or precios.empty:
        raise ValueError("No hay operaciones o precios para optimizar.")

    datos["hora"] = pd.to_datetime(datos["hora"])
    precios["hora"] = pd.to_datetime(precios["hora"])
    if datos["hora"].isna().any() or precios["hora"].isna().any():
        raise ValueError("Hay fechas horarias vacías o incorrectas.")

    # Trabajamos con la misma referencia temporal en las dos tablas.
    zona_datos = datos["hora"].dt.tz
    zona_precios = precios["hora"].dt.tz
    if (zona_datos is None) != (zona_precios is None):
        raise ValueError("Operaciones y precios deben usar la misma zona horaria.")
    if zona_datos is not None:
        datos["hora"] = datos["hora"].dt.tz_convert("UTC").dt.tz_localize(None)
        precios["hora"] = precios["hora"].dt.tz_convert("UTC").dt.tz_localize(None)

    if datos["vehicle_id"].isna().any():
        raise ValueError("Hay vehículos sin identificador.")
    if datos.duplicated(["vehicle_id", "hora"]).any():
        raise ValueError("Hay operaciones duplicadas por vehículo y hora.")
    if precios["hora"].duplicated().any():
        raise ValueError("Hay precios horarios duplicados.")

    datos["energia_consumida_kwh"] = pd.to_numeric(
        datos["energia_consumida_kwh"], errors="coerce"
    )
    precios["price_eur_mwh"] = pd.to_numeric(
        precios["price_eur_mwh"], errors="coerce"
    )
    if not np.isfinite(datos["energia_consumida_kwh"].to_numpy()).all():
        raise ValueError("Hay consumos vacíos o no numéricos.")
    if (datos["energia_consumida_kwh"] < 0).any():
        raise ValueError("Hay consumos negativos.")
    if not np.isfinite(precios["price_eur_mwh"].to_numpy()).all():
        raise ValueError("Hay precios vacíos o no numéricos.")
    if datos["disponible_carga"].isna().any():
        raise ValueError("Hay disponibilidades sin informar.")
    if not pd.api.types.is_bool_dtype(datos["disponible_carga"]):
        raise ValueError("disponible_carga debe ser booleana (True/False).")

    precios = precios.sort_values("hora").reset_index(drop=True)
    horas = precios["hora"].tolist()
    if len(horas) > 1 and not (
        precios["hora"].diff().iloc[1:] == pd.Timedelta(hours=1)
    ).all():
        raise ValueError("Los precios deben tener intervalos horarios consecutivos.")

    vehiculos = sorted(datos["vehicle_id"].unique().tolist())
    if set(energia_final_objetivo) != set(vehiculos):
        raise ValueError("Faltan objetivos finales de batería por vehículo.")
    if len(datos) != len(vehiculos) * len(horas):
        raise ValueError("La matriz vehículo-hora está incompleta.")
    if set(datos["hora"]) != set(horas):
        raise ValueError("Las horas de operaciones y precios no coinciden.")

    datos_idx = datos.set_index(["vehicle_id", "hora"])
    precios_idx = precios.set_index("hora")["price_eur_mwh"]

    energia_min = CAPACIDAD_BATERIA_KWH * SOC_MINIMO
    energia_max = CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO
    # Estado inicial de cada vehículo: permite continuidad entre días.
    if energia_inicial_vehiculos is None:
        energia_inicial_vehiculos = {
            v: CAPACIDAD_BATERIA_KWH * SOC_INICIAL
            for v in vehiculos
        }

    if set(energia_inicial_vehiculos) != set(vehiculos):
        raise ValueError("Faltan estados iniciales de batería por vehículo.")

    iniciales = {}
    for vehiculo in vehiculos:
        try:
            inicial = float(energia_inicial_vehiculos[vehiculo])
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Batería inicial no numérica para {vehiculo}."
            ) from error
        if not np.isfinite(inicial) or not energia_min <= inicial <= energia_max:
            raise ValueError(f"Batería inicial fuera de límites: {vehiculo}.")
        iniciales[vehiculo] = inicial

    objetivos = {}
    for vehiculo in vehiculos:
        objetivo = float(energia_final_objetivo[vehiculo])
        if not np.isfinite(objetivo) or not energia_min <= objetivo <= energia_max:
            raise ValueError(f"Objetivo final de batería inválido: {vehiculo}")
        objetivos[vehiculo] = objetivo

    periodos = range(len(horas))
    indices = [(v, t) for v in vehiculos for t in periodos]
    modelo = pulp.LpProblem("FlotIQ_Recargas", pulp.LpMinimize)

    # En PuLP 4.x las variables se crean mediante el propio modelo.
    carga = modelo.add_variable_dicts("carga_red", indices, lowBound=0)
    conexion = modelo.add_variable_dicts("conexion", indices, cat="Binary")
    bateria = modelo.add_variable_dicts(
        "bateria", indices, lowBound=energia_min, upBound=energia_max
    )

    modelo += pulp.lpSum(
        carga[v, t] * float(precios_idx.loc[horas[t]]) / 1000
        for v, t in indices
    )

    for v in vehiculos:
        for t in periodos:
            fila = datos_idx.loc[(v, horas[t])]
            consumo = float(fila["energia_consumida_kwh"])
            disponible = bool(fila["disponible_carga"])

            if not disponible:
                modelo += conexion[v, t] == 0
            modelo += (
                carga[v, t]
                <= POTENCIA_CARGADOR_KW * INTERVALO_HORAS * conexion[v, t]
            )
            anterior = iniciales[v] if t == 0 else bateria[v, t - 1]
            modelo += (
                bateria[v, t]
                == anterior - consumo + carga[v, t] * EFICIENCIA_CARGA
            )

        modelo += bateria[v, len(horas) - 1] == objetivos[v]

    for t in periodos:
        modelo += pulp.lpSum(conexion[v, t] for v in vehiculos) <= NUM_CARGADORES
        modelo += pulp.lpSum(carga[v, t] for v in vehiculos) <= (
            POTENCIA_MAX_INSTALACION_KW * INTERVALO_HORAS
        )

    # En PuLP 4.x solve() devuelve LpSolveStats, no un entero.
    solver = pulp.COIN_CMD(msg=False, timeLimit=tiempo_maximo_segundos)
    estadisticas = modelo.solve(solver)
    estado = estadisticas.status_str

    if not estadisticas.has_solution:
        raise RuntimeError(
            f"CBC no devolvió una solución utilizable (estado: {estado}). "
            "Revisa la factibilidad o amplía el tiempo del solver."
        )
    if estado in {"Infeasible", "Unbounded"}:
        raise RuntimeError(f"CBC devolvió el estado {estado}; no se acepta la solución.")

    # Verificación independiente: una solución con GapLimit puede ser factible
    # sin estar certificada como óptima. Validamos antes de publicarla.
    registros = []
    totales_por_hora = {t: 0.0 for t in periodos}
    conexiones_por_hora = {t: 0 for t in periodos}

    for v in vehiculos:
        anterior = iniciales[v]
        for t in periodos:
            valores = [
                pulp.value(carga[v, t]),
                pulp.value(bateria[v, t]),
                pulp.value(conexion[v, t]),
            ]
            if any(valor is None for valor in valores):
                raise RuntimeError(f"Valores incompletos para {v}, hora {t}.")
            energia_red, energia_bateria, conectado = map(float, valores)
            if not all(np.isfinite(x) for x in valores):
                raise RuntimeError(f"Valores no finitos para {v}, hora {t}.")
            if abs(conectado - round(conectado)) > TOLERANCIA:
                raise RuntimeError(f"Conexión no binaria para {v}, hora {t}.")
            conectado = int(round(conectado))
            if conectado not in (0, 1):
                raise RuntimeError(f"Conexión inválida para {v}, hora {t}.")
            if energia_red < -TOLERANCIA:
                raise RuntimeError(f"Carga negativa para {v}, hora {t}.")
            if energia_red > POTENCIA_CARGADOR_KW * INTERVALO_HORAS * conectado + TOLERANCIA:
                raise RuntimeError(f"Potencia individual excedida para {v}, hora {t}.")
            if not bool(datos_idx.loc[(v, horas[t]), "disponible_carga"]) and conectado:
                raise RuntimeError(f"Carga conectada durante turno de {v}, hora {t}.")
            if not energia_min - TOLERANCIA <= energia_bateria <= energia_max + TOLERANCIA:
                raise RuntimeError(f"Batería fuera de límites para {v}, hora {t}.")

            consumo = float(datos_idx.loc[(v, horas[t]), "energia_consumida_kwh"])
            calculada = anterior - consumo + energia_red * EFICIENCIA_CARGA
            if abs(energia_bateria - calculada) > TOLERANCIA:
                raise RuntimeError(f"Balance energético incorrecto para {v}, hora {t}.")
            anterior = energia_bateria
            totales_por_hora[t] += energia_red
            conexiones_por_hora[t] += conectado
            precio = float(precios_idx.loc[horas[t]])
            registros.append({
                "vehicle_id": v,
                "hora": pd.Timestamp(horas[t]),
                "recarga_red_kwh": max(energia_red, 0.0),
                "energia_bateria_kwh": energia_bateria,
                "conexion": conectado,
                "soc_pct": energia_bateria / CAPACIDAD_BATERIA_KWH * 100,
                "coste_estimado_eur": energia_red * precio / 1000,
            })

        if abs(anterior - objetivos[v]) > TOLERANCIA:
            raise RuntimeError(f"No se cumple el objetivo final del vehículo {v}.")

    for t in periodos:
        if conexiones_por_hora[t] > NUM_CARGADORES:
            raise RuntimeError(f"Se superan 20 cargadores en la hora {t}.")
        if totales_por_hora[t] > POTENCIA_MAX_INSTALACION_KW * INTERVALO_HORAS + TOLERANCIA:
            raise RuntimeError(f"Se superan 150 kW en la hora {t}.")

    resultado = pd.DataFrame(registros)
    return {
        "estado": estado,
        "optimalidad_certificada": estado == "Optimal",
        "factibilidad_validada": True,
        "vehiculos": len(vehiculos),
        "horas": len(horas),
        "coste_estimado_eur": round(float(resultado["coste_estimado_eur"].sum()), 2),
        "energia_total_kwh": round(float(resultado["recarga_red_kwh"].sum()), 2),
        "recargas": resultado,
    }
