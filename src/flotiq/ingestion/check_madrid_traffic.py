
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]

ZIP_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "madrid_traffic"
    / "208627-130-transporte-ptomedida-historico-zip.zip"
)

CSV_NAME = "09-2025.csv"
CHUNK_SIZE = 100_000


def audit_traffic():
    total_rows = 0
    sensors = set()

    error_counts = Counter()
    sensor_types = Counter()
    integration_counts = Counter()
    null_counts = Counter()

    min_date = None
    max_date = None

    print("\n=== FlotIQ | AUDITORÍA TRÁFICO MADRID ===")

    with ZipFile(ZIP_PATH) as zip_file:
        with zip_file.open(CSV_NAME) as csv_file:

            chunks = pd.read_csv(
                csv_file,
                sep=";",
                chunksize=CHUNK_SIZE,
                encoding="utf-8-sig",
                low_memory=False,
            )

            for number, chunk in enumerate(chunks, start=1):
                total_rows += len(chunk)

                sensors.update(
                    chunk["id"].dropna().unique().tolist()
                )

                error_counts.update(
                    chunk["error"]
                    .fillna("NULL")
                    .astype(str)
                    .value_counts()
                    .to_dict()
                )

                sensor_types.update(
                    chunk["tipo_elem"]
                    .fillna("NULL")
                    .astype(str)
                    .value_counts()
                    .to_dict()
                )

                integration_counts.update(
                    chunk["periodo_integracion"]
                    .fillna("NULL")
                    .astype(str)
                    .value_counts()
                    .to_dict()
                )

                null_counts.update(
                    chunk.isna().sum().to_dict()
                )

                dates = pd.to_datetime(
                    chunk["fecha"],
                    errors="coerce",
                )

                null_counts["fecha_invalida"] += (
                    dates.isna().sum()
                )

                valid_dates = dates.dropna()

                if not valid_dates.empty:
                    chunk_min = valid_dates.min()
                    chunk_max = valid_dates.max()

                    min_date = (
                        chunk_min if min_date is None
                        else min(min_date, chunk_min)
                    )

                    max_date = (
                        chunk_max if max_date is None
                        else max(max_date, chunk_max)
                    )

                if number % 10 == 0:
                    print(
                        f"Bloques: {number} | "
                        f"Registros: {total_rows:,}"
                    )

    print("\n=== RESULTADOS FINALES ===")
    print(f"Registros totales: {total_rows:,}")
    print(f"Sensores únicos: {len(sensors):,}")
    print(f"Fecha inicial: {min_date}")
    print(f"Fecha final: {max_date}")

    print("\nValores de error:")
    print(dict(error_counts))

    print("\nTipos de sensores:")
    print(dict(sensor_types))

    print("\nPeriodos de integración:")
    print(dict(integration_counts))

    print("\nValores nulos por columna:")
    print(dict(null_counts))

    print("\nAuditoría finalizada.")


if __name__ == "__main__":
    audit_traffic()
