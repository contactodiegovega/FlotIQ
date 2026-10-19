

from datetime import date, timedelta
from pathlib import Path
import csv
import time

import requests

from parse_omie import parse_omie


PROJECT_ROOT = Path(__file__).resolve().parents[3]

OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "omie"
REPORT_DIR = PROJECT_ROOT / "data" / "processed"

BASE_URL = "https://www.omie.es/es/file-download"

# Versiones que probaremos si falta la primera.
MAX_VERSION = 4


def validate_file(path: Path, target_date: date):
    df = parse_omie(path)

    if not (df["market_date"].dt.date == target_date).all():
        raise ValueError("La fecha del archivo no coincide")

    return df


def download_omie(target_date: date):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    prefix = f"marginalpdbc_{target_date:%Y%m%d}"

    # Buscar archivos que ya tenemos descargados.
    existing = sorted(
        (
            path for path in OUTPUT_DIR.glob(f"{prefix}.*")
            if path.suffix[1:].isdigit()
        ),
        key=lambda path: int(path.suffix[1:]),
        reverse=True,
    )

    # Validar primero las copias existentes.
    for path in existing:
        try:
            df = validate_file(path, target_date)

            print(
                f"Ya existe: {path.name} | "
                f"{len(df)} registros"
            )

            return {
                "date": target_date.isoformat(),
                "filename": path.name,
                "status": "existing",
                "records": len(df),
            }

        except (ValueError, OSError) as error:
            print(f"Archivo local no válido: {path.name}: {error}")

    # Descargar probando diferentes versiones.
    for version in range(1, MAX_VERSION + 1):
        filename = f"{prefix}.{version}"
        output_path = OUTPUT_DIR / filename
        temp_path = OUTPUT_DIR / f"{filename}.tmp"

        print(f"Probando: {filename}")

        try:
            response = requests.get(
                BASE_URL,
                params={
                    "parents": "marginalpdbc",
                    "filename": filename,
                },
                timeout=30,
                headers={"User-Agent": "FlotIQ/0.1"},
            )

            if response.status_code == 404:
                continue

            response.raise_for_status()

            content = response.content

            if not content.lstrip().startswith(b"MARGINALPDBC;"):
                raise ValueError("Cabecera OMIE incorrecta")

            if not any(
                line.strip() == "*"
                for line in content.decode("latin-1").splitlines()
            ):
                raise ValueError("Falta el cierre del archivo")

            # Validar antes de guardar definitivamente.
            temp_path.write_bytes(content)
            df = validate_file(temp_path, target_date)

            temp_path.replace(output_path)

            print(
                f"Descargado: {filename} | "
                f"{len(df)} registros"
            )

            return {
                "date": target_date.isoformat(),
                "filename": filename,
                "status": "downloaded",
                "records": len(df),
            }

        except (requests.RequestException, ValueError, OSError) as error:
            print(f"Error: {error}")

            # Un error de conexión no debe confundirse
            # con una versión inexistente.
            return {
                "date": target_date.isoformat(),
                "filename": filename,
                "status": "error",
                "records": 0,
            }

        finally:
            temp_path.unlink(missing_ok=True)

        time.sleep(1)

    print(f"No se encontró ninguna versión: {prefix}")

    return {
        "date": target_date.isoformat(),
        "filename": "",
        "status": "not_found",
        "records": 0,
    }


def download_range(start_date: date, end_date: date):
    if end_date < start_date:
        raise ValueError("Rango de fechas incorrecto")

    results = []
    current_date = start_date

    while current_date <= end_date:
        result = download_omie(current_date)
        results.append(result)

        current_date += timedelta(days=1)

        if current_date <= end_date:
            time.sleep(1)

    # Guardar un informe reproducible.
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report_path = (
        REPORT_DIR
        / f"omie_download_{start_date:%Y%m%d}_{end_date:%Y%m%d}.csv"
    )

    with report_path.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "date", "filename", "status", "records"
            ],
        )

        writer.writeheader()
        writer.writerows(results)

    correct = sum(
        r["status"] in ("existing", "downloaded")
        for r in results
    )

    print("\n=== RESUMEN DE DESCARGA ===")
    print(f"Días correctos: {correct}")
    print(f"Días con errores: {len(results) - correct}")
    print(f"Registros totales: {sum(r['records'] for r in results)}")
    print(f"Informe: {report_path}")



if __name__ == "__main__":

    # Descargar el histórico por meses
    for year, month in [
        (2025, 10),
        (2025, 11),
        (2025, 12),
        (2026, 1),
        (2026, 2),
        (2026, 3),
        (2026, 4),
        (2026, 5),
        (2026, 6),
        (2026, 7),
        (2026, 8),
        (2026, 9),
    ]:
        import calendar

        last_day = calendar.monthrange(year, month)[1]

        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

        print(f"\n{'=' * 45}")
        print(f"DESCARGANDO {year}-{month:02d}")
        print(f"{'=' * 45}")

        download_range(start_date, end_date)
