
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

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "madrid_traffic_hourly_202509.parquet"
)

CHUNK_SIZE = 100_000


def build_traffic_dataset():
    aggregated_chunks = []

    total_rows = 0
    valid_rows = 0

    print("\n=== FlotIQ | ETL TRÁFICO MADRID ===")

    with ZipFile(ZIP_PATH) as zip_file:
        with zip_file.open(CSV_NAME) as csv_file:

            chunks = pd.read_csv(
                csv_file,
                sep=";",
                chunksize=CHUNK_SIZE,
                encoding="utf-8-sig",
                usecols=[
                    "fecha",
                    "tipo_elem",
                    "intensidad",
                    "vmed",
                    "error",
                ],
            )

            for number, chunk in enumerate(chunks, start=1):
                total_rows += len(chunk)

                # Conservar observaciones sin error señalado.
                chunk = chunk[
                    chunk["error"].astype("string")
                    .str.strip().eq("N").fillna(False)
                ].copy()

                chunk["fecha"] = pd.to_datetime(
                    chunk["fecha"],
                    errors="coerce",
                )

                chunk["intensidad"] = pd.to_numeric(
                    chunk["intensidad"],
                    errors="coerce",
                )

                chunk["vmed"] = pd.to_numeric(
                    chunk["vmed"],
                    errors="coerce",
                )

                chunk = chunk.dropna(
                    subset=["fecha", "tipo_elem", "intensidad"]
                )

                # Excluir intensidades negativas.
                chunk = chunk[
                    chunk["intensidad"] >= 0
                ].copy()

                valid_rows += len(chunk)

                # Agrupar por hora y tipo de sensor.
                chunk["hour"] = chunk["fecha"].dt.floor("h")

                grouped = chunk.groupby(
                    ["hour", "tipo_elem"]
                ).agg(
                    intensity_sum=("intensidad", "sum"),
                    intensity_count=("intensidad", "count"),
                    speed_sum=("vmed", "sum"),
                    speed_count=("vmed", "count"),
                ).reset_index()

                aggregated_chunks.append(grouped)

                if number % 20 == 0:
                    print(
                        f"Bloques: {number} | "
                        f"Filas leídas: {total_rows:,}"
                    )

    combined = pd.concat(
        aggregated_chunks,
        ignore_index=True,
    )

    dataset = combined.groupby(
        ["hour", "tipo_elem"],
        as_index=False,
    ).agg(
        intensity_sum=("intensity_sum", "sum"),
        intensity_count=("intensity_count", "sum"),
        speed_sum=("speed_sum", "sum"),
        speed_count=("speed_count", "sum"),
    )

    dataset["mean_intensity"] = (
        dataset["intensity_sum"]
        / dataset["intensity_count"]
    )

    dataset["mean_speed"] = (
        dataset["speed_sum"]
        / dataset["speed_count"].replace(0, float("nan"))
    )

    dataset["day_of_week"] = (
        dataset["hour"].dt.dayofweek
    )

    dataset["hour_of_day"] = (
        dataset["hour"].dt.hour
    )

    dataset["is_weekend"] = (
        dataset["day_of_week"] >= 5
    )

    dataset = dataset[
        [
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
    ].sort_values(["hour", "tipo_elem"])

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataset.to_parquet(
        OUTPUT_PATH,
        index=False,
    )

    print("\n=== RESULTADO ETL ===")
    print(f"Filas originales: {total_rows:,}")
    print(f"Filas conservadas: {valid_rows:,}")
    print(f"Filas agregadas: {len(dataset):,}")
    print(f"Horas diferentes: {dataset['hour'].nunique()}")
    print(f"Categorías: {dataset['tipo_elem'].unique().tolist()}")

    print("\nValores nulos:")
    print(dataset.isna().sum().to_string())

    print(f"\nArchivo generado: {OUTPUT_PATH}")


if __name__ == "__main__":
    build_traffic_dataset()
