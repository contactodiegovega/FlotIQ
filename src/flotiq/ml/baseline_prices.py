
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
)


# ============================================
# CONFIGURACIÓN
# ============================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "omie_ml_hourly.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "omie_baseline_predictions.parquet"
)

TEST_DAYS = 90


# ============================================
# EVALUACIÓN
# ============================================

def calculate_metrics(real, predicted):
    mae = mean_absolute_error(real, predicted)

    rmse = np.sqrt(
        mean_squared_error(real, predicted)
    )

    return mae, rmse


def main():
    print("=" * 55)
    print("FlotIQ | BASELINE PRECIOS OMIE")
    print("=" * 55)

    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"No existe: {DATA_PATH}"
        )

    df = pd.read_parquet(DATA_PATH)

    df["datetime_utc"] = pd.to_datetime(
        df["datetime_utc"],
        utc=True,
    )

    df = df.sort_values(
        "datetime_utc"
    ).reset_index(drop=True)

    # Reservar los últimos 90 días para evaluación.
    test_start = (
        df["datetime_utc"].max()
        - pd.Timedelta(days=TEST_DAYS)
        + pd.Timedelta(hours=1)
    )

    train = df[
        df["datetime_utc"] < test_start
    ].copy()

    test = df[
        df["datetime_utc"] >= test_start
    ].copy()

    if train.empty or test.empty:
        raise ValueError(
            "No hay suficientes datos para evaluar."
        )

    if len(test) != TEST_DAYS * 24:
        raise ValueError(
            "El periodo de prueba no tiene 90 días completos."
        )

    print(f"\nEntrenamiento: {len(train):,} filas")
    print(f"Evaluación: {len(test):,} filas")

    print(
        "Inicio evaluación:",
        test["datetime_utc"].min()
    )

    print(
        "Final evaluación:",
        test["datetime_utc"].max()
    )

    # Baselines sin entrenamiento.
    test["prediction_48h"] = (
        test["price_lag_48h"]
    )

    test["prediction_168h"] = (
        test["price_lag_168h"]
    )

    real = test["price_eur_mwh"]

    print("\nRESULTADOS")
    print("-" * 55)

    results = {}

    for name, column in [
        ("Baseline 48 h", "prediction_48h"),
        ("Baseline semanal", "prediction_168h"),
    ]:

        mae, rmse = calculate_metrics(
            real,
            test[column],
        )

        results[name] = mae

        print(f"\n{name}")
        print(f"MAE:  {mae:.2f} €/MWh")
        print(f"RMSE: {rmse:.2f} €/MWh")

    best = min(results, key=results.get)

    print("\nMejor baseline según MAE:", best)

    # Guardar resultados para futuros gráficos.
    output = test[
        [
            "datetime_utc",
            "price_eur_mwh",
            "prediction_48h",
            "prediction_168h",
        ]
    ].copy()

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.to_parquet(
        OUTPUT_PATH,
        index=False,
    )

    print("\nPredicciones guardadas en:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
