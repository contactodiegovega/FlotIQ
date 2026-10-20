
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
    / "processed"
    / "madrid_traffic_hourly_202509.parquet"
)

load_dotenv(PROJECT_ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")

COLUMNS = [
    "hour",
    "tipo_elem",
    "mean_intensity",
    "mean_speed",
    "intensity_count",
    "speed_count",
    "day_of_week",
    "hour_of_day",
    "is_weekend",
]


# ==========================================
# LECTURA Y VALIDACIÓN
# ==========================================

def prepare_data():
    print("\nLeyendo datos de tráfico...")

    if not FILE_PATH.exists():
        raise FileNotFoundError(
            f"No se encuentra: {FILE_PATH.name}"
        )

    df = pd.read_parquet(FILE_PATH)

    missing = set(COLUMNS) - set(df.columns)

    if missing:
        raise ValueError(
            f"Faltan columnas: {sorted(missing)}"
        )

    df = df[COLUMNS].copy()

    if df.isna().any().any():
        raise ValueError(
            "Se encontraron valores nulos."
        )

    df["hour"] = pd.to_datetime(df["hour"])

    if df.duplicated(["hour", "tipo_elem"]).any():
        raise ValueError(
            "Hay horas y categorías duplicadas."
        )

    if not df["hour_of_day"].between(0, 23).all():
        raise ValueError(
            "Se encontraron horas inválidas."
        )

    if not df["day_of_week"].between(0, 6).all():
        raise ValueError(
            "Se encontraron días de semana inválidos."
        )

    if (
        (df["intensity_count"] < 0).any()
        or (df["speed_count"] < 0).any()
    ):
        raise ValueError(
            "Se encontraron recuentos negativos."
        )

    # Comprobación de columnas derivadas
    if not (
        df["hour"].dt.hour == df["hour_of_day"]
    ).all():
        raise ValueError(
            "La hora no coincide con hour_of_day."
        )

    if not (
        df["hour"].dt.dayofweek == df["day_of_week"]
    ).all():
        raise ValueError(
            "El día no coincide con day_of_week."
        )

    if not (
        df["day_of_week"].ge(5) == df["is_weekend"]
    ).all():
        raise ValueError(
            "Hay incoherencias en is_weekend."
        )

    print(f"Registros validados: {len(df):,}")
    print("Categorías:", sorted(df["tipo_elem"].unique()))

    records = []

    for row in df.itertuples(index=False, name=None):
        records.append((
            row[0].to_pydatetime(),
            str(row[1]),
            float(row[2]),
            float(row[3]),
            int(row[4]),
            int(row[5]),
            int(row[6]),
            int(row[7]),
            bool(row[8]),
        ))

    return records


# ==========================================
# IMPORTACIÓN A POSTGRESQL
# ==========================================

def load_traffic(records):
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
                CREATE TEMP TABLE traffic_import_stage (
                    hour TIMESTAMP,
                    tipo_elem VARCHAR(10),
                    mean_intensity DOUBLE PRECISION,
                    mean_speed DOUBLE PRECISION,
                    intensity_count INTEGER,
                    speed_count INTEGER,
                    day_of_week INTEGER,
                    hour_of_day INTEGER,
                    is_weekend BOOLEAN
                ) ON COMMIT DROP;
            """)

            with cursor.copy("""
                COPY traffic_import_stage (
                    hour,
                    tipo_elem,
                    mean_intensity,
                    mean_speed,
                    intensity_count,
                    speed_count,
                    day_of_week,
                    hour_of_day,
                    is_weekend
                )
                FROM STDIN
            """) as copy:

                for record in records:
                    copy.write_row(record)

            cursor.execute("""
                INSERT INTO traffic_hourly (
                    hour,
                    tipo_elem,
                    mean_intensity,
                    mean_speed,
                    intensity_count,
                    speed_count,
                    day_of_week,
                    hour_of_day,
                    is_weekend
                )
                SELECT
                    hour,
                    tipo_elem,
                    mean_intensity,
                    mean_speed,
                    intensity_count,
                    speed_count,
                    day_of_week,
                    hour_of_day,
                    is_weekend
                FROM traffic_import_stage
                ON CONFLICT (hour, tipo_elem)
                DO NOTHING;
            """)

            inserted = cursor.rowcount

            cursor.execute("""
                SELECT COUNT(*)
                FROM traffic_hourly;
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
    print("FlotIQ | IMPORTACIÓN TRÁFICO MADRID")
    print("=" * 50)

    try:
        records = prepare_data()
        load_traffic(records)

    except (ValueError, FileNotFoundError) as error:
        print(f"\nERROR DE VALIDACIÓN: {error}")

    except psycopg.Error as error:
        print("\nERROR EN POSTGRESQL")
        print(f"Tipo: {type(error).__name__}")


if __name__ == "__main__":
    main()
