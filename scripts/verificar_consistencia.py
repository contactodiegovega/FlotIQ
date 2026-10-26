
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1] / "data" / "processed"

COLUMNAS = [
    "recarga_red_kwh",
    "energia_bateria_kwh",
    "conexion",
    "soc_pct",
    "coste_estimado_eur",
    "precio_predicho_eur_mwh",
    "energia_consumida_kwh",
    "disponible_carga",
]


def leer_dia(dia, emision):
    ruta = BASE / (
        f"planificacion_ml_48h_{emision}.parquet"
    )

    df = pd.read_parquet(ruta)

    df["datetime_utc"] = pd.to_datetime(
        df["datetime_utc"], utc=True
    )

    df["vehicle_id"] = df["vehicle_id"].astype(str)

    df = df.loc[
        df["datetime_utc"]
        .dt.tz_convert("Europe/Madrid")
        .dt.date == dia
    ]

    if df.empty:
        raise RuntimeError(
            f"Sin registros del día {dia} en {ruta.name}"
        )

    if df.duplicated(
        ["vehicle_id", "datetime_utc"]
    ).any():
        raise RuntimeError(
            "Registros duplicados"
        )

    return (
        df.set_index(
            ["vehicle_id", "datetime_utc"]
        )[COLUMNAS]
        .sort_index()
    )


def verificar(dia):

    plan_anterior = leer_dia(
        dia, dia - timedelta(days=2)
    )

    plan_siguiente = leer_dia(
        dia, dia - timedelta(days=1)
    )

    if not plan_anterior.index.equals(
        plan_siguiente.index
    ):
        raise AssertionError(
            "Los vehículos y horas no coinciden"
        )

    for columna in COLUMNAS:

        a = plan_anterior[columna]
        b = plan_siguiente[columna]

        if columna == "disponible_carga":
            iguales = a.astype(bool).equals(
                b.astype(bool)
            )
        else:
            iguales = np.allclose(
                a.to_numpy(dtype=float),
                b.to_numpy(dtype=float),
                atol=1e-4,
                rtol=0,
            )

        if not iguales:
            raise AssertionError(
                f"Diferencia detectada en {columna}"
            )

    coste = round(
        float(
            plan_anterior["coste_estimado_eur"].sum()
        ),
        2,
    )

    energia = round(
        float(
            plan_anterior["recarga_red_kwh"].sum()
        ),
        2,
    )

    # Comprobar continuidad de baterías.
    ruta_estado = BASE / (
        f"estado_baterias_{dia + timedelta(days=1)}.json"
    )

    estado = json.loads(
        ruta_estado.read_text(encoding="utf-8")
    )

    finales = (
        plan_siguiente.reset_index()
        .sort_values("datetime_utc")
        .groupby("vehicle_id")
        .tail(1)
    )

    baterias = estado["energia_inicial_vehiculos"]

    if set(finales["vehicle_id"]) != set(baterias):
        raise AssertionError(
            "Faltan vehículos en el estado posterior"
        )

    for fila in finales.itertuples(index=False):
        if abs(
            float(fila.energia_bateria_kwh)
            - float(baterias[fila.vehicle_id])
        ) > 0.025:
            raise AssertionError(
                f"Continuidad incorrecta: {fila.vehicle_id}"
            )

    print()
    print("FLOTIQ | CONSISTENCIA VALIDADA")
    print("--------------------------------")
    print("Día:", dia)
    print("Registros:", len(plan_anterior))
    print("Coste en ambos planes:", coste, "EUR")
    print("Recarga en ambos planes:", energia, "kWh")
    print("Baterías:", "CONTINUIDAD CORRECTA")
    print("Resultado:", "COINCIDENCIA CONFIRMADA")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--dia",
        required=True,
        type=date.fromisoformat,
    )

    args = parser.parse_args()

    verificar(args.dia)
