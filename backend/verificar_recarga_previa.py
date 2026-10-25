
from datetime import date, timedelta
from pathlib import Path
import json

import pandas as pd
import pulp

from backend.optimizador import (
    CAPACIDAD_BATERIA_KWH,
    SOC_OBJETIVO,
    EFICIENCIA_CARGA,
    POTENCIA_CARGADOR_KW,
    POTENCIA_MAX_INSTALACION_KW,
    NUM_CARGADORES,
)

ROOT = Path(__file__).resolve().parents[1]
DATOS = ROOT / "data" / "processed"

FECHA_CONSULTA = date(2026, 10, 26)
VEHICULO = "V016"
EXTRA_BATERIA_KWH = 2.0
ZONA = "Europe/Madrid"

fecha_anterior = FECHA_CONSULTA - timedelta(days=1)
fecha_inicio = FECHA_CONSULTA + timedelta(days=1)

ruta_plan = DATOS / (
    f"planificacion_ml_48h_{fecha_anterior.isoformat()}.parquet"
)

ruta_estado = DATOS / (
    f"estado_baterias_{fecha_inicio.isoformat()}.json"
)

if not ruta_plan.exists():
    raise FileNotFoundError(f"Falta {ruta_plan.name}")

if not ruta_estado.exists():
    raise FileNotFoundError(f"Falta {ruta_estado.name}")

plan = pd.read_parquet(ruta_plan)

columnas = {
    "datetime_utc",
    "vehicle_id",
    "recarga_red_kwh",
    "energia_bateria_kwh",
    "disponible_carga",
    "conexion",
    "precio_predicho_eur_mwh",
}

faltantes = columnas - set(plan.columns)

if faltantes:
    raise ValueError(
        f"Faltan columnas: {sorted(faltantes)}"
    )

plan["datetime_utc"] = pd.to_datetime(
    plan["datetime_utc"],
    utc=True,
)

# Recuperar exclusivamente la jornada anterior.
plan = plan.loc[
    plan["datetime_utc"].dt.tz_convert(ZONA).dt.date
    == FECHA_CONSULTA
].copy()

if plan.empty:
    raise ValueError("No hay datos del día anterior")

vehiculo = plan.loc[
    plan["vehicle_id"] == VEHICULO
].sort_values("datetime_utc").copy()

horas = vehiculo["datetime_utc"].tolist()

if len(horas) != 24:
    raise ValueError(
        "El vehículo no tiene 24 horas de planificación"
    )

if plan.duplicated(
    ["vehicle_id", "datetime_utc"]
).any():
    raise ValueError("Hay registros duplicados")

estado = json.loads(
    ruta_estado.read_text(encoding="utf-8")
)

energia_guardada = float(
    estado["energia_inicial_vehiculos"][VEHICULO]
)

energia_final_anterior = float(
    vehiculo.iloc[-1]["energia_bateria_kwh"]
)

# El estado de salida del día anterior debe coincidir
# con la batería inicial utilizada por el escenario.
if abs(
    energia_guardada - energia_final_anterior
) > 0.03:
    raise ValueError(
        "El estado de baterías no coincide con "
        "la planificación del día anterior"
    )

maximo_bateria = (
    CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO
)

if energia_guardada + EXTRA_BATERIA_KWH > maximo_bateria:
    raise ValueError(
        "La preparación excedería el 80% de batería"
    )

modelo = pulp.LpProblem(
    "FlotIQ_Preparacion_Anticipada",
    pulp.LpMinimize,
)

indices = list(range(len(horas)))

extra = modelo.add_variable_dicts(
    "energia_extra_red",
    indices,
    lowBound=0,
)

precios = []
limites = []

for i, hora in enumerate(horas):
    filas_hora = plan.loc[
        plan["datetime_utc"] == hora
    ]

    registro = vehiculo.iloc[i]

    energia_vehiculo = float(
        registro["recarga_red_kwh"]
    )

    carga_total = float(
        filas_hora["recarga_red_kwh"].sum()
    )

    conexiones = int(
        (filas_hora["conexion"] > 0.5).sum()
    )

    disponible = bool(
        registro["disponible_carga"]
    )

    conectado = (
        float(registro["conexion"]) > 0.5
    )

    espacio_vehiculo = max(
        0.0,
        POTENCIA_CARGADOR_KW - energia_vehiculo,
    )

    espacio_instalacion = max(
        0.0,
        POTENCIA_MAX_INSTALACION_KW - carga_total,
    )

    if (
        not disponible
        or (
            not conectado
            and conexiones >= NUM_CARGADORES
        )
    ):
        limite = 0.0
    else:
        limite = min(
            espacio_vehiculo,
            espacio_instalacion,
        )

    modelo += extra[i] <= limite

    limites.append(limite)

    precios.append(
        float(
            registro["precio_predicho_eur_mwh"]
        )
    )

    # La carga adicional se acumula en la batería.
    # Nunca puede superar el 80%.
    aumento_acumulado = (
        EFICIENCIA_CARGA
        * pulp.lpSum(
            extra[j]
            for j in range(i + 1)
        )
    )

    modelo += (
        float(registro["energia_bateria_kwh"])
        + aumento_acumulado
        <= maximo_bateria
    )

# Queremos aportar exactamente 2 kWh a la batería.
modelo += (
    EFICIENCIA_CARGA
    * pulp.lpSum(extra[i] for i in indices)
    == EXTRA_BATERIA_KWH
)

# Elegir las horas más baratas entre las factibles.
modelo += pulp.lpSum(
    extra[i] * precios[i] / 1000
    for i in indices
)

estadisticas = modelo.solve(
    pulp.COIN_CMD(
        msg=False,
        timeLimit=30,
    )
)

print()
print("VERIFICACION DE PREPARACION ANTICIPADA")
print("Vehiculo:", VEHICULO)
print("Dia de preparacion:", FECHA_CONSULTA)
print("Energia adicional en bateria:", EXTRA_BATERIA_KWH, "kWh")
print("Energia inicial original:", energia_guardada, "kWh")
print("Estado del solver:", estadisticas.status_str)
print()

if not estadisticas.has_solution:
    print(
        "No se ha encontrado una recarga adicional "
        "compatible con el plan anterior sin modificar "
        "las recargas de los demás vehículos."
    )
else:
    cargas = [
        float(pulp.value(extra[i]) or 0.0)
        for i in indices
    ]

    energia_red = sum(cargas)

    energia_entregada = (
        energia_red * EFICIENCIA_CARGA
    )

    coste = sum(
        cargas[i] * precios[i] / 1000
        for i in indices
    )

    if abs(
        energia_entregada - EXTRA_BATERIA_KWH
    ) > 0.002:
        raise RuntimeError(
            "La carga adicional no ha sido validada"
        )

    print("PREPARACION FACTIBLE")
    print("Electricidad adicional:", round(energia_red, 3), "kWh")
    print("Coste adicional estimado:", round(coste, 4), "EUR")
    print()
    print("HORARIO DE PREPARACION")

    for i, cantidad in enumerate(cargas):
        if cantidad > 0.001:
            print(
                horas[i].tz_convert(ZONA),
                "recarga adicional:",
                round(cantidad, 3),
                "kWh",
                "precio:",
                round(precios[i], 2),
                "EUR/MWh",
            )

    print()
    print(
        "Bateria prevista al inicio del 27:",
        round(
            energia_guardada + energia_entregada,
            3,
        ),
        "kWh",
    )

print()
print("Los archivos originales no se han modificado.")
