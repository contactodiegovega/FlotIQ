
# FLOTIQ | PREDICCION DIARIA DE PRECIOS CON MACHINE LEARNING

import argparse
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RUTA_MODELO = (
    PROJECT_ROOT / "models" / "modelo_precio_hgb.joblib"
)

RUTA_PRECIOS = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "omie_precios_actualizados.parquet"
)

RUTA_RESULTADOS = (
    PROJECT_ROOT / "data" / "processed"
)

ZONA = "Europe/Madrid"

VARIABLES_MODELO = [
    "hour_sin",
    "hour_cos",
    "month_sin",
    "month_cos",
    "day_of_week",
    "is_weekend",
    "price_lag_72h",
    "price_lag_168h",
]


def predecir_precios_dia(fecha: str) -> pd.DataFrame:
    dia = date.fromisoformat(fecha)

    if not RUTA_MODELO.exists():
        raise FileNotFoundError(
            f"No se encuentra el modelo: {RUTA_MODELO}"
        )

    if not RUTA_PRECIOS.exists():
        raise FileNotFoundError(
            f"No se encuentran los precios: {RUTA_PRECIOS}"
        )

    modelo = joblib.load(RUTA_MODELO)

    if not hasattr(modelo, "predict"):
        raise TypeError(
            "El archivo cargado no contiene un predictor válido."
        )

    if hasattr(modelo, "feature_names_in_"):
        variables_guardadas = list(
            modelo.feature_names_in_
        )

        if variables_guardadas != VARIABLES_MODELO:
            raise ValueError(
                "Las variables del modelo no coinciden "
                "con las esperadas."
            )

    precios = pd.read_parquet(RUTA_PRECIOS)

    columnas_obligatorias = {
        "datetime_utc",
        "price_eur_mwh",
    }

    if not columnas_obligatorias.issubset(
        precios.columns
    ):
        raise ValueError(
            "El fichero OMIE no tiene las columnas necesarias."
        )

    precios["datetime_utc"] = pd.to_datetime(
        precios["datetime_utc"],
        utc=True,
    )

    precios["price_eur_mwh"] = pd.to_numeric(
        precios["price_eur_mwh"],
        errors="coerce",
    )

    precios = (
        precios
        .dropna(subset=["datetime_utc", "price_eur_mwh"])
        .sort_values("datetime_utc")
    )

    if precios["datetime_utc"].duplicated().any():
        raise ValueError(
            "El histórico contiene horas UTC duplicadas."
        )

    precios = precios.set_index("datetime_utc")

    inicio = pd.Timestamp(dia).tz_localize(ZONA)

    fin = pd.Timestamp(
        dia + timedelta(days=1)
    ).tz_localize(ZONA)

    horas = pd.date_range(
        inicio,
        fin,
        freq="h",
        inclusive="left",
    )

    # Los lags del modelo representan 72 y 168
    # observaciones HORARIAS anteriores.
    # Se calculan en UTC para mantener la
    # continuidad incluso en cambios de horario.
    horas_utc = horas.tz_convert("UTC")

    lag_72 = horas_utc - pd.Timedelta(hours=72)
    lag_168 = horas_utc - pd.Timedelta(hours=168)

    precios_72 = precios["price_eur_mwh"].reindex(
        lag_72
    )

    precios_168 = precios["price_eur_mwh"].reindex(
        lag_168
    )

    if (
        precios_72.isna().any()
        or precios_168.isna().any()
    ):
        faltantes = []

        for nombre, origen, valores in [
            ("72h", lag_72, precios_72),
            ("168h", lag_168, precios_168),
        ]:
            for instante, vacio in zip(
                origen, valores.isna()
            ):
                if vacio:
                    faltantes.append(
                        f"{nombre}: {instante.isoformat()}"
                    )

        raise ValueError(
            "Faltan precios históricos necesarios "
            "para predecir este día:\n"
            + "\n".join(faltantes[:12])
        )

    # Variables temporales.
    # IMPORTANTE: estas fórmulas deben coincidir
    # exactamente con las del notebook de entrenamiento.
    horas_locales = horas.hour
    meses = horas.month
    dias_semana = horas.dayofweek

    variables = pd.DataFrame({
        "hour_sin": np.sin(
            2 * np.pi * horas_locales / 24
        ),
        "hour_cos": np.cos(
            2 * np.pi * horas_locales / 24
        ),
        "month_sin": np.sin(
            2 * np.pi * meses / 12
        ),
        "month_cos": np.cos(
            2 * np.pi * meses / 12
        ),
        "day_of_week": dias_semana,
        "is_weekend": (
            dias_semana >= 5
        ).astype(int),
        "price_lag_72h": precios_72.to_numpy(),
        "price_lag_168h": precios_168.to_numpy(),
    })

    variables = variables[VARIABLES_MODELO]

    predicciones = modelo.predict(variables)

    if not np.isfinite(predicciones).all():
        raise ValueError(
            "El modelo ha generado predicciones no válidas."
        )

    resultado = pd.DataFrame({
        "datetime_utc": horas_utc,
        "fecha_local": horas,
        "precio_predicho_eur_mwh": predicciones,
        "modelo": "HistGradientBoostingRegressor",
        "tipo_datos": "prediccion_ml",
    })

    print("\nFLOTIQ | PREDICCION DIARIA CON ML")
    print("-" * 45)
    print("Día:", fecha)
    print("Modelo:", type(modelo).__name__)
    print("Horas previstas:", len(resultado))
    print(
        "Precio medio predicho:",
        round(
            resultado["precio_predicho_eur_mwh"].mean(),
            2,
        ),
        "€/MWh",
    )

    print("\nPRIMERAS PREDICCIONES:")
    print(
        resultado[
            ["fecha_local", "precio_predicho_eur_mwh"]
        ].head(8).to_string(index=False)
    )

    return resultado


def guardar_prediccion(
    fecha: str,
    resultado: pd.DataFrame,
):
    RUTA_RESULTADOS.mkdir(
        parents=True,
        exist_ok=True,
    )

    ruta = (
        RUTA_RESULTADOS
        / f"prediccion_ml_{fecha}.parquet"
    )

    resultado.to_parquet(
        ruta,
        index=False,
    )

    print("\nPredicción guardada en:")
    print(ruta)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--fecha",
        required=True,
        help="Día que queremos predecir: AAAA-MM-DD",
    )

    argumentos = parser.parse_args()

    prediccion = predecir_precios_dia(
        argumentos.fecha
    )

    guardar_prediccion(
        argumentos.fecha,
        prediccion,
    )
