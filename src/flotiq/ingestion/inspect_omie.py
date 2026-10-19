
from pathlib import Path
import hashlib

# Ruta raíz del proyecto FlotIQ
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Archivo original descargado de OMIE
FILE_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "omie"
    / "marginalpdbc_20261015.1"
)


def inspect_file():
    if not FILE_PATH.is_file():
        print(f"ERROR: No se encuentra el archivo:\n{FILE_PATH}")
        return

    content = FILE_PATH.read_bytes()

    print("=== FlotIQ | Inspección de OMIE ===")
    print(f"Archivo: {FILE_PATH.name}")
    print(f"Tamaño: {len(content)} bytes")
    print(f"SHA-256: {hashlib.sha256(content).hexdigest()}")

    # Inspección inicial sin modificar los datos originales.
    try:
        text = content.decode("latin-1")
    except UnicodeError as error:
        print(f"No se pudo decodificar el archivo: {error}")
        return

    print("\nPrimeras 12 líneas del fichero:\n")

    for line in text.splitlines()[:12]:
        print(line)

    print("\nInspección finalizada.")


if __name__ == "__main__":
    inspect_file()
