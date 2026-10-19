
from pathlib import Path

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[3]

OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "weather"
OUTPUT_FILE = OUTPUT_DIR / "madrid_weather_2023_2026.csv"

API_URL = "https://archive-api.open-meteo.com/v1/archive"

# Coordenadas aproximadas del centro de Madrid.
LATITUDE = 40.4168
LONGITUDE = -3.7038


def download_weather():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": "2023-01-01",
        "end_date": "2026-09-30",
        "hourly": [
            "temperature_2m",
            "precipitation",
            "wind_speed_10m",
        ],
        "timezone": "Europe/Madrid",
    }

    print("\n=== FlotIQ | METEOROLOGÍA MADRID ===")
    print("Consultando Open-Meteo...")

    response = requests.get(
        API_URL,
        params=params,
        timeout=120,
    )
    response.raise_for_status()

    data = response.json()

    if "hourly" not in data:
        raise ValueError(
            "La respuesta no contiene datos horarios"
        )

    df = pd.DataFrame(data["hourly"])

    if df.empty:
        raise ValueError("El dataset está vacío")

    df["time"] = pd.to_datetime(df["time"])

    df = df.rename(
        columns={
            "time": "datetime",
            "temperature_2m": "temperature_c",
            "precipitation": "precipitation_mm",
            "wind_speed_10m": "wind_speed_kmh",
        }
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8",
    )

    print(f"Registros: {len(df):,}")
    print(f"Fecha inicial: {df['datetime'].min()}")
    print(f"Fecha final: {df['datetime'].max()}")

    print("\nValores nulos:")
    print(df.isna().sum().to_string())

    print(f"\nArchivo generado: {OUTPUT_FILE}")


if __name__ == "__main__":
    download_weather()
