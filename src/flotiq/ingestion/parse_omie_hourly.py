
from pathlib import Path
from datetime import date
import calendar

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]

FILE_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "omie_hourly"
    / "marginalpdbc_20240115.1"
)


def last_sunday(year, month):
    last_day = calendar.monthrange(year, month)[1]
    last_date = date(year, month, last_day)

    return date.fromordinal(
        last_date.toordinal()
        - (last_date.weekday() + 1) % 7
    )


def parse_omie_hourly(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"No existe: {path}")

    df = pd.read_csv(
        path,
        sep=";",
        skiprows=1,
        header=None,
        encoding="latin-1",
        dtype=str,
    )

    # Descartar la columna vacía final.
    df = df.iloc[:, :6].copy()

    df.columns = [
        "year",
        "month",
        "day",
        "period",
        "price_portugal_eur_mwh",
        "price_spain_eur_mwh",
    ]

    # Separar las filas de cierre del archivo.
    df = df[
        df["year"].str.fullmatch(r"\d{4}", na=False)
    ].copy()

    if df.empty:
        raise ValueError("No se encontraron precios horarios")

    # Convertir columnas numéricas.
    for column in df.columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="raise",
        )

    # Año, mes, día y periodo deben ser enteros.
    for column in ["year", "month", "day", "period"]:
        df[column] = df[column].astype("int64")

    # Construir la fecha.
    df["market_date"] = pd.to_datetime(
        df[["year", "month", "day"]]
    )

    if df["market_date"].nunique() != 1:
        raise ValueError("El archivo contiene varias fechas")

    market_date = df["market_date"].iloc[0].date()

    # Validar el número de periodos horarios.
    if market_date == last_sunday(market_date.year, 3):
        expected_periods = 23
    elif market_date == last_sunday(market_date.year, 10):
        expected_periods = 25
    else:
        expected_periods = 24

    if len(df) != expected_periods:
        raise ValueError(
            f"Se esperaban {expected_periods} periodos, "
            f"pero se encontraron {len(df)}"
        )

    # Comprobar que los periodos son consecutivos.
    if sorted(df["period"].tolist()) != list(
        range(1, expected_periods + 1)
    ):
        raise ValueError("Periodos duplicados o incompletos")

    # Conversión de unidades.
    df["price_spain_eur_kwh"] = (
        df["price_spain_eur_mwh"] / 1000
    )

    df["price_portugal_eur_kwh"] = (
        df["price_portugal_eur_mwh"] / 1000
    )

    df["interval_minutes"] = 60

    if df.isna().any().any():
        raise ValueError("Se encontraron valores nulos")

    return df.reset_index(drop=True)


if __name__ == "__main__":
    data = parse_omie_hourly(FILE_PATH)

    print("\n=== FlotIQ | OMIE HORARIO ===")
    print(f"Fecha: {data['market_date'].iloc[0].date()}")
    print(f"Registros: {len(data)}")
    print(f"Periodos: {data['period'].nunique()}")

    print("\nPrimeras filas:")
    print(data.head().to_string(index=False))

    print("\nPrecios España (€/MWh):")
    print(
        data["price_spain_eur_mwh"]
        .describe()
        .round(2)
    )

    print("\nValores nulos:")
    print(data.isna().sum().sum())
