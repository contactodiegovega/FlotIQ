
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]

FILE_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "omie"
    / "marginalpdbc_20261015.1"
)


def parse_omie(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"No existe el archivo: {path}")

    df = pd.read_csv(
        path,
        sep=";",
        skiprows=1,
        header=None,
        encoding="latin-1",
    )

    # Eliminar la columna vacía final
    df = df.iloc[:, :6].copy()

    df.columns = [
        "year",
        "month",
        "day",
        "period",
        "price_portugal_eur_mwh",
        "price_spain_eur_mwh",
    ]

    # Eliminar filas de cierre o control de OMIE que no representan registros de precios.
    df = df[
        df["year"].astype(str).str.fullmatch(r"\d{4}")
    ].copy()

    # Convertir las columnas a valores numéricos
    numeric_columns = [
        "year",
        "month",
        "day",
        "period",
        "price_portugal_eur_mwh",
        "price_spain_eur_mwh",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="raise"
        )

        # Asegurar que los campos de fecha y periodo sean enteros
    integer_columns = ["year", "month", "day", "period"]

    for column in integer_columns:
        df[column] = df[column].astype("int64")


    # Conversión de €/MWh a €/kWh
    df["price_spain_eur_kwh"] = (
        df["price_spain_eur_mwh"] / 1000
    )

    df["price_portugal_eur_kwh"] = (
        df["price_portugal_eur_mwh"] / 1000
    )

    # Crear fecha del mercado
    df["market_date"] = pd.to_datetime(
        df[["year", "month", "day"]]
    )

    # Validar valores nulos
    if df.isna().any().any():
        raise ValueError(
            "El fichero contiene valores nulos."
        )

    # Validar periodos duplicados
    if df.duplicated(
        subset=["market_date", "period"]
    ).any():
        raise ValueError(
            "Hay periodos duplicados para una misma fecha."
        )

        # Validar el número de periodos según el cambio horario
    import calendar

    market_date = df["market_date"].iloc[0].date()

    def last_sunday(year, month):
        last_day = calendar.monthrange(year, month)[1]
        last_date = pd.Timestamp(year, month, last_day)

        return (
            last_date - pd.Timedelta(
                days=(last_date.weekday() + 1) % 7
            )
        ).date()

    summer_change = last_sunday(market_date.year, 3)
    winter_change = last_sunday(market_date.year, 10)

    if market_date == summer_change:
        expected_periods = 92
    elif market_date == winter_change:
        expected_periods = 100
    else:
        expected_periods = 96

    if len(df) != expected_periods:
        raise ValueError(
            f"Se esperaban {expected_periods} periodos, "
            f"pero se encontraron {len(df)}."
        )

    if sorted(df["period"].tolist()) != list(
        range(1, expected_periods + 1)
    ):
        raise ValueError(
            "Los periodos no son consecutivos o están duplicados."
        )
    
    return df


if __name__ == "__main__":
    data = parse_omie(FILE_PATH)

    print("\n=== FlotIQ | Datos OMIE ===")
    print(f"Registros: {len(data)}")
    print(f"Periodos: {data['period'].nunique()}")

    print("\nPrimeras filas:")
    print(data.head().to_string(index=False))

    print("\nEstadísticas del precio español:")
    print(
        data["price_spain_eur_mwh"]
        .describe()
        .round(2)
    )

    print("\nValores nulos:")
    print(data.isna().sum().to_string())
