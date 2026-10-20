
from pathlib import Path
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
import os

import pandas as pd
import psycopg
from dotenv import load_dotenv


# ==========================================
# CONFIGURACIÓN
# ==========================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "processed"

load_dotenv(PROJECT_ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL")

MADRID = ZoneInfo("Europe/Madrid")
UTC = timezone.utc

FILES = [
    ("omie_prices_2023_2025_hourly.parquet", 60),
    ("omie_prices_2025_2026.parquet", 15),
]


# ==========================================
# PREPARAR Y VALIDAR LOS DATOS
# ==========================================

def prepare_prices():
    all_records = []
    seen_timestamps = set()

    for filename, interval_minutes in FILES:
        path = DATA_DIR / filename

        if not path.exists():
            raise FileNotFoundError(
                f"No se encuentra: {filename}"
            )

        df = pd.read_parquet(
            path,
            columns=[
                "market_date",
                "period",
                "price_spain_eur_mwh",
            ],
        )

        if df.isna().any().any():
            raise ValueError(
                f"Hay valores nulos en {filename}"
            )

        print(f"\nProcesando: {filename}")
        print(f"  Registros: {len(df):,}")

        file_count = 0

        for market_date, group in df.groupby(
            "market_date", sort=True
        ):
            day = pd.Timestamp(market_date).date()

            # Medianoches locales convertidas a UTC.
            # Esto permite gestionar días de 23 y 25 h.
            start_local = datetime.combine(
                day, time.min, tzinfo=MADRID
            )

            end_local = datetime.combine(
                day + timedelta(days=1),
                time.min,
                tzinfo=MADRID,
            )

            start_utc = start_local.astimezone(UTC)
            end_utc = end_local.astimezone(UTC)

            minutes_in_day = int(
                (end_utc - start_utc).total_seconds()
                / 60
            )

            expected_periods = (
                minutes_in_day // interval_minutes
            )

            if len(group) != expected_periods:
                raise ValueError(
                    f"{day}: se esperaban "
                    f"{expected_periods} periodos, "
                    f"pero hay {len(group)}."
                )

            group = group.sort_values("period")

            expected_numbers = list(
                range(1, expected_periods + 1)
            )

            actual_numbers = group[
                "period"
            ].astype(int).tolist()

            if actual_numbers != expected_numbers:
                raise ValueError(
                    f"Numeración incorrecta: {day}"
                )

            for period, price in group[
                ["period", "price_spain_eur_mwh"]
            ].itertuples(index=False, name=None):

                timestamp_utc = (
                    start_utc
                    + timedelta(
                        minutes=(
                            int(period) - 1
                        ) * interval_minutes
                    )
                )

                if timestamp_utc in seen_timestamps:
                    raise ValueError(
                        "Timestamp duplicado: "
                        f"{timestamp_utc}"
                    )

                seen_timestamps.add(timestamp_utc)

                record = (
                    timestamp_utc,
                    "OMIE",
                    Decimal(str(price)),
                    f"OMIE_{interval_minutes}min",
                )

                all_records.append(record)
                file_count += 1

        print(f"  Validados: {file_count:,}")

    print("\nTotal preparado:", f"{len(all_records):,}")

    return all_records


# ==========================================
# CARGAR EN POSTGRESQL
# ==========================================

def load_prices(records):
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

            # Tabla temporal para cargar rápidamente
            # los registros en una única transacción.
            cursor.execute("""
                CREATE TEMP TABLE omie_import_stage (
                    timestamp_utc TIMESTAMPTZ NOT NULL,
                    market VARCHAR(30) NOT NULL,
                    price_eur_mwh NUMERIC(12,4) NOT NULL,
                    source VARCHAR(100) NOT NULL
                ) ON COMMIT DROP;
            """)

            with cursor.copy("""
                COPY omie_import_stage (
                    timestamp_utc,
                    market,
                    price_eur_mwh,
                    source
                )
                FROM STDIN
            """) as copy:

                for record in records:
                    copy.write_row(record)

            cursor.execute("""
                INSERT INTO electricity_prices (
                    timestamp_utc,
                    market,
                    price_eur_mwh,
                    source
                )
                SELECT
                    timestamp_utc,
                    market,
                    price_eur_mwh,
                    source
                FROM omie_import_stage
                ON CONFLICT (
                    timestamp_utc, market
                ) DO NOTHING;
            """)

            inserted = cursor.rowcount

            cursor.execute("""
                SELECT COUNT(*)
                FROM electricity_prices
                WHERE market = 'OMIE';
            """)

            total = cursor.fetchone()[0]

    print("\nIMPORTACIÓN COMPLETADA")
    print(f"Registros nuevos: {inserted:,}")
    print(f"Total OMIE en Supabase: {total:,}")


# ==========================================
# EJECUCIÓN
# ==========================================

def main():
    print("=" * 50)
    print("FlotIQ | IMPORTACIÓN DE PRECIOS OMIE")
    print("=" * 50)

    try:
        records = prepare_prices()
        load_prices(records)

    except (ValueError, FileNotFoundError) as error:
        print(f"\nERROR DE VALIDACIÓN: {error}")

    except psycopg.Error as error:
        print("\nERROR EN POSTGRESQL")
        print(f"Tipo: {type(error).__name__}")


if __name__ == "__main__":
    main()
