
from datetime import timedelta
from pathlib import Path
import random

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"

ASSIGNMENTS_PATH = SAMPLE_DIR / "assignments.csv"
SHIFTS_PATH = SAMPLE_DIR / "shifts.csv"
VEHICLES_PATH = SAMPLE_DIR / "vehicles.csv"
OUTPUT_PATH = SAMPLE_DIR / "trips.csv"

RANDOM_SEED = 42

# Zonas reales utilizadas como etiquetas de
# viajes ficticios. No representan rutas verificadas.
MADRID_AREAS = [
    "Centro",
    "Salamanca",
    "Chamartín",
    "Chamberí",
    "Moncloa",
    "Retiro",
    "Arganzuela",
    "Tetuán",
    "Hortaleza",
    "Barajas",
    "Fuencarral",
    "Ciudad Lineal",
    "Carabanchel",
    "Vallecas",
    "Atocha",
]

# Hipótesis de simulación.
MIN_TRIP_MINUTES = 12
MAX_TRIP_MINUTES = 32

MIN_WAIT_MINUTES = 8
MAX_WAIT_MINUTES = 20

BREAK_MINUTES = 30


def generate_trips():
    rng = random.Random(RANDOM_SEED)

    assignments = pd.read_csv(
        ASSIGNMENTS_PATH,
        parse_dates=["start_time", "end_time"],
    )

    shifts = pd.read_csv(SHIFTS_PATH)

    vehicles = pd.read_csv(VEHICLES_PATH)

    if assignments.empty:
        raise ValueError("No hay asignaciones")

    if not assignments["assignment_id"].is_unique:
        raise ValueError("Asignaciones duplicadas")

    if not assignments["shift_id"].is_unique:
        raise ValueError("Un turno tiene varias asignaciones")

    if len(assignments) != len(shifts):
        raise ValueError(
            "El número de turnos y asignaciones no coincide"
        )

    merged = assignments.merge(
        shifts[["shift_id", "driver_id"]],
        on="shift_id",
        suffixes=("", "_shift"),
        validate="one_to_one",
    )

    if not (
        merged["driver_id"] == merged["driver_id_shift"]
    ).all():
        raise ValueError(
            "Conductores inconsistentes entre tablas"
        )

    consumption_map = vehicles.set_index(
        "vehicle_id"
    )["simulated_consumption_kwh_100km"].to_dict()

    if not set(assignments["vehicle_id"]).issubset(
        consumption_map
    ):
        raise ValueError("Existen vehículos desconocidos")

    trips = []
    trip_number = 1

    assignments = assignments.sort_values(
        ["start_time", "assignment_id"]
    )

    for assignment in assignments.itertuples():
        shift_start = assignment.start_time
        shift_end = assignment.end_time

        # Pequeño margen al comenzar el turno.
        current_time = shift_start + timedelta(
            minutes=rng.randint(5, 15)
        )

        previous_area = rng.choice(MADRID_AREAS)
        break_taken = False

        # Una jornada de 8 horas no equivale
        # a 8 horas transportando pasajeros.
        while current_time + timedelta(
            minutes=MIN_TRIP_MINUTES
        ) <= shift_end:

            elapsed_hours = (
                current_time - shift_start
            ).total_seconds() / 3600

            # Descanso de 30 minutos después
            # de aproximadamente cuatro horas.
            if elapsed_hours >= 4 and not break_taken:
                current_time += timedelta(
                    minutes=BREAK_MINUTES
                )
                break_taken = True
                continue

            remaining_minutes = int(
                (shift_end - current_time).total_seconds() / 60
            )

            duration = rng.randint(
                MIN_TRIP_MINUTES,
                min(MAX_TRIP_MINUTES, remaining_minutes),
            )

            trip_end = current_time + timedelta(
                minutes=duration
            )

            # Velocidad comercial sintética.
            # No procede directamente de sensores.
            speed_kmh = rng.uniform(16, 32)

            distance_km = round(
                speed_kmh * duration / 60,
                2,
            )

            origin = previous_area

            destination = rng.choice([
                area for area in MADRID_AREAS
                if area != origin
            ])

            consumption = consumption_map[
                assignment.vehicle_id
            ]

            energy_kwh = round(
                distance_km * consumption / 100,
                3,
            )

            trips.append({
                "trip_id": f"T{trip_number:06d}",
                "assignment_id": assignment.assignment_id,
                "shift_id": assignment.shift_id,
                "driver_id": assignment.driver_id,
                "vehicle_id": assignment.vehicle_id,
                "start_time": current_time,
                "end_time": trip_end,
                "origin_area": origin,
                "destination_area": destination,
                "distance_km": distance_km,
                "duration_minutes": duration,
                "average_speed_kmh": round(speed_kmh, 2),
                "energy_consumed_kwh": energy_kwh,
                "data_type": "synthetic",
            })

            trip_number += 1
            previous_area = destination

            # Espera entre servicios.
            current_time = trip_end + timedelta(
                minutes=rng.randint(
                    MIN_WAIT_MINUTES,
                    MAX_WAIT_MINUTES,
                )
            )

    df = pd.DataFrame(trips)

    if df.empty:
        raise ValueError("No se generaron trayectos")

    # Validaciones de duración y consumo.
    if not (df["start_time"] < df["end_time"]).all():
        raise ValueError("Hay viajes con horarios incorrectos")

    if not df["trip_id"].is_unique:
        raise ValueError("Hay identificadores duplicados")

    if not df["distance_km"].gt(0).all():
        raise ValueError("Hay distancias inválidas")

    if not df["energy_consumed_kwh"].gt(0).all():
        raise ValueError("Hay consumos inválidos")

    # Validar que cada viaje esté dentro
    # del turno asignado.
    checked = df.merge(
        assignments[
            [
                "assignment_id",
                "start_time",
                "end_time",
            ]
        ],
        on="assignment_id",
        suffixes=("_trip", "_shift"),
        validate="many_to_one",
    )

    if not (
        (
            checked["start_time_trip"]
            >= checked["start_time_shift"]
        )
        &
        (
            checked["end_time_trip"]
            <= checked["end_time_shift"]
        )
    ).all():
        raise ValueError(
            "Existen viajes fuera de su turno"
        )

    # Validar que no haya viajes solapados
    # para un mismo vehículo o conductor.
    for column in ["vehicle_id", "driver_id"]:
        for identifier, group in df.groupby(column):
            ordered = group.sort_values("start_time")

            previous_end = None

            for trip in ordered.itertuples():
                if (
                    previous_end is not None
                    and trip.start_time < previous_end
                ):
                    raise ValueError(
                        f"Solapamiento para {column}: {identifier}"
                    )

                previous_end = trip.end_time

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n=== FlotIQ | TRAYECTOS VTC ===")
    print(f"Viajes generados: {len(df):,}")
    print(f"Turnos con viajes: {df['shift_id'].nunique()}")
    print(f"Vehículos utilizados: {df['vehicle_id'].nunique()}")
    print(f"Conductores: {df['driver_id'].nunique()}")

    print(
        f"Kilómetros totales: "
        f"{df['distance_km'].sum():,.2f} km"
    )

    print(
        f"Energía consumida: "
        f"{df['energy_consumed_kwh'].sum():,.2f} kWh"
    )

    print(
        f"Distancia media por viaje: "
        f"{df['distance_km'].mean():.2f} km"
    )

    print("\nResumen por vehículo:")
    vehicle_summary = df.groupby(
        "vehicle_id"
    ).agg(
        trips=("trip_id", "count"),
        distance_km=("distance_km", "sum"),
        energy_kwh=("energy_consumed_kwh", "sum"),
    )

    print(vehicle_summary.head(10).round(2).to_string())

    print(f"\nArchivo generado: {OUTPUT_PATH}")


if __name__ == "__main__":
    generate_trips()
