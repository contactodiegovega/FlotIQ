
from pathlib import Path
import random

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]

OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "sample" / "drivers.csv"
)

NUM_DRIVERS = 80
RANDOM_SEED = 42

FIRST_NAMES = [
    "Alejandro", "Pablo", "Javier", "Carlos", "David",
    "Daniel", "Sergio", "Miguel", "Álvaro", "Adrián",
    "Antonio", "Francisco", "Manuel", "José", "Luis",
    "Rubén", "Fernando", "Raúl", "Mario", "Iván",
    "Laura", "Marta", "Lucía", "Paula", "María",
    "Ana", "Elena", "Sara", "Claudia", "Cristina",
    "Andrea", "Carmen", "Patricia", "Natalia",
    "Sandra", "Beatriz", "Isabel", "Raquel",
    "Sofía", "Alba"
]

SURNAMES = [
    "García", "Fernández", "González", "Rodríguez",
    "López", "Martínez", "Sánchez", "Pérez",
    "Gómez", "Martín", "Jiménez", "Ruiz",
    "Hernández", "Díaz", "Moreno", "Muñoz",
    "Álvarez", "Romero", "Alonso", "Gutiérrez",
    "Navarro", "Torres", "Domínguez", "Vázquez",
    "Ramos", "Gil", "Ramírez", "Serrano",
    "Blanco", "Molina", "Suárez", "Ortega"
]


def generate_drivers():
    rng = random.Random(RANDOM_SEED)

    drivers = []
    used_names = set()

    shift_preferences = (
        ["morning"] * 30
        + ["afternoon"] * 30
        + ["night"] * 20
    )

    rng.shuffle(shift_preferences)

    for number in range(1, NUM_DRIVERS + 1):

        # Evitar nombres completos duplicados.
        while True:
            first_name = rng.choice(FIRST_NAMES)
            surname_1 = rng.choice(SURNAMES)
            surname_2 = rng.choice(SURNAMES)

            full_name = (
                first_name,
                surname_1,
                surname_2,
            )

            if full_name not in used_names:
                used_names.add(full_name)
                break

        driver = {
            "driver_id": f"D{number:03d}",
            "first_name": first_name,
            "last_name_1": surname_1,
            "last_name_2": surname_2,
            "full_name": (
                f"{first_name} {surname_1} {surname_2}"
            ),
            "contract_type": "full_time",
            "weekly_hours": 40,
            "preferred_shift": shift_preferences[number - 1],
            "is_active": True,
            "data_type": "synthetic",
        }

        drivers.append(driver)

    df = pd.DataFrame(drivers)

    # Validaciones
    assert len(df) == NUM_DRIVERS
    assert df["driver_id"].is_unique
    assert df["full_name"].is_unique
    assert df["weekly_hours"].gt(0).all()

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n=== FlotIQ | CONDUCTORES ===")
    print(f"Conductores generados: {len(df)}")
    print(f"Nombres únicos: {df['full_name'].nunique()}")

    print("\nPreferencias de turno:")
    print(df["preferred_shift"].value_counts())

    print("\nPrimeros 10 conductores:")
    print(
        df[
            [
                "driver_id",
                "full_name",
                "preferred_shift",
                "weekly_hours",
            ]
        ].head(10).to_string(index=False)
    )

    print(f"\nArchivo generado: {OUTPUT_PATH}")


if __name__ == "__main__":
    generate_drivers()
