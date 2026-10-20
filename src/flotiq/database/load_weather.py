
from pathlib import Path
import os

import pandas as pd
import psycopg
from dotenv import load_dotenv


# ==========================================
# CONFIGURACIÓN
# ==========================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

FILE_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "weather"
    / "madrid_weather_2023_2026.csv"
)

load_dotenv(PROJECT_ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")

COLUMNS = [
    "datetime",
    "temperature_c",
    "precipitation_mm",
    "wind_speed_kmh",
]


# ==========================================
# LECTURA Y VALIDACIÓN
# ==========================================

def prepare_data():
    print("\nLeyendo datos meteorológicos...")

    if not FILE_PATH.exists():
        raise FileNotFoundError(
            f"No existe el archivo: {FILE_PATH}"
        )

    df = pd.read_csv(FILE_PATH)

    missing = set(COLUMNS) - set(df.columns)

    if missing:
        raise ValueError(
            f"Faltan columnas: {sorted(missing)}"
        )

    df = df[COLUMNS].copy()

    df["datetime"] = pd.to_datetime(
        df["datetime"],
        errors="raise",
    )

    if df.isna().any().any():
        raise ValueError(
            "Hay valores nulos en los datos."
        )

    if df["datetime"].duplicated().any():
        raise ValueError(
            "Existen fechas y horas duplicadas."
        )

    if (df["precipitation_mm"] < 0).any():
        raise ValueError(
            "Se encontró precipitación negativa."
        )

    if (df["wind_speed_kmh"] < 0).any():
        raise ValueError(
            "Se encontró velocidad del viento negativa."
        )

    df = df.sort_values("datetime")

    print(f"Registros validados: {len(df):,}")
    print(f"Primera fecha: {df['datetime'].min()}")
    print(f"Última fecha: {df['datetime'].max()}")

    records = [
        (
            row.datetime.to_pydatetime(),
            float(row.temperature_c),
            float(row.precipitation_mm),
            float(row.wind_speed_kmh),
        )
        for row in df.itertuples(index=False)
    ]

    return records


# ==========================================
# IMPORTACIÓN A SUPABASE
# ==========================================

def load_weather(records):
    if not DATABASE_URL:
        raise ValueError(
            "No se encontró DATABASE_URL en .env"
        )

    print("\nConectando con Supabase...")

    with psycopg.connect(
        DATABASE_URL,
        connect_timeout=15,
        sslmode="require",
    ) as conn:

        with conn.cursor() as cursor:

            cursor.execute("""
                CREATE TEMP TABLE weather_import_stage (
                    datetime TIMESTAMP NOT NULL,
                    temperature_c DOUBLE PRECISION,
                    precipitation_mm DOUBLE PRECISION,
                    wind_speed_kmh DOUBLE PRECISION
                ) ON COMMIT DROP;
            """)

            with cursor.copy("""
                COPY weather_import_stage (
                    datetime,
                    temperature_c,
                    precipitation_mm,
                    wind_speed_kmh
                )
                FROM STDIN
            """) as copy:

                for record in records:
                    copy.write_row(record)

            cursor.execute("""
                INSERT INTO weather_hourly (
                    datetime,
                    temperature_c,
                    precipitation_mm,
                    wind_speed_kmh
                )
                SELECT
                    datetime,
                    temperature_c,
                    precipitation_mm,
                    wind_speed_kmh
                FROM weather_import_stage
                ON CONFLICT (datetime) DO NOTHING;
            """)

            inserted = cursor.rowcount

            cursor.execute("""
                SELECT COUNT(*)
                FROM weather_hourly;
            """)

            total = cursor.fetchone()[0]

    print("\nIMPORTACIÓN COMPLETADA")
    print(f"Registros nuevos: {inserted:,}")
    print(f"Total en Supabase: {total:,}")


# ==========================================
# EJECUCIÓN
# ==========================================

def main():
    print("=" * 50)
    print("FlotIQ | IMPORTACIÓN METEOROLOGÍA")
    print("=" * 50)

    try:
        records = prepare_data()
        load_weather(records)

    except (
        ValueError,
        FileNotFoundError,
        pd.errors.ParserError,
    ) as error:
        print(f"\nERROR DE VALIDACIÓN: {error}")

    except psycopg.Error as error:
        print("\nERROR EN POSTGRESQL")
        print(f"Tipo: {type(error).__name__}")


if __name__ == "__main__":
    main()
