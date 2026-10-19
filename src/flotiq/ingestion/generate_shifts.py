
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"

DRIVERS_PATH = SAMPLE_DIR / "drivers.csv"
VEHICLES_PATH = SAMPLE_DIR / "vehicles.csv"

SHIFTS_PATH = SAMPLE_DIR / "shifts.csv"
ASSIGNMENTS_PATH = SAMPLE_DIR / "assignments.csv"

START_DATE = date(2026, 9, 21)
NUM_DAYS = 7

SHIFT_HOURS = {
    "night": (0, 8),
    "morning": (8, 16),
    "afternoon": (16, 24),
}

SHIFT_ORDER = ["night", "morning", "afternoon"]


def generate_shifts():
    drivers = pd.read_csv(DRIVERS_PATH)
    vehicles = pd.read_csv(VEHICLES_PATH)

    if len(drivers) != 80 or not drivers["driver_id"].is_unique:
        raise ValueError("El inventario debe tener 80 conductores únicos")

    if len(vehicles) != 50 or not vehicles["vehicle_id"].is_unique:
        raise ValueError("El inventario debe tener 50 vehículos únicos")

    if not drivers["preferred_shift"].isin(SHIFT_HOURS).all():
        raise ValueError("Existen preferencias de turno desconocidas")

    drivers = drivers.sort_values("driver_id").reset_index(drop=True)
    vehicle_ids = sorted(vehicles["vehicle_id"].tolist())

    shifts = []
    assignments = []

    shift_number = 1
    assignment_number = 1

    for day_offset in range(NUM_DAYS):
        current_date = START_DATE + timedelta(days=day_offset)

        daily_shifts = []

        for driver_index, driver in drivers.iterrows():

            # Dos días consecutivos de descanso,
            # distribuidos entre los siete días.
            first_day_off = driver_index % NUM_DAYS
            days_off = {
                first_day_off,
                (first_day_off + 1) % NUM_DAYS,
            }

            if day_offset in days_off:
                continue

            shift_type = driver["preferred_shift"]
            start_hour, end_hour = SHIFT_HOURS[shift_type]

            start_time = datetime.combine(
                current_date,
                datetime.min.time()
            ) + timedelta(hours=start_hour)

            end_time = datetime.combine(
                current_date,
                datetime.min.time()
            ) + timedelta(hours=end_hour)

            shift = {
                "shift_id": f"S{shift_number:05d}",
                "driver_id": driver["driver_id"],
                "shift_date": current_date.isoformat(),
                "shift_type": shift_type,
                "start_time": start_time,
                "end_time": end_time,
                "planned_hours": 8,
                "data_type": "synthetic",
            }

            daily_shifts.append(shift)
            shift_number += 1

        # Asignar vehículos por turnos, evitando
        # solapamientos y más de dos turnos diarios.
        vehicle_usage = {vehicle_id: 0 for vehicle_id in vehicle_ids}

        daily_shifts.sort(
            key=lambda shift: (
                SHIFT_ORDER.index(shift["shift_type"]),
                shift["driver_id"],
            )
        )

        for shift in daily_shifts:
            eligible = [
                vehicle_id
                for vehicle_id in vehicle_ids
                if vehicle_usage[vehicle_id] < 2
            ]

            # Repartir las asignaciones entre vehículos
            # con menor uso durante el día.
            eligible.sort(
                key=lambda vehicle_id: (
                    vehicle_usage[vehicle_id],
                    (
                        vehicle_ids.index(vehicle_id)
                        - day_offset * 7
                    ) % len(vehicle_ids),
                )
            )

            if not eligible:
                raise ValueError(
                    f"No hay vehículos disponibles el {current_date}"
                )

            vehicle_id = eligible[0]
            vehicle_usage[vehicle_id] += 1

            assignments.append({
                "assignment_id": f"A{assignment_number:05d}",
                "shift_id": shift["shift_id"],
                "driver_id": shift["driver_id"],
                "vehicle_id": vehicle_id,
                "start_time": shift["start_time"],
                "end_time": shift["end_time"],
                "data_type": "synthetic",
            })

            assignment_number += 1

        shifts.extend(daily_shifts)

    shifts_df = pd.DataFrame(shifts)
    assignments_df = pd.DataFrame(assignments)

    # Validaciones iniciales.
    assert len(shifts_df) == 400
    assert len(assignments_df) == 400
    assert shifts_df["shift_id"].is_unique
    assert assignments_df["shift_id"].is_unique

    weekly_hours = shifts_df.groupby("driver_id")[
        "planned_hours"
    ].sum()

    if len(weekly_hours) != 80 or not weekly_hours.eq(40).all():
        raise ValueError("Las horas semanales no son correctas")

    if not set(assignments_df["vehicle_id"]).issubset(vehicle_ids):
        raise ValueError("Hay vehículos desconocidos")

    # Comprobar solapamientos de vehículos y conductores.
    for column in ["vehicle_id", "driver_id"]:
        for identifier, group in assignments_df.groupby(column):
            ordered = group.sort_values("start_time")
            previous_end = None

            for row in ordered.itertuples():
                if previous_end is not None and row.start_time < previous_end:
                    raise ValueError(
                        f"Solapamiento para {column}: {identifier}"
                    )

                previous_end = row.end_time

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    shifts_df.to_csv(
        SHIFTS_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    assignments_df.to_csv(
        ASSIGNMENTS_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n=== FlotIQ | PLANIFICACIÓN SEMANAL ===")
    print(f"Conductores: {len(drivers)}")
    print(f"Vehículos: {len(vehicles)}")
    print(f"Turnos generados: {len(shifts_df)}")
    print(f"Asignaciones: {len(assignments_df)}")
    print(f"Horas planificadas: {shifts_df['planned_hours'].sum()}")

    print("\nTurnos por franja:")
    print(shifts_df["shift_type"].value_counts().to_string())

    print("\nTurnos por día y franja:")
    print(
        shifts_df.pivot_table(
            index="shift_date",
            columns="shift_type",
            values="shift_id",
            aggfunc="count",
            fill_value=0,
        ).to_string()
    )

    print(f"\nArchivo: {SHIFTS_PATH}")
    print(f"Archivo: {ASSIGNMENTS_PATH}")


if __name__ == "__main__":
    generate_shifts()
