
# FLOTIQ | PREPARAR DATOS PARA LA PLANIFICACION FUTURA

from datetime import date, datetime

import pandas as pd

from backend.escenarios import generar_escenario_precios
from backend.operaciones import generar_operaciones_semana


def preparar_planificacion(fecha_inicio: str):
    """
    Genera los datos operativos y los precios
    de una semana futura.

    Todavía no ejecuta el optimizador.
    """

    fecha = date.fromisoformat(fecha_inicio)

    # 1. Obtener las operaciones simuladas.
    operaciones = generar_operaciones_semana(
        fecha_inicio
    )

    # 2. Obtener el escenario de precios.
    escenario = generar_escenario_precios(fecha)

    # 3. Convertir los precios a DataFrame.
    precios = pd.DataFrame(
        escenario["registros"]
    )

    # Convertir las fechas con zona horaria de Madrid
    # al formato local usado por las operaciones.
    precios["hora"] = pd.to_datetime(
        precios["fecha"],
        utc=True,
    ).dt.tz_convert(
        "Europe/Madrid"
    ).dt.tz_localize(None)

    precios = precios.rename(
        columns={
            "precio_central_eur_mwh": "price_eur_mwh"
        }
    )

    precios = precios[
        ["hora", "price_eur_mwh"]
    ].copy()

    # 4. Comprobar integridad temporal.
    if precios["hora"].duplicated().any():
        raise ValueError(
            "Existen horas duplicadas en los precios."
        )

    if operaciones.duplicated(
        ["vehicle_id", "hora"]
    ).any():
        raise ValueError(
            "Existen operaciones duplicadas."
        )

    horas_operaciones = set(
        operaciones["hora"]
    )

    horas_precios = set(
        precios["hora"]
    )

    if horas_operaciones != horas_precios:
        raise ValueError(
            "Las horas de operaciones y precios "
            "no coinciden."
        )

    if precios["price_eur_mwh"].isna().any():
        raise ValueError(
            "Existen precios eléctricos vacíos."
        )

    # 5. Unir para verificar cobertura.
    comprobacion = operaciones.merge(
        precios,
        on="hora",
        how="left",
        validate="many_to_one",
    )

    if comprobacion["price_eur_mwh"].isna().any():
        raise ValueError(
            "Hay operaciones sin precio eléctrico."
        )

    if len(comprobacion) != len(operaciones):
        raise ValueError(
            "Se ha modificado el número de registros."
        )

    return {
        "fecha_inicio": fecha_inicio,
        "operaciones": operaciones,
        "precios": precios,
        "escenario": escenario,
    }


if __name__ == "__main__":

    resultado = preparar_planificacion(
        "2026-11-23"
    )

    operaciones = resultado["operaciones"]
    precios = resultado["precios"]

    print("FLOTIQ | DATOS DE PLANIFICACION")
    print("Semana:", resultado["fecha_inicio"])

    print(
        "Vehículos:",
        operaciones["vehicle_id"].nunique(),
    )

    print(
        "Horas operativas:",
        operaciones["hora"].nunique(),
    )

    print(
        "Horas con precio:",
        len(precios),
    )

    print(
        "Registros:",
        len(operaciones),
    )

    print(
        "Consumo previsto simulado:",
        round(
            operaciones["energia_consumida_kwh"].sum(),
            2,
        ),
        "kWh",
    )

    print(
        "Precio central medio:",
        round(
            precios["price_eur_mwh"].mean(),
            2,
        ),
        "€/MWh",
    )

    print(
        "Coincidencia temporal:",
        "CORRECTA",
    )
