
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal
import csv
import os

import psycopg
from dotenv import load_dotenv
from psycopg import sql


# =====================================================
# CONFIGURACIÓN
# =====================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "sample"

load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")


# Columnas que guardaremos en PostgreSQL.
# Algunas columnas repetidas de los CSV se omiten.
TABLES = {
    "vehicles": [
        "vehicle_id",
        "manufacturer",
        "model",
        "version",
        "model_year",
        "battery_usable_kwh",
        "max_ac_charging_kw",
        "wltp_consumption_kwh_100km",
        "simulated_consumption_kwh_100km",
        "data_type",
    ],
    "drivers": [
        "driver_id",
        "first_name",
        "last_name_1",
        "last_name_2",
        "full_name",
        "contract_type",
        "weekly_hours",
        "preferred_shift",
        "is_active",
        "data_type",
    ],
    "shifts": [
        "shift_id",
        "driver_id",
        "shift_date",
        "shift_type",
        "start_time",
        "end_time",
        "planned_hours",
        "data_type",
    ],
    "assignments": [
        "assignment_id",
        "shift_id",
        "vehicle_id",
        "data_type",
    ],
    "trips": [
        "trip_id",
        "assignment_id",
        "start_time",
        "end_time",
        "origin_area",
        "destination_area",
        "distance_km",
        "duration_minutes",
        "average_speed_kmh",
        "energy_consumed_kwh",
        "data_type",
    ],
}

PRIMARY_KEYS = {
    "vehicles": "vehicle_id",
    "drivers": "driver_id",
    "shifts": "shift_id",
    "assignments": "assignment_id",
    "trips": "trip_id",
}

INTEGER_COLUMNS = {
    "model_year",
    "weekly_hours",
    "duration_minutes",
}

DECIMAL_COLUMNS = {
    "battery_usable_kwh",
    "max_ac_charging_kw",
    "wltp_consumption_kwh_100km",
    "simulated_consumption_kwh_100km",
    "planned_hours",
    "distance_km",
    "average_speed_kmh",
    "energy_consumed_kwh",
}

BOOLEAN_COLUMNS = {"is_active"}
DATETIME_COLUMNS = {"start_time", "end_time"}
DATE_COLUMNS = {"shift_date"}


# =====================================================
# LECTURA Y TRANSFORMACIÓN
# =====================================================

def convert_value(column, value):
    if value is None or value.strip() == "":
        return None

    value = value.strip()

    if column in INTEGER_COLUMNS:
        return int(value)

    if column in DECIMAL_COLUMNS:
        return Decimal(value)

    if column in BOOLEAN_COLUMNS:
        if value.lower() in ("true", "1", "yes"):
            return True
        if value.lower() in ("false", "0", "no"):
            return False
        raise ValueError(
            f"Valor booleano no reconocido: {value}"
        )

    if column in DATETIME_COLUMNS:
        return datetime.fromisoformat(value)

    if column in DATE_COLUMNS:
        return date.fromisoformat(value)

    return value


def read_csv(table_name, columns):
    file_path = DATA_DIR / f"{table_name}.csv"

    if not file_path.exists():
        raise FileNotFoundError(
            f"No existe el archivo: {file_path}"
        )

    with file_path.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:

        reader = csv.DictReader(file)

        missing = set(columns) - set(reader.fieldnames or [])

        if missing:
            raise ValueError(
                f"{table_name}: faltan columnas {sorted(missing)}"
            )

        records = []

        for row_number, row in enumerate(reader, start=2):
            try:
                record = {
                    column: convert_value(column, row[column])
                    for column in columns
                }
            except (ValueError, TypeError) as error:
                raise ValueError(
                    f"{table_name}, línea {row_number}: {error}"
                ) from error

            records.append(record)

    return records


# =====================================================
# VALIDACIONES
# =====================================================

def validate_data(data):
    print("\nValidando los CSV...")

    # Comprobar identificadores obligatorios y únicos.
    for table, records in data.items():
        primary_key = PRIMARY_KEYS[table]
        identifiers = [row[primary_key] for row in records]

        if any(identifier is None for identifier in identifiers):
            raise ValueError(
                f"{table}: existen identificadores vacíos."
            )

        if len(identifiers) != len(set(identifiers)):
            raise ValueError(
                f"{table}: existen identificadores duplicados."
            )

        print(f"  OK {table}: {len(records):,} registros")

    drivers = {
        row["driver_id"] for row in data["drivers"]
    }

    vehicles = {
        row["vehicle_id"] for row in data["vehicles"]
    }

    shifts = {
        row["shift_id"]: row
        for row in data["shifts"]
    }

    assignments = {
        row["assignment_id"]: row
        for row in data["assignments"]
    }

    # Integridad referencial.
    for shift in shifts.values():
        if shift["driver_id"] not in drivers:
            raise ValueError(
                f"Conductor inexistente en {shift['shift_id']}"
            )

        if shift["end_time"] <= shift["start_time"]:
            raise ValueError(
                f"Horario incorrecto: {shift['shift_id']}"
            )

    assigned_shifts = set()

    for assignment in assignments.values():
        shift_id = assignment["shift_id"]

        if shift_id not in shifts:
            raise ValueError(
                f"Turno inexistente: {shift_id}"
            )

        if assignment["vehicle_id"] not in vehicles:
            raise ValueError(
                f"Vehículo inexistente en "
                f"{assignment['assignment_id']}"
            )

        if shift_id in assigned_shifts:
            raise ValueError(
                f"Turno asignado más de una vez: {shift_id}"
            )

        assigned_shifts.add(shift_id)

    for trip in data["trips"]:
        assignment_id = trip["assignment_id"]

        if assignment_id not in assignments:
            raise ValueError(
                f"Asignación inexistente: {assignment_id}"
            )

        if trip["end_time"] <= trip["start_time"]:
            raise ValueError(
                f"Horario incorrecto: {trip['trip_id']}"
            )

        if (
            trip["distance_km"] is not None
            and trip["distance_km"] < 0
        ):
            raise ValueError(
                f"Distancia negativa: {trip['trip_id']}"
            )

        if (
            trip["energy_consumed_kwh"] is not None
            and trip["energy_consumed_kwh"] < 0
        ):
            raise ValueError(
                f"Energía negativa: {trip['trip_id']}"
            )

    print("Validación básica: CORRECTA")


# =====================================================
# INSERCIÓN EN POSTGRESQL
# =====================================================

def insert_table(cursor, table_name, columns, records):
    if not records:
        return

    query = sql.SQL("""
        INSERT INTO {} ({})
        VALUES ({})
        ON CONFLICT ({}) DO NOTHING
    """).format(
        sql.Identifier(table_name),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(
            sql.Placeholder() for _ in columns
        ),
        sql.Identifier(PRIMARY_KEYS[table_name]),
    )

    values = [
        tuple(record[column] for column in columns)
        for record in records
    ]

    cursor.executemany(query, values)


def main():
    print("=" * 50)
    print("FlotIQ | CARGA DE DATOS EN SUPABASE")
    print("=" * 50)

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL no está configurada.")
        return

    try:
        # Primero leemos y validamos todo.
        data = {
            table: read_csv(table, columns)
            for table, columns in TABLES.items()
        }

        validate_data(data)

        print("\nConectando con Supabase...")

        # Una sola transacción para las cinco tablas.
        # Si falla una inserción, se revierte todo.
        with psycopg.connect(
            DATABASE_URL,
            connect_timeout=15,
            sslmode="require",
        ) as conn:

            with conn.cursor() as cursor:

                for table, columns in TABLES.items():
                    insert_table(
                        cursor,
                        table,
                        columns,
                        data[table],
                    )

                    cursor.execute(
                        sql.SQL("SELECT COUNT(*) FROM {}").format(
                            sql.Identifier(table)
                        )
                    )

                    total = cursor.fetchone()[0]

                    print(
                        f"  {table}: "
                        f"{total:,} registros en PostgreSQL"
                    )

            # El contexto de conexión confirma los
            # cambios únicamente si todo ha salido bien.

        print("\nCARGA COMPLETADA CORRECTAMENTE")

    except (ValueError, FileNotFoundError) as error:
        print(f"\nERROR DE VALIDACIÓN: {error}")

    except psycopg.Error as error:
        print("\nERROR EN LA BASE DE DATOS")
        print(f"Tipo: {type(error).__name__}")
        print(
            "Revisa el esquema SQL, los datos "
            "y las relaciones entre tablas."
        )


if __name__ == "__main__":
    main()
