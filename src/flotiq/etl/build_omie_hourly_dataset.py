
from datetime import date, timedelta
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "omie_hourly"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

sys.path.insert(
    0,
    str(PROJECT_ROOT / "src" / "flotiq" / "ingestion")
)

from parse_omie_hourly import parse_omie_hourly


START_DATE = date(2023, 1, 1)
END_DATE = date(2025, 9, 30)

OUTPUT_FILE = OUTPUT_DIR / "omie_prices_2023_2025_hourly.parquet"


def build_dataset():
    frames = []
    current_date = START_DATE

    while current_date <= END_DATE:
        prefix = f"marginalpdbc_{current_date:%Y%m%d}"

        files = sorted(
            [
                path for path in RAW_DIR.glob(f"{prefix}.*")
                if path.suffix[1:].isdigit()
            ],
            key=lambda path: int(path.suffix[1:]),
            reverse=True,
        )

        if not files:
            raise FileNotFoundError(
                f"Falta el archivo del día {current_date}"
            )

        # Seleccionar la versión más alta disponible
        # localmente; pendiente de auditoría oficial.
        path = files[0]

        df = parse_omie_hourly(path)

        if not (df["market_date"].dt.date == current_date).all():
            raise ValueError(
                f"Fecha incorrecta en {path.name}"
            )

        df["source_file"] = path.name
        frames.append(df)

        current_date += timedelta(days=1)

    dataset = pd.concat(frames, ignore_index=True)

    dataset = dataset.sort_values(
        ["market_date", "period"]
    ).reset_index(drop=True)

    duplicates = dataset.duplicated(
        subset=["market_date", "period"]
    ).sum()

    if duplicates:
        raise ValueError(
            f"Se encontraron {duplicates} duplicados"
        )

    days = dataset["market_date"].nunique()

    if days != 1004:
        raise ValueError(
            f"Días incorrectos: {days}"
        )

    if len(dataset) != 24095:
        raise ValueError(
            f"Registros incorrectos: {len(dataset)}"
        )

    nulls = int(dataset.isna().sum().sum())

    if nulls:
        raise ValueError(
            f"Se encontraron {nulls} valores nulos"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset.to_parquet(
        OUTPUT_FILE,
        index=False
    )

    print("\n=== FlotIQ | HISTÓRICO HORARIO OMIE ===")
    print(f"Días: {days}")
    print(f"Registros: {len(dataset)}")
    print(f"Duplicados: {duplicates}")
    print(f"Valores nulos: {nulls}")

    print("\nPrecios España (€/MWh):")
    print(
        dataset["price_spain_eur_mwh"]
        .describe()
        .round(2)
    )

    print(f"\nArchivo generado: {OUTPUT_FILE}")


if __name__ == "__main__":
    build_dataset()
