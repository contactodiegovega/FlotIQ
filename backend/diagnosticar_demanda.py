
from pathlib import Path
from datetime import date, timedelta
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

FECHA_CONSULTA = date(2026, 10, 26)
AUMENTO_DEMANDA = 20
DIA_AFECTADO = "ambos"

BATERIA_MAX = 60 * 0.80
BATERIA_MIN = 60 * 0.15
CARGA_EFECTIVA_HORA = 11 * 0.90

primer_dia = FECHA_CONSULTA + timedelta(days=1)
segundo_dia = FECHA_CONSULTA + timedelta(days=2)

fecha_texto = FECHA_CONSULTA.isoformat()

ruta_ops = PROCESSED / (
    f"prevision_operaciones_48h_emitida_{fecha_texto}.parquet"
)

ruta_estado = PROCESSED / (
    f"estado_baterias_{primer_dia.isoformat()}.json"
)

operaciones = pd.read_parquet(ruta_ops)

operaciones["datetime_utc"] = pd.to_datetime(
    operaciones["datetime_utc"],
    utc=True,
)

operaciones = operaciones.sort_values(
    ["vehicle_id", "datetime_utc"]
)

estado = json.loads(
    ruta_estado.read_text(encoding="utf-8")
)

iniciales = estado["energia_inicial_vehiculos"]


def consumo_ajustado(fila):
    fecha_local = fila.datetime_utc.tz_convert(
        "Europe/Madrid"
    ).date()

    afectado = (
        DIA_AFECTADO == "ambos"
        or (
            DIA_AFECTADO == "primero"
            and fecha_local == primer_dia
        )
        or (
            DIA_AFECTADO == "segundo"
            and fecha_local == segundo_dia
        )
    )

    factor = (
        1 + AUMENTO_DEMANDA / 100
        if afectado
        else 1
    )

    return float(fila.energia_consumida_kwh) * factor


def comprobar_vehiculo(grupo, energia_inicial):
    energia = energia_inicial

    for fila in grupo.itertuples(index=False):
        consumo = consumo_ajustado(fila)

        carga = (
            CARGA_EFECTIVA_HORA
            if fila.disponible_carga
            else 0
        )

        # Escenario optimista:
        # cargar al máximo en toda hora disponible,
        # independientemente del precio.
        energia = min(
            BATERIA_MAX,
            energia - consumo + carga,
        )

        if energia < BATERIA_MIN - 0.001:
            return {
                "hora": fila.datetime_utc,
                "deficit_kwh": round(
                    BATERIA_MIN - energia, 2
                ),
            }

    return None


fallos_actuales = []
fallos_preparados = []

for vehiculo, grupo in operaciones.groupby("vehicle_id"):
    inicial = float(iniciales[str(vehiculo)])

    fallo_actual = comprobar_vehiculo(
        grupo, inicial
    )

    fallo_preparado = comprobar_vehiculo(
        grupo, BATERIA_MAX
    )

    if fallo_actual:
        fallos_actuales.append(
            (vehiculo, fallo_actual)
        )

    if fallo_preparado:
        fallos_preparados.append(
            (vehiculo, fallo_preparado)
        )


print()
print("DIAGNOSTICO DE DEMANDA FLOTIQ")
print("Fecha:", fecha_texto)
print("Aumento:", AUMENTO_DEMANDA, "%")
print("Dia afectado:", DIA_AFECTADO)

print()
print(
    "Vehiculos imposibles con SOC inicial actual:",
    len(fallos_actuales),
)

print(
    "Vehiculos imposibles incluso iniciando al 80%:",
    len(fallos_preparados),
)

print()
print("Primeros problemas detectados:")

for vehiculo, problema in fallos_actuales[:10]:
    print(
        vehiculo,
        problema["hora"],
        "déficit:",
        problema["deficit_kwh"],
        "kWh",
    )

print()

if fallos_preparados:
    print(
        "Hay vehiculos que necesitan cambiar su "
        "programacion de servicios o disponibilidad."
    )
elif fallos_actuales:
    print(
        "La preparacion previa de baterias podria "
        "resolver parte del problema. Debe verificarse "
        "si esa carga previa se puede programar."
    )
else:
    print(
        "Los vehiculos tienen capacidad individual "
        "suficiente en esta prueba optimista."
    )
    print(
        "Hay que comprobar los limites compartidos "
        "de cargadores y potencia."
    )
