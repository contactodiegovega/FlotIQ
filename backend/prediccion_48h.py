# FlotIQ: emitir precios eléctricos para los dos próximos días naturales

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import numpy as np
import pandas as pd

TZ = "Europe/Madrid"
FEATURES = [
    "hour_sin",
    "hour_cos",
    "month_sin",
    "month_cos",
    "day_of_week",
    "is_weekend",
    "price_lag_72h",
    "price_lag_168h",
]


def find_root() -> Path:
    # Soporta ejecución desde scripts/ o desde la raíz del proyecto.
    for base in (
        Path(__file__).resolve().parent,
        *Path(__file__).resolve().parents,
        Path.cwd(),
    ):
        if (base / "data" / "processed").is_dir() and (base / "models").is_dir():
            return base

    raise FileNotFoundError(
        "No encuentro data/processed y models. "
        "Copia este archivo a FLOTIQ/scripts/."
    )


def build_calendar_features(
    times_utc: pd.DatetimeIndex,
    zone: str,
) -> pd.DataFrame:
    times = times_utc.tz_convert(zone)

    hour = times.hour.to_numpy(dtype=float)
    month = times.month.to_numpy(dtype=float)
    weekday = times.dayofweek.to_numpy()

    return pd.DataFrame({
        "hour_sin": np.sin(2 * np.pi * hour / 24),
        "hour_cos": np.cos(2 * np.pi * hour / 24),
        "month_sin": np.sin(2 * np.pi * month / 12),
        "month_cos": np.cos(2 * np.pi * month / 12),
        "day_of_week": weekday,
        "is_weekend": (weekday >= 5).astype(int),
    })


def determine_calendar_zone(training_path: Path) -> str:
    """Comprueba si las variables temporales originales se calcularon
    en UTC o en hora local.
    """

    training = pd.read_parquet(training_path)

    cols = ["datetime_utc", *FEATURES[:6]]

    missing = set(cols).difference(training.columns)

    if missing:
        raise ValueError(
            f"Faltan columnas en dataset de entrenamiento: {sorted(missing)}"
        )

    training = (
        training[cols]
        .dropna()
        .iloc[-1000:]
        .copy()
        .reset_index(drop=True)
    )

    if len(training) < 24:
        raise ValueError(
            "No hay suficientes filas para verificar las variables temporales."
        )

    idx = pd.DatetimeIndex(
        pd.to_datetime(training["datetime_utc"], utc=True)
    )

    target = training[FEATURES[:6]].astype(float).to_numpy()

    discrepancies = {}

    for name, zone in (("UTC", "UTC"), (TZ, TZ)):
        candidate = build_calendar_features(
            idx, zone
        )[FEATURES[:6]].to_numpy(dtype=float)

        discrepancies[name] = float(
            np.max(np.abs(target - candidate))
        )

    chosen = min(discrepancies, key=discrepancies.get)

    if discrepancies[chosen] > 0.02:
        raise ValueError(
            "Las variables temporales del dataset de entrenamiento "
            "no coinciden con las fórmulas estándar. "
            "Es necesario reutilizar el código original de "
            "ingeniería de variables. "
            f"Errores máximos: {discrepancies}"
        )

    print(
        f"Variables temporales verificadas: {chosen} "
        f"(error máximo {discrepancies[chosen]:.5f})"
    )

    return chosen


def run(consultation_date: date, root: Path) -> Path:
    data_dir = root / "data" / "processed"

    input_path = (
        data_dir / "omie_precios_actualizados.parquet"
    )

    training_path = (
        data_dir / "omie_ml_hourly.parquet"
    )

    model_path = (
        root / "models" / "modelo_precio_hgb.joblib"
    )

    for path in (input_path, training_path, model_path):
        if not path.is_file():
            raise FileNotFoundError(
                f"Archivo obligatorio ausente: {path}"
            )

    # Dos días naturales locales siguientes.
    # En cambios de hora pueden ser 47, 48 o 49 horas físicas.

    start_local = pd.Timestamp(
        consultation_date + timedelta(days=1),
        tz=TZ,
    )

    end_local = pd.Timestamp(
        consultation_date + timedelta(days=3),
        tz=TZ,
    )

    local_hours = pd.date_range(
        start=start_local,
        end=end_local,
        freq="h",
        inclusive="left",
    )

    future_utc = local_hours.tz_convert("UTC")

    # Leer precios OMIE actualizados.

    prices = pd.read_parquet(input_path)

    required = {
        "datetime_utc",
        "price_eur_mwh",
    }

    if not required.issubset(prices.columns):
        raise ValueError(
            f"El fichero OMIE debe tener {sorted(required)}"
        )

    prices["datetime_utc"] = pd.to_datetime(
        prices["datetime_utc"],
        utc=True,
    )

    prices = prices.sort_values("datetime_utc")

    if prices["datetime_utc"].duplicated().any():
        raise ValueError(
            "Hay horas UTC duplicadas en los datos OMIE actualizados."
        )

    if prices["price_eur_mwh"].isna().any():
        raise ValueError(
            "Hay precios históricos nulos."
        )

    # No utilizar precios reales de los días predichos.

    prices = prices[
        prices["datetime_utc"] < future_utc.min()
    ]

    observed = prices.set_index(
        "datetime_utc"
    )["price_eur_mwh"]

    if observed.empty:
        raise ValueError(
            "El fichero OMIE no contiene histórico anterior a la predicción."
        )

    inferred_zone = determine_calendar_zone(
        training_path
    )

    features = build_calendar_features(
        future_utc,
        inferred_zone,
    )

    # Construir las variables históricas del modelo.

    for hours in (72, 168):
        lag_dates = (
            future_utc - pd.Timedelta(hours=hours)
        )

        lag_prices = observed.reindex(lag_dates)

        if lag_prices.isna().any():
            missing_dates = lag_dates[
                lag_prices.isna().to_numpy()
            ]

            preview = ", ".join(
                str(x) for x in missing_dates[:3]
            )

            raise ValueError(
                f"No hay precios reales para construir "
                f"price_lag_{hours}h. "
                f"Horas ausentes (UTC): {preview}. "
                "Actualiza OMIE antes de generar el plan."
            )

        features[
            f"price_lag_{hours}h"
        ] = lag_prices.to_numpy(dtype=float)

    # Cargar el modelo entrenado.

    model = joblib.load(model_path)

    if not hasattr(model, "feature_names_in_"):
        raise ValueError(
            "El modelo guardado no contiene nombres "
            "de variables verificables."
        )

    model_features = list(
        model.feature_names_in_
    )

    if model_features != FEATURES:
        raise ValueError(
            f"Variables del modelo diferentes de las esperadas: "
            f"{model_features}"
        )

    # Generar predicciones.

    prediction = np.asarray(
        model.predict(features[model_features]),
        dtype=float,
    )

    if not np.isfinite(prediction).all():
        raise ValueError(
            "El modelo generó algún precio no finito."
        )

    # Crear resultados.

    report = pd.DataFrame({
        "datetime_utc": future_utc,
        "fecha_local": local_hours,
        "precio_predicho_eur_mwh": prediction,
        "precio_baseline_eur_mwh": (
            features["price_lag_168h"].to_numpy()
        ),
        "fecha_emision_local": str(consultation_date),
        "modelo": type(model).__name__,
    })

    # Guardar archivo Parquet.

    out_path = (
        data_dir
        / f"prediccion_ml_48h_emitida_{consultation_date.isoformat()}.parquet"
    )

    report.to_parquet(
        out_path,
        index=False,
    )

    # Guardar metadatos.

    metadata = {
        "fecha_emision": str(consultation_date),
        "horizonte_inicio_local": str(start_local),
        "horizonte_fin_exclusivo_local": str(end_local),
        "horas": len(report),
        "primera_fecha_omie_disponible_utc": str(
            observed.index.min()
        ),
        "ultima_fecha_omie_disponible_utc": str(
            observed.index.max()
        ),
        "modelo": type(model).__name__,
        "precio_medio_predicho_eur_mwh": round(
            float(prediction.mean()), 3
        ),
        "estado": "prediccion_generada_pendiente_optimizacion",
    }

    out_path.with_suffix(".json").write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Mostrar resultados.

    print()
    print("FLOTIQ | PREVISION DE LOS DOS PROXIMOS DIAS")
    print("---------------------------------------------")
    print("Consulta:", consultation_date)
    print(
        "Horizonte local:",
        start_local,
        "→",
        end_local,
        "(exclusivo)",
    )
    print("Horas generadas:", len(report))
    print(
        f"Precio medio: {prediction.mean():.2f} €/MWh"
    )
    print("Guardado:", out_path)

    print()
    print(
        report[
            ["fecha_local", "precio_predicho_eur_mwh"]
        ].head(6).to_string(index=False)
    )

    print()
    print(
        "NOTA: Este fichero predice precios. "
        "El plan de recargas se calcula en el paso siguiente."
    )

    return out_path


def main() -> None:
    p = argparse.ArgumentParser(
        description=(
            "FLOTIQ: previsión de precios para "
            "los próximos dos días naturales"
        )
    )

    p.add_argument(
        "--fecha-consulta",
        help=(
            "Fecha local YYYY-MM-DD "
            "(por defecto, hoy en Madrid)"
        ),
    )

    args = p.parse_args()

    today = datetime.now(
        ZoneInfo(TZ)
    ).date()

    consultation_date = (
        date.fromisoformat(args.fecha_consulta)
        if args.fecha_consulta
        else today
    )

    run(
        consultation_date,
        find_root(),
    )


if __name__ == "__main__":
    main()
