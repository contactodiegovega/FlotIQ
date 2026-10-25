
from pathlib import Path
import json
import importlib.util

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error

ROOT = Path(__file__).resolve().parents[1]
DATOS = ROOT / "data" / "processed" / "omie_ml_hourly.parquet"
MODELOS = ROOT / "models"

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


def main():
    if not DATOS.exists():
        raise FileNotFoundError(f"Falta el dataset: {DATOS}")

    df = pd.read_parquet(DATOS)
    df["datetime_utc"] = pd.to_datetime(
        df["datetime_utc"], utc=True
    )
    df = df.sort_values("datetime_utc").reset_index(drop=True)

    requeridas = ["datetime_utc", "price_eur_mwh", *FEATURES]

    if df[requeridas].isna().any().any():
        raise ValueError("El dataset ML contiene valores nulos")

    test_start = (
        df["datetime_utc"].max()
        - pd.Timedelta(days=90)
        + pd.Timedelta(hours=1)
    )

    train_val = df[df["datetime_utc"] < test_start]
    test = df[df["datetime_utc"] >= test_start]

    val_start = (
        train_val["datetime_utc"].max()
        - pd.Timedelta(days=60)
        + pd.Timedelta(hours=1)
    )

    train = train_val[
        train_val["datetime_utc"] < val_start
    ]

    val = train_val[
        train_val["datetime_utc"] >= val_start
    ]

    if min(map(len, [train, val, test])) < 100:
        raise ValueError("Datos insuficientes para entrenar")

    modelos = {
        "ridge": [
            Pipeline([
                ("scaler", StandardScaler()),
                ("ridge", Ridge(alpha=a)),
            ])
            for a in [0.1, 1, 10, 100, 1000]
        ],

        "rf": [
            RandomForestRegressor(
                n_estimators=150,
                max_depth=depth,
                min_samples_leaf=leaf,
                random_state=42,
                n_jobs=-1,
            )
            for depth, leaf in [(8, 10), (14, 5)]
        ],
    }

    if importlib.util.find_spec("xgboost"):
        from xgboost import XGBRegressor

        modelos["xgb"] = [
            XGBRegressor(
                max_depth=depth,
                learning_rate=rate,
                n_estimators=n,
                objective="reg:squarederror",
                subsample=0.8,
                colsample_bytree=0.9,
                reg_lambda=5.0,
                tree_method="hist",
                random_state=42,
                n_jobs=4,
            )
            for depth, rate, n in [
                (3, 0.05, 300),
                (5, 0.05, 300),
                (3, 0.03, 500),
            ]
        ]
    else:
        print("XGBoost no instalado: se omite")

    MODELOS.mkdir(parents=True, exist_ok=True)

    informe = {
        "dataset": DATOS.name,
        "test_inicio_utc": str(test["datetime_utc"].min()),
        "test_fin_utc": str(test["datetime_utc"].max()),
        "baseline_mae_test": round(
            float(mean_absolute_error(
                test["price_eur_mwh"],
                test["price_lag_168h"],
            )),
            3,
        ),
        "modelos": {},
    }

    for nombre, candidatos in modelos.items():
        mejor = None
        mejor_mae = float("inf")

        for candidato in candidatos:
            candidato.fit(
                train[FEATURES],
                train["price_eur_mwh"],
            )

            predicciones = candidato.predict(
                val[FEATURES]
            )

            mae = mean_absolute_error(
                val["price_eur_mwh"],
                predicciones,
            )

            if mae < mejor_mae:
                mejor = candidato
                mejor_mae = float(mae)

        test_mae = mean_absolute_error(
            test["price_eur_mwh"],
            mejor.predict(test[FEATURES]),
        )

        ruta = MODELOS / f"modelo_precio_{nombre}.joblib"

        joblib.dump(mejor, ruta)

        informe["modelos"][nombre] = {
            "mae_validacion": round(mejor_mae, 3),
            "mae_test": round(float(test_mae), 3),
            "archivo": ruta.name,
        }

        print(
            nombre,
            "MAE test:",
            round(float(test_mae), 2),
            "archivo:",
            ruta.name,
        )

    # El modelo HGB existente permanece intacto.
    (MODELOS / "metricas_escenarios.json").write_text(
        json.dumps(
            informe,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        "Baseline MAE test:",
        informe["baseline_mae_test"],
    )


if __name__ == "__main__":
    main()
