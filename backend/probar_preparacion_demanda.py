
from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd
from fastapi import HTTPException

import backend.api_escenarios as escenarios
from backend.optimizador import (
    CAPACIDAD_BATERIA_KWH,
    SOC_OBJETIVO,
)

FECHA = date(2026, 10, 26)
MODELO = "baseline"
AUMENTO_DEMANDA = 20
VEHICULO = "V016"

ruta_operaciones = escenarios.PROCESSED / (
    f"prevision_operaciones_48h_emitida_{FECHA.isoformat()}.parquet"
)

operaciones = pd.read_parquet(ruta_operaciones)

vehiculos = sorted(
    operaciones["vehicle_id"].astype(str).unique()
)

# Leer el estado de baterías real de la simulación anterior.
estado_original = escenarios.baterias_inicio(
    FECHA,
    vehiculos,
)

energia_actual = estado_original[VEHICULO]

energia_maxima = (
    CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO
)

energia_adicional = (
    energia_maxima - energia_actual
)

print()
print("PREPARACION ANTICIPADA")
print("Vehiculo:", VEHICULO)
print("Energia inicial:", round(energia_actual, 3), "kWh")
print("Energia maxima:", energia_maxima, "kWh")
print(
    "Margen de preparacion:",
    round(energia_adicional, 3),
    "kWh",
)

# Copia en memoria. No modifica el estado guardado.
estado_preparado = estado_original.copy()
energia_extra_prueba = 2.0

estado_preparado[VEHICULO] = min(
    energia_actual + energia_extra_prueba,
    energia_maxima,
)

solicitud = escenarios.SolicitudEscenario(
    fecha_consulta=FECHA,
    modelo=MODELO,
    cambio_demanda_pct=AUMENTO_DEMANDA,
    dia_demanda="ambos",
)

print()
print("Probando demanda +20%")
print(
    "V016 inicia con:",
    round(estado_preparado[VEHICULO], 3),
    "kWh",
)
print("El resto conserva su estado inicial")
print("Ejecutando CBC...")
print()

try:
    with patch.object(
        escenarios,
        "baterias_inicio",
        return_value=estado_preparado,
    ):
        resultado = escenarios.simular(solicitud)

    resumen = resultado["resumen"]

    print("RESULTADO: FACTIBLE")
    print("Estado solver:", resumen["estado_solver"])
    print(
        "Coste estimado:",
        resumen["coste_estimado_eur"],
        "EUR",
    )
    print(
        "Energia de red:",
        resumen["energia_red_kwh"],
        "kWh",
    )
    print(
        "Registros:",
        len(resultado["calendario"]["registros"]),
    )

except HTTPException as error:
    print("RESULTADO: NO VALIDADO")
    print("Motivo:", error.detail)

except (ValueError, RuntimeError) as error:
    print("RESULTADO: ERROR")
    print("Motivo:", error)

print()
print("Prueba terminada.")
print("No se ha modificado ningun archivo.")
