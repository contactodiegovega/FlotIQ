
from pathlib import Path
import os

import psycopg
from dotenv import load_dotenv


# Localizar la raíz de FlotIQ
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Cargar las credenciales privadas
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")


def test_connection():

    if not DATABASE_URL:
        print("ERROR: No se ha encontrado DATABASE_URL en .env")
        return

    try:
        with psycopg.connect(
            DATABASE_URL,
            connect_timeout=10,
            sslmode="require"
        ) as conn:

            with conn.cursor() as cursor:

                cursor.execute("SELECT current_database();")
                database = cursor.fetchone()[0]

                print("Conexión con Supabase: CORRECTA")
                print(f"Base de datos: {database}")

                cursor.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name IN (
                        'vehicles',
                        'drivers',
                        'shifts',
                        'assignments',
                        'trips'
                    )
                    ORDER BY table_name;
                """)

                tables = cursor.fetchall()

                print("\nTablas encontradas:")

                for table in tables:
                    print(f" - {table[0]}")

                print(f"\nTotal: {len(tables)} de 5 tablas")

                if len(tables) == 5:
                    print("\nFlotIQ: BASE DE DATOS PREPARADA")

    except psycopg.Error as error:
        print("ERROR: No se ha podido conectar a Supabase.")
        print(f"Tipo de error: {type(error).__name__}")

        mensaje = str(error).lower()

        if "password authentication failed" in mensaje:
            print("Causa probable: contraseña o usuario incorrectos.")
        elif "name or service not known" in mensaje or "could not translate host name" in mensaje:
            print("Causa probable: dirección del servidor incorrecta.")
        elif "connection refused" in mensaje or "timeout" in mensaje or "timed out" in mensaje:
            print("Causa probable: puerto, red o método de conexión.")
        elif "invalid" in mensaje or "missing" in mensaje:
            print("Causa probable: formato incorrecto de DATABASE_URL.")
        else:
            print("No se ha podido identificar la causa automáticamente.")


if __name__ == "__main__":
    test_connection()
