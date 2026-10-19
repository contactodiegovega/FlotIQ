
from datetime import date, timedelta
from pathlib import Path
import csv
import time

import requests

from parse_omie_hourly import parse_omie_hourly


PROJECT_ROOT = Path(__file__).resolve().parents[3]

OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "omie_hourly"
REPORT_DIR = PROJECT_ROOT / "data" / "processed" / "omie_reports"

BASE_URL = "https://www.omie.es/es/file-download"

START_DATE = date(2023, 1, 1)
END_DATE = date(2025, 9, 30)

MAX_VERSION = 4
PAUSE_SECONDS = 1
MAX_RETRIES = 3


def validate_file(path, target_date):
    df = parse_omie_hourly(path)

    if not (df["market_date"].dt.date == target_date).all():
        raise ValueError("Fecha incorrecta en el fichero")

    return len(df)


def download_day(session, target_date):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    prefix = f"marginalpdbc_{target_date:%Y%m%d}"

    # Comprobar primero los archivos existentes.
    existing = sorted(
        (
            p for p in OUTPUT_DIR.glob(f"{prefix}.*")
            if p.suffix[1:].isdigit()
        ),
        key=lambda p: int(p.suffix[1:]),
        reverse=True,
    )

    for path in existing:
        try:
            records = validate_file(path, target_date)
            print(f"EXISTENTE: {path.name} ({records} registros)")
            return target_date, path.name, "existing", records, ""
        except (ValueError, OSError) as error:
            print(f"Archivo local no válido: {path.name}: {error}")

    # Probar otras versiones cuando la solicitada no existe.
    for version in range(1, MAX_VERSION + 1):
        filename = f"{prefix}.{version}"
        path = OUTPUT_DIR / filename
        temp_path = OUTPUT_DIR / f"{filename}.tmp"

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = session.get(
                    BASE_URL,
                    params={
                        "parents": "marginalpdbc",
                        "filename": filename,
                    },
                    timeout=30,
                )

                if response.status_code == 404:
                    break

                response.raise_for_status()

                content = response.content

                if not content.lstrip().startswith(
                    b"MARGINALPDBC;"
                ):
                    raise ValueError(
                        "Contenido vacío o formato inesperado"
                    )

                # Validar antes de guardar el archivo original.
                temp_path.write_bytes(content)
                records = validate_file(temp_path, target_date)

                temp_path.replace(path)

                print(f"DESCARGADO: {filename} ({records} registros)")
                return (
                    target_date, filename, "downloaded", records, ""
                )

            except ValueError as error:
                # Un fichero inválido no mejorará por
                # repetir la misma descarga.
                print(f"Versión no válida {filename}: {error}")
                break

            except (requests.RequestException, OSError) as error:
                if attempt < MAX_RETRIES:
                    print(
                        f"Reintento {attempt}/{MAX_RETRIES}: "
                        f"{filename}"
                    )
                    time.sleep(2 * attempt)
                else:
                    print(f"ERROR de conexión: {filename}: {error}")
                    return (
                        target_date, filename, "error", 0, str(error)
                    )

            finally:
                temp_path.unlink(missing_ok=True)

        time.sleep(PAUSE_SECONDS)

    print(f"NO ENCONTRADO: {target_date}")
    return (
        target_date, "", "not_found", 0,
        "No se encontró una versión válida entre 1 y 4"
    )


def save_report(results, year, month):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report_path = REPORT_DIR / f"omie_hourly_{year}_{month:02d}.csv"

    with report_path.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.writer(file)
        writer.writerow([
            "date", "filename", "status", "records", "error"
        ])

        for target_date, filename, status, records, error in results:
            writer.writerow([
                target_date.isoformat(),
                filename,
                status,
                records,
                error,
            ])

    return report_path


def main():
    current = START_DATE
    monthly_results = []
    all_results = []

    with requests.Session() as session:
        session.headers.update({
            "User-Agent": "FlotIQ/0.1"
        })

        while current <= END_DATE:
            print(f"\n--- {current} ---")

            result = download_day(session, current)

            monthly_results.append(result)
            all_results.append(result)

            next_date = current + timedelta(days=1)

            # Guardar un informe al terminar cada mes.
            if (
                next_date.month != current.month
                or next_date.year != current.year
                or current == END_DATE
            ):
                report = save_report(
                    monthly_results,
                    current.year,
                    current.month,
                )

                correct = sum(
                    r[2] in ("existing", "downloaded")
                    for r in monthly_results
                )

                print("\n=== RESUMEN MENSUAL ===")
                print(f"Mes: {current.year}-{current.month:02d}")
                print(f"Días correctos: {correct}")
                print(
                    f"Días con errores: "
                    f"{len(monthly_results) - correct}"
                )
                print(f"Informe: {report}")

                monthly_results = []

            current = next_date

            if current <= END_DATE:
                time.sleep(PAUSE_SECONDS)

    correct = sum(
        r[2] in ("existing", "downloaded")
        for r in all_results
    )

    print("\n=== RESUMEN HISTÓRICO FLOTIQ ===")
    print(f"Días solicitados: {len(all_results)}")
    print(f"Días correctos: {correct}")
    print(f"Días con errores: {len(all_results) - correct}")
    print(f"Registros: {sum(r[3] for r in all_results)}")


if __name__ == "__main__":
    main()
