
from pathlib import Path

import pandas as pd


# =========================================================
# CONFIGURACIÓN
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

VEHICLES_PATH = SAMPLE_DIR / "vehicles.csv"
ASSIGNMENTS_PATH = SAMPLE_DIR / "assignments.csv"
TRIPS_PATH = SAMPLE_DIR / "trips.csv"

EVENTS_PATH = (
    PROCESSED_DIR / "battery_events_202609.csv"
)

SUMMARY_PATH = (
    PROCESSED_DIR / "battery_shifts_202609.csv"
)

BATTERY_CAPACITY_KWH = 60.0
INITIAL_SOC = 90.0
MIN_SOC = 15.0


# =========================================================
# SIMULACIÓN
# =========================================================

def simulate_battery():

    print("\n=== FlotIQ | SIMULACIÓN DE BATERÍAS ===")

    vehicles = pd.read_csv(VEHICLES_PATH)

    assignments = pd.read_csv(
        ASSIGNMENTS_PATH,
        parse_dates=["start_time", "end_time"],
    )

    trips = pd.read_csv(
        TRIPS_PATH,
        parse_dates=["start_time", "end_time"],
    )

    # Validar estructura y relaciones.
    required_vehicle = {"vehicle_id"}
    required_assignment = {
        "assignment_id", "shift_id", "driver_id",
        "vehicle_id", "start_time", "end_time",
    }
    required_trip = {
        "trip_id", "assignment_id", "vehicle_id",
        "start_time", "end_time",
        "energy_consumed_kwh",
    }

    for df, required, name in [
        (vehicles, required_vehicle, "vehicles"),
        (assignments, required_assignment, "assignments"),
        (trips, required_trip, "trips"),
    ]:
        missing = required - set(df.columns)

        if missing:
            raise ValueError(
                f"Faltan columnas en {name}: {sorted(missing)}"
            )

    if vehicles["vehicle_id"].duplicated().any():
        raise ValueError("Hay vehículos duplicados")

    if assignments["assignment_id"].duplicated().any():
        raise ValueError("Hay asignaciones duplicadas")

    if trips["trip_id"].duplicated().any():
        raise ValueError("Hay viajes duplicados")

    if trips["energy_consumed_kwh"].isna().any():
        raise ValueError("Hay consumos nulos")

    if (trips["energy_consumed_kwh"] < 0).any():
        raise ValueError("Hay consumos negativos")

    if not set(assignments["vehicle_id"]).issubset(
        set(vehicles["vehicle_id"])
    ):
        raise ValueError("Hay vehículos desconocidos")

    if not set(trips["assignment_id"]).issubset(
        set(assignments["assignment_id"])
    ):
        raise ValueError("Hay viajes sin asignación")

    # Comprobar coherencia de vehículo.
    checked = trips.merge(
        assignments[
            [
                "assignment_id",
                "vehicle_id",
                "start_time",
                "end_time",
            ]
        ],
        on="assignment_id",
        suffixes=("_trip", "_shift"),
        validate="many_to_one",
    )

    valid = (
        (checked["vehicle_id_trip"] == checked["vehicle_id_shift"])
        & (checked["start_time_trip"] >= checked["start_time_shift"])
        & (checked["end_time_trip"] <= checked["end_time_shift"])
    )

    if not valid.all():
        raise ValueError(
            "Hay viajes con vehículo u horario inconsistente"
        )

    # Energía inicial y reserva mínima.
    initial_energy = (
        BATTERY_CAPACITY_KWH * INITIAL_SOC / 100
    )

    reserve_energy = (
        BATTERY_CAPACITY_KWH * MIN_SOC / 100
    )

    battery_state = {
        vehicle_id: initial_energy
        for vehicle_id in vehicles["vehicle_id"]
    }

    events = []
    summaries = []

    assignments = assignments.sort_values(
        ["start_time", "assignment_id"]
    )

    trips_by_assignment = {
        key: group.sort_values(["start_time", "trip_id"])
        for key, group in trips.groupby("assignment_id")
    }

    # =====================================================
    # RECORRER TURNOS CRONOLÓGICAMENTE
    # =====================================================

    for assignment in assignments.itertuples():

        vehicle_id = assignment.vehicle_id

        energy_before_shift = battery_state[vehicle_id]

        shift_trips = trips_by_assignment.get(
            assignment.assignment_id
        )

        shift_consumption = 0.0
        trip_count = 0

        if shift_trips is not None:

            for trip in shift_trips.itertuples():

                energy_before = battery_state[vehicle_id]

                consumed = float(
                    trip.energy_consumed_kwh
                )

                energy_after = energy_before - consumed

                battery_state[vehicle_id] = energy_after

                soc_before = (
                    energy_before / BATTERY_CAPACITY_KWH * 100
                )

                soc_after = (
                    energy_after / BATTERY_CAPACITY_KWH * 100
                )

                # Son saldos teóricos sin recargas.
                # Pueden ser negativos: representan
                # demanda energética no cubierta.
                events.append({
                    "trip_id": trip.trip_id,
                    "assignment_id": assignment.assignment_id,
                    "shift_id": assignment.shift_id,
                    "driver_id": assignment.driver_id,
                    "vehicle_id": vehicle_id,
                    "timestamp": trip.end_time,
                    "energy_consumed_kwh": consumed,
                    "energy_before_kwh": round(
                        energy_before, 3
                    ),
                    "energy_after_kwh": round(
                        energy_after, 3
                    ),
                    "soc_before_pct": round(
                        soc_before, 2
                    ),
                    "soc_after_pct": round(
                        soc_after, 2
                    ),
                    "below_min_soc": (
                        energy_after < reserve_energy
                    ),
                    "energy_deficit_kwh": round(
                        max(0.0, -energy_after), 3
                    ),
                    "data_type": "synthetic",
                })

                shift_consumption += consumed
                trip_count += 1

        energy_after_shift = battery_state[vehicle_id]

        summaries.append({
            "assignment_id": assignment.assignment_id,
            "shift_id": assignment.shift_id,
            "driver_id": assignment.driver_id,
            "vehicle_id": vehicle_id,
            "start_time": assignment.start_time,
            "end_time": assignment.end_time,
            "trips": trip_count,
            "energy_consumed_kwh": round(
                shift_consumption, 3
            ),
            "energy_start_kwh": round(
                energy_before_shift, 3
            ),
            "energy_end_kwh": round(
                energy_after_shift, 3
            ),
            "soc_start_pct": round(
                energy_before_shift
                / BATTERY_CAPACITY_KWH * 100,
                2,
            ),
            "soc_end_pct": round(
                energy_after_shift
                / BATTERY_CAPACITY_KWH * 100,
                2,
            ),
            "below_min_soc": (
                energy_after_shift < reserve_energy
            ),
            "data_type": "synthetic",
        })

    # =====================================================
    # GUARDAR RESULTADOS
    # =====================================================

    events_df = pd.DataFrame(events)
    summary_df = pd.DataFrame(summaries)

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    events_df.to_csv(
        EVENTS_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    summary_df.to_csv(
        SUMMARY_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    # =====================================================
    # AUDITORÍA FINAL
    # =====================================================

    print(f"Vehículos: {len(vehicles)}")
    print(f"Turnos analizados: {len(summary_df):,}")
    print(f"Viajes analizados: {len(events_df):,}")

    print(
        f"Energía total consumida: "
        f"{events_df['energy_consumed_kwh'].sum():,.2f} kWh"
    )

    print(
        f"Viajes que terminan por debajo del 15 %: "
        f"{events_df['below_min_soc'].sum():,}"
    )

    print(
        f"Turnos que terminan por debajo del 15 %: "
        f"{summary_df['below_min_soc'].sum():,}"
    )

    deficit = (
        summary_df.groupby("vehicle_id")["energy_end_kwh"]
        .last()
        .lt(0)
        .sum()
    )

    print(
        f"Vehículos con saldo energético final negativo: "
        f"{deficit}"
    )

    print("\nPrimeros 10 turnos:")
    print(
        summary_df[
            [
                "vehicle_id",
                "shift_id",
                "energy_consumed_kwh",
                "soc_start_pct",
                "soc_end_pct",
                "below_min_soc",
            ]
        ].head(10).to_string(index=False)
    )

    print(f"\nEventos: {EVENTS_PATH}")
    print(f"Resumen: {SUMMARY_PATH}")

    print(
        "\nNOTA: Esta simulación NO incluye recargas. "
        "Los saldos negativos son déficits teóricos, "
        "no estados físicos posibles de una batería."
    )


if __name__ == "__main__":
    simulate_battery()
