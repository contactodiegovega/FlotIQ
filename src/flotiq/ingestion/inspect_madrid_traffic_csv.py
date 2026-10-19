
from pathlib import Path
from zipfile import ZipFile
import io

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


def inspect_traffic_csv():
    print("\n=== FlotIQ | INSPECCIÓN CSV DE TRÁFICO ===")

    with ZipFile(ZIP_PATH) as zip_file:
        with zip_file.open(CSV_NAME) as csv_file:
            # Leer solo una pequeña muestra del CSV.
            sample = csv_file.read(20000)

    # Detectar de forma sencilla el separador.
    first_line = sample.decode(
        "utf-8-sig", errors="replace"
    ).splitlines()[0]

    separators = [";", ",", "\t"]

    separator = max(
        separators,
        key=lambda sep: first_line.count(sep)
    )

    print(f"Separador detectado: {repr(separator)}")
    print(f"Cabecera original: {first_line[:300]}")

    # Leer únicamente las primeras 10 filas.
    df = pd.read_csv(
        io.BytesIO(sample),
        sep=separator,
        nrows=10,
        encoding="utf-8-sig",
        on_bad_lines="skip",
    )

    print("\nColumnas:")
    for column in df.columns:
        print(f"- {column}")

    print("\nPrimeras filas:")
    print(df.head().to_string(index=False))

    print("\nTipos de datos:")
    print(df.dtypes)


if __name__ == "__main__":
    inspect_traffic_csv()
