
from pathlib import Path
from zipfile import ZipFile

PROJECT_ROOT = Path(__file__).resolve().parents[3]

ZIP_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "madrid_traffic"
    / "208627-130-transporte-ptomedida-historico-zip.zip"
)


def inspect_zip():
    if not ZIP_PATH.is_file():
        raise FileNotFoundError(
            f"No se encuentra el archivo: {ZIP_PATH}"
        )

    print("\n=== FlotIQ | TRÁFICO DE MADRID ===")
    print(f"Archivo: {ZIP_PATH.name}")
    print(f"Tamaño: {ZIP_PATH.stat().st_size / 1024**2:.2f} MB")

    with ZipFile(ZIP_PATH) as zip_file:
        files = [
            info for info in zip_file.infolist()
            if not info.is_dir()
        ]

        print(f"\nArchivos internos: {len(files)}")

        print("\nContenido del ZIP:")
        for info in files[:20]:
            size_mb = info.file_size / 1024**2

            print(
                f"- {info.filename} "
                f"({size_mb:.2f} MB)"
            )

        if len(files) > 20:
            print(
                f"\n... y {len(files) - 20} archivos más."
            )

        print("\nInspección completada.")


if __name__ == "__main__":
    inspect_zip()
