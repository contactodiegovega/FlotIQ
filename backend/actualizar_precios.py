
# FLOTIQ | ACTUALIZAR PRECIOS ELECTRICOS DE OMIE

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RUTA_SALIDA = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "omie_precios_actualizados.parquet"
)

ZONA = ZoneInfo("Europe/Madrid")

URL_OMIE = "https://www.omie.es/es/file-download"


def descargar_dia(fecha):
    """
    Descarga los precios del mercado diario español.

    OMIE puede publicar periodos de 15 minutos.
    Los agregamos a horas para mantener la
    frecuencia del modelo ML de FlotIQ.
    """

    nombre = f"marginalpdbc_{fecha:%Y%m%d}.1"

    respuesta = requests.get(
        URL_OMIE,
        params={
            "parents": "marginalpdbc",
            "filename": nombre,
        },
        timeout=30,
        headers={
            "User-Agent": "FlotIQ/0.1",
        },
    )

    if respuesta.status_code in (404, 410):
        print(f"  Archivo no publicado: {fecha}")
        return None

    respuesta.raise_for_status()

    texto = respuesta.content.decode(
        "utf-8-sig",
        errors="replace",
    )

    if not texto.lstrip().upper().startswith(
        "MARGINALPDBC;"
    ):
        print(f"  Formato no reconocido: {fecha}")
        return None

    registros = []

    for linea in texto.splitlines():
        partes = [
            elemento.strip()
            for elemento in linea.split(";")
        ]

        if len(partes) < 6:
            continue

        if not all(
            partes[i].isdigit()
            for i in range(4)
        ):
            continue

        anio = int(partes[0])
        mes = int(partes[1])
        dia = int(partes[2])
        periodo = int(partes[3])

        if (anio, mes, dia) != (
            fecha.year,
            fecha.month,
            fecha.day,
        ):
            raise ValueError(
                f"{nombre}: fecha interna incorrecta."
            )

        try:
            precio_espana = float(
                partes[5].replace(",", ".")
            )
        except ValueError as error:
            raise ValueError(
                f"{nombre}: precio español incorrecto "
                f"en periodo {periodo}."
            ) from error

        registros.append({
            "periodo": periodo,
            "price_eur_mwh": precio_espana,
        })

    if not registros:
        print(f"  Sin precios disponibles: {fecha}")
        return None

    datos = pd.DataFrame(registros).sort_values(
        "periodo"
    )

    # Fechas locales con zona horaria de Madrid.
    inicio = pd.Timestamp(fecha).tz_localize(
        "Europe/Madrid"
    )

    fin = pd.Timestamp(
        fecha + timedelta(days=1)
    ).tz_localize(
        "Europe/Madrid"
    )

    horas = pd.date_range(
        start=inicio,
        end=fin,
        freq="h",
        inclusive="left",
    )

    cuartos = pd.date_range(
        start=inicio,
        end=fin,
        freq="15min",
        inclusive="left",
    )

    # Normalmente hay 96 periodos.
    # Con cambios horarios pueden ser 92 o 100.
    periodos_esperados = len(cuartos)

    periodos_encontrados = (
        datos["periodo"].tolist()
    )

    if periodos_encontrados != list(
        range(1, periodos_esperados + 1)
    ):
        raise ValueError(
            f"{fecha}: se esperaban "
            f"{periodos_esperados} periodos de "
            f"15 minutos y se encontraron "
            f"{len(datos)}. "
            "Comprueba el archivo de OMIE."
        )

    datos["datetime_utc"] = (
        cuartos.tz_convert("UTC")
    )

    datos = datos[
        ["datetime_utc", "price_eur_mwh"]
    ].copy()

    # Media aritmética de los cuatro precios
    # de 15 minutos correspondientes a cada hora.
    datos["hora_utc"] = (
        datos["datetime_utc"].dt.floor("h")
    )

    horario = (
        datos.groupby(
            "hora_utc",
            as_index=False,
        )["price_eur_mwh"]
        .mean()
        .rename(
            columns={
                "hora_utc": "datetime_utc",
            }
        )
    )

    if len(horario) != len(horas):
        raise ValueError(
            f"{fecha}: la agregación horaria "
            "ha producido un número incorrecto "
            "de horas."
        )

    if not (
        datos.groupby("hora_utc").size() == 4
    ).all():
        raise ValueError(
            f"{fecha}: alguna hora no contiene "
            "cuatro precios de 15 minutos."
        )

    horario["fuente"] = "OMIE_mercado_diario_ES"
    horario["granularidad_original"] = "15min"
    horario["granularidad_final"] = "1h"

    return horario


def actualizar_precios():
    hoy = datetime.now(ZONA).date()

    # Últimos 10 días, hoy y mañana.
    fechas = [
        hoy + timedelta(days=dias)
        for dias in range(-10, 2)
    ]

    nuevos = []

    for fecha in fechas:
        print(f"Consultando {fecha}...")

        try:
            datos = descargar_dia(fecha)

            if datos is None:
                continue

            nuevos.append(datos)

            print(
                f"  Correcto: {len(datos)} "
                "precios horarios descargados"
            )

        except requests.RequestException as error:
            print(
                f"  Error de conexión: {error}"
            )

        except ValueError as error:
            print(
                f"  Error de validación: {error}"
            )
            raise

    if not nuevos:
        print(
            "\nNo se han encontrado nuevos "
            "precios válidos."
        )
        return

    actualizados = pd.concat(
        nuevos,
        ignore_index=True,
    )

    if RUTA_SALIDA.exists():
        anteriores = pd.read_parquet(
            RUTA_SALIDA
        )

        actualizados = pd.concat(
            [anteriores, actualizados],
            ignore_index=True,
        )

    actualizados["datetime_utc"] = (
        pd.to_datetime(
            actualizados["datetime_utc"],
            utc=True,
        )
    )

    actualizados = (
        actualizados
        .drop_duplicates(
            subset=["datetime_utc"],
            keep="last",
        )
        .sort_values("datetime_utc")
        .reset_index(drop=True)
    )

    if actualizados[
        "price_eur_mwh"
    ].isna().any():
        raise ValueError(
            "Existen precios horarios vacíos."
        )

    RUTA_SALIDA.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    actualizados.to_parquet(
        RUTA_SALIDA,
        index=False,
    )

    print(
        "\nFLOTIQ | ACTUALIZACION COMPLETADA"
    )

    print(
        "Precios horarios almacenados:",
        len(actualizados),
    )

    print(
        "Primera hora:",
        actualizados["datetime_utc"].min(),
    )

    print(
        "Última hora:",
        actualizados["datetime_utc"].max(),
    )

    print(
        "Archivo:",
        RUTA_SALIDA,
    )


if __name__ == "__main__":
    actualizar_precios()
