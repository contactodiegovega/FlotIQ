
from datetime import date, timedelta
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "omie"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

INGESTION_DIR = PROJECT_ROOT / "src" / "flotiq" / "ingestion"
sys.path.insert(0, str(INGESTION_DIR))

from parse_omie import parse_omie


START_DATE = date(2025, 10, 1)
END_DATE = date(2026, 9, 30)

OUTPUT_FILE = PROCESSED_DIR / "omie_prices_2025_2026.parquet"


def build_dataset():
    frames = []
    missing_dates = []
    current_date = START_DATE

    while current_date <= END_DATE:
        prefix = f"marginalpdbc_{current_date:%Y%m%d}"

        files = sorted(
            (
                path for path in RAW_DIR.glob(f"{prefix}.*")
                if path.suffix[1:].isdigit()
            ),
            key=lambda path: int(path.suffix[1:]),
            reverse=True,
        )

        if not files:
            missing_dates.append(current_date.isoformat())
            current_date += timedelta(days=1)
            continue

        # Elegir la versión más alta disponible localmente.
        # La última versión oficial aún debe auditarse.
        file_path = files[0]

        df = parse_omie(file_path)

        if not (df["market_date"].dt.date == current_date).all():
            raise ValueError(
                f"Fecha incorrecta en {file_path.name}"
            )

        df["source_file"] = file_path.name

        frames.append(df)

        current_date += timedelta(days=1)

    if missing_dates:
        raise ValueError(
            f"Faltan días: {missing_dates}"
        )

    if not frames:
        raise ValueError("No se encontraron datos")

    dataset = pd.concat(
        frames,
        ignore_index=True
    )

    dataset = dataset.sort_values(
        ["market_date", "period"]
    ).reset_index(drop=True)

    # Comprobar duplicados
    duplicates = dataset.duplicated(
        subset=["market_date", "period"]
    ).sum()

    if duplicates:
        raise ValueError(
            f"Se encontraron {duplicates} registros duplicados"
        )

    # Comprobar cobertura
    days = dataset["market_date"].nunique()

    if days != 365:
        raise ValueError(
            f"Se esperaban 365 días, encontrados: {days}"
        )

    if len(dataset) != 35040:
        raise ValueError(
            f"Se esperaban 35040 registros, "
            f"encontrados: {len(dataset)}"
        )

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    dataset.to_parquet(
        OUTPUT_FILE,
        index=False
    )

    print("\n=== FlotIQ | DATASET OMIE ===")
    print(f"Días: {days}")
    print(f"Registros: {len(dataset)}")
    print(f"Duplicados: {duplicates}")
    print(f"Valores nulos: {dataset.isna().sum().sum()}")

    print("\nPrecio España (€/MWh):")
    print(
        dataset["price_spain_eur_mwh"]
        .describe()
        .round(2)
    )

    print(f"\nArchivo generado: {OUTPUT_FILE}")


if __name__ == "__main__":
    build_dataset()
