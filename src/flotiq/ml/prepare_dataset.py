
from pathlib import Path
import os

import numpy as np
import pandas as pd
import psycopg
from dotenv import load_dotenv


# ==============================================
# CONFIGURACIÓN
# ==============================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "omie_ml_hourly.parquet"
)

load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

EXPECTED_INTERVALS = {
    "OMIE_60min": 1,
    "OMIE_15min": 4,
}


# ==============================================
# LEER PRECIOS DESDE SUPABASE
# ==============================================

def load_prices():
    if not DATABASE_URL:
        raise ValueError(
            "No se encuentra DATABASE_URL en .env"
        )

    print("\nConectando con Supabase...")

    with psycopg.connect(
        DATABASE_URL,
        connect_timeout=15,
        sslmode="require",
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    timestamp_utc,
                    price_eur_mwh,
                    source
                FROM electricity_prices
                WHERE market = 'OMIE'
                ORDER BY timestamp_utc;
            """)

            records = cursor.fetchall()

    df = pd.DataFrame(
        records,
        columns=[
            "datetime",
            "price_eur_mwh",
            "source",
        ],
    )

    if df.empty:
        raise ValueError(
            "No se encontraron precios de OMIE."
        )

    df["datetime"] = pd.to_datetime(
        df["datetime"],
        utc=True,
    )

    df["price_eur_mwh"] = pd.to_numeric(
        df["price_eur_mwh"]
    )

    print(f"Precios recuperados: {len(df):,}")

    return df


# ==============================================
# UNIFICAR A FRECUENCIA HORARIA
# ==============================================

def create_hourly_prices(df):
    df = df.copy()

    # Agrupamos por horas reales en UTC.
    # No reconstruimos fechas usando period.
    df["hour_utc"] = df["datetime"].dt.floor("h")

    hourly = (
        df.groupby(
            ["hour_utc", "source"],
            as_index=False,
        )
        .agg(
            price_eur_mwh=(
                "price_eur_mwh", "mean"
            ),
            intervals=("price_eur_mwh", "size"),
        )
    )

    # Comprobar que las horas de 15 minutos
    # contienen exactamente cuatro intervalos.
    for source, expected in EXPECTED_INTERVALS.items():
        subset = hourly[hourly["source"] == source]

        if subset.empty:
            raise ValueError(
                f"No se encontraron datos: {source}"
            )

        invalid = subset[
            subset["intervals"] != expected
        ]

        if not invalid.empty:
            raise ValueError(
                f"{source}: {len(invalid)} horas "
                f"con intervalos incompletos."
            )

        print(
            f"{source}: {len(subset):,} horas completas"
        )

    # Comprobar que no se solapan las dos fuentes.
    if hourly["hour_utc"].duplicated().any():
        raise ValueError(
            "Hay horas duplicadas entre las fuentes."
        )

    hourly = (
        hourly[
            ["hour_utc", "price_eur_mwh"]
        ]
        .rename(
            columns={"hour_utc": "datetime_utc"}
        )
        .sort_values("datetime_utc")
        .reset_index(drop=True)
    )

    # Crear calendario horario continuo.
    # Las horas que falten quedan como NaN.
    full_index = pd.date_range(
        start=hourly["datetime_utc"].min(),
        end=hourly["datetime_utc"].max(),
        freq="h",
        tz="UTC",
    )

    hourly = (
        hourly.set_index("datetime_utc")
        .reindex(full_index)
        .rename_axis("datetime_utc")
        .reset_index()
    )

    missing = hourly["price_eur_mwh"].isna().sum()

    print(f"\nHoras del calendario: {len(hourly):,}")
    print(f"Horas sin precio: {missing:,}")

    if missing:
        print(
            "AVISO: las horas sin precio se "
            "mantienen como nulas."
        )

    return hourly


# ==============================================
# INGENIERÍA DE VARIABLES
# ==============================================

def create_features(df):
    df = df.copy()

    # Convertimos a hora local solo para
    # extraer características del calendario.
    local_time = df["datetime_utc"].dt.tz_convert(
        "Europe/Madrid"
    )

    df["hour"] = local_time.dt.hour
    df["day_of_week"] = local_time.dt.dayofweek
    df["month"] = local_time.dt.month

    df["is_weekend"] = (
        df["day_of_week"] >= 5
    ).astype(int)

    # Variables cíclicas
    df["hour_sin"] = np.sin(
        2 * np.pi * df["hour"] / 24
    )

    df["hour_cos"] = np.cos(
        2 * np.pi * df["hour"] / 24
    )

    df["month_sin"] = np.sin(
        2 * np.pi * df["month"] / 12
    )

    df["month_cos"] = np.cos(
        2 * np.pi * df["month"] / 12
    )

    # Preparación conservadora para predicciones
    # de hasta 48 horas de antelación.
    #
    # No utilizamos el precio de la hora anterior
    # al instante que queremos predecir.
    df["price_lag_48h"] = (
        df["price_eur_mwh"].shift(48)
    )

    df["price_lag_72h"] = (
        df["price_eur_mwh"].shift(72)
    )

    df["price_lag_168h"] = (
        df["price_eur_mwh"].shift(168)
    )

    historical_prices = (
        df["price_eur_mwh"].shift(48)
    )

    df["price_rolling_mean_24h"] = (
        historical_prices.rolling(24).mean()
    )

    df["price_rolling_mean_168h"] = (
        historical_prices.rolling(168).mean()
    )

    # Se eliminan filas sin precio objetivo
    # o con variables históricas incompletas.
    before = len(df)

    df = df.dropna().reset_index(drop=True)

    print(
        f"Filas descartadas por histórico "
        f"incompleto: {before - len(df):,}"
    )

    return df


# ==============================================
# EJECUCIÓN
# ==============================================

def main():
    print("=" * 55)
    print("FlotIQ | DATASET MACHINE LEARNING OMIE")
    print("=" * 55)

    try:
        prices = load_prices()

        hourly = create_hourly_prices(prices)

        dataset = create_features(hourly)

        if dataset.empty:
            raise ValueError(
                "El dataset final está vacío."
            )

        if dataset["datetime_utc"].duplicated().any():
            raise ValueError(
                "Hay fechas UTC duplicadas."
            )

        OUTPUT_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        dataset.to_parquet(
            OUTPUT_PATH,
            index=False,
        )

        print("\nDATASET GENERADO CORRECTAMENTE")
        print(f"Filas finales: {len(dataset):,}")
        print(f"Columnas: {len(dataset.columns)}")

        print("\nPrimeras 3 filas:")
        print(dataset.head(3).to_string(index=False))

        print(f"\nArchivo: {OUTPUT_PATH}")

    except (ValueError, OSError) as error:
        print(f"\nERROR: {error}")

    except psycopg.Error as error:
        print("\nERROR DE CONEXIÓN CON SUPABASE")
        print(f"Tipo: {type(error).__name__}")


if __name__ == "__main__":
    main()
