
from pathlib import Path
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]

OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "sample" / "vehicles.csv"
)

NUM_VEHICLES = 50

# Especificaciones de referencia del modelo 2025.
# Pendientes de verificación final de variante.
BATTERY_KWH = 60.0
CHARGING_POWER_AC_KW = 11.0
WLTP_CONSUMPTION_KWH_100KM = 13.0

# Hipótesis operativa para la simulación VTC.
SIMULATED_CONSUMPTION_KWH_100KM = 16.0


def generate_vehicles():
    vehicles = []

    for number in range(1, NUM_VEHICLES + 1):
        vehicle = {
            "vehicle_id": f"V{number:03d}",
            "manufacturer": "Tesla",
            "model": "Model 3",
            "version": "RWD",
            "model_year": 2025,
            "battery_usable_kwh": BATTERY_KWH,
            "max_ac_charging_kw": CHARGING_POWER_AC_KW,
            "wltp_consumption_kwh_100km":
                WLTP_CONSUMPTION_KWH_100KM,
            "simulated_consumption_kwh_100km":
                SIMULATED_CONSUMPTION_KWH_100KM,
            "data_type": "synthetic_fleet",
        }

        vehicles.append(vehicle)

    df = pd.DataFrame(vehicles)

    # Validaciones básicas.
    assert len(df) == NUM_VEHICLES
    assert df["vehicle_id"].is_unique
    assert df["battery_usable_kwh"].gt(0).all()
    assert df["max_ac_charging_kw"].gt(0).all()

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8"
    )

    print("\n=== FlotIQ | FLOTA DE VEHÍCULOS ===")
    print(f"Vehículos generados: {len(df)}")
    print(f"Modelos diferentes: {df['model'].nunique()}")
    print(f"Batería por vehículo: {BATTERY_KWH} kWh")
    print(
        "Capacidad total teórica: "
        f"{df['battery_usable_kwh'].sum():.0f} kWh"
    )
    print("\nPrimeros vehículos:")
    print(df.head().to_string(index=False))
    print(f"\nArchivo generado: {OUTPUT_PATH}")


if __name__ == "__main__":
    generate_vehicles()
