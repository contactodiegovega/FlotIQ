
# FLOTIQ | ESCENARIOS DE PRECIOS CON ESTACIONALIDAD

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Query


router = APIRouter(
    prefix="/api/escenarios",
    tags=["Escenarios"],
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RUTA_PRECIOS = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "omie_ml_hourly.parquet"
)

ZONA_HORARIA = "Europe/Madrid"

# Ventana histórica alrededor de la fecha equivalente.
VENTANA_ESTACIONAL_DIAS = 21

# Año bisiesto de referencia para admitir el 29 de febrero.
DIAS_TEMPORADA = {
    (dia.month, dia.day): dia.dayofyear
    for dia in pd.date_range(
        "2024-01-01",
        "2024-12-31",
        freq="D",
    )
}


def numero_dia_temporada(mes, dia):
    return DIAS_TEMPORADA[(int(mes), int(dia))]


@router.get("/precios")
def generar_escenario_precios(
    fecha: date = Query(
        ...,
        description="Lunes de la semana: AAAA-MM-DD",
    ),
):
    if fecha.weekday() != 0:
        raise HTTPException(
            status_code=400,
            detail="Selecciona un lunes como inicio de semana.",
        )

    hoy = pd.Timestamp.now(
        tz=ZONA_HORARIA
    ).date()

    lunes_actual = hoy - timedelta(
        days=hoy.weekday()
    )

    if fecha < lunes_actual:
        raise HTTPException(
            status_code=400,
            detail="Selecciona la semana actual o una futura.",
        )

    if not RUTA_PRECIOS.exists():
        raise HTTPException(
            status_code=404,
            detail="No se encuentra el dataset OMIE.",
        )

    df = pd.read_parquet(
        RUTA_PRECIOS,
        columns=[
            "datetime_utc",
            "price_eur_mwh",
        ],
    )

    df["datetime_utc"] = pd.to_datetime(
        df["datetime_utc"],
        utc=True,
    )

    df["price_eur_mwh"] = pd.to_numeric(
        df["price_eur_mwh"],
        errors="coerce",
    )

    ahora_utc = pd.Timestamp.now(tz="UTC")

    df = df.loc[
        (df["datetime_utc"] < ahora_utc)
        & df["price_eur_mwh"].notna()
    ].copy()

    if df.empty:
        raise HTTPException(
            status_code=422,
            detail="No existen precios históricos utilizables.",
        )

    local = df["datetime_utc"].dt.tz_convert(
        ZONA_HORARIA
    )

    df["dia_semana"] = local.dt.dayofweek
    df["hora_dia"] = local.dt.hour
    df["mes"] = local.dt.month
    df["dia_mes"] = local.dt.day

    # Día del año normalizado sobre un calendario
    # de 366 días para comparar distintas anualidades.
    df["dia_temporada"] = [
        numero_dia_temporada(mes, dia)
        for mes, dia in zip(
            df["mes"],
            df["dia_mes"],
        )
    ]

    inicio = pd.Timestamp(fecha).tz_localize(
        ZONA_HORARIA
    )

    fin = pd.Timestamp(
        fecha + timedelta(days=7)
    ).tz_localize(ZONA_HORARIA)

    horas_futuras = pd.date_range(
        start=inicio,
        end=fin,
        freq="h",
        inclusive="left",
    )

    resultados = []

    # Cada día utiliza un perfil propio basado en
    # fechas históricas próximas dentro del año.
    for fecha_dia in sorted({
        instante.date()
        for instante in horas_futuras
    }):
        objetivo_temporada = numero_dia_temporada(
            fecha_dia.month,
            fecha_dia.day,
        )

        distancia = (
            df["dia_temporada"] - objetivo_temporada
        ).abs()

        # Distancia circular: diciembre y enero
        # también pueden ser fechas próximas.
        distancia = distancia.where(
            distancia <= 183,
            366 - distancia,
        )

        historico_dia = df.loc[
            (distancia <= VENTANA_ESTACIONAL_DIAS)
            & (
                df["dia_semana"]
                == fecha_dia.weekday()
            )
        ]

        if historico_dia.empty:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"No hay histórico suficiente para "
                    f"{fecha_dia.isoformat()}."
                ),
            )

        perfiles = (
            historico_dia
            .groupby("hora_dia")["price_eur_mwh"]
            .agg(
                central="median",
                bajo=lambda x: x.quantile(0.25),
                alto=lambda x: x.quantile(0.75),
                muestras="size",
            )
        )

        horas_del_dia = [
            instante
            for instante in horas_futuras
            if instante.date() == fecha_dia
        ]

        for instante in horas_del_dia:
            hora = instante.hour

            if hora not in perfiles.index:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Faltan precios históricos para "
                        f"la hora {hora} del "
                        f"{fecha_dia.isoformat()}."
                    ),
                )

            perfil = perfiles.loc[hora]

            resultados.append({
                "fecha": instante.isoformat(),
                "precio_central_eur_mwh": round(
                    float(perfil["central"]), 2
                ),
                "precio_bajo_eur_mwh": round(
                    float(perfil["bajo"]), 2
                ),
                "precio_alto_eur_mwh": round(
                    float(perfil["alto"]), 2
                ),
                "muestras_historicas": int(
                    perfil["muestras"]
                ),
            })

    precio_medio = (
        sum(
            r["precio_central_eur_mwh"]
            for r in resultados
        )
        / len(resultados)
    )

    return {
        "tipo_datos": "escenario_historico_estacional",
        "metodo": "mediana_historica_estacional_21_dias",
        "ventana_estacional_dias": VENTANA_ESTACIONAL_DIAS,
        "semana_inicio": fecha.isoformat(),
        "semana_fin": (
            fecha + timedelta(days=6)
        ).isoformat(),
        "horas": len(resultados),
        "precio_medio_escenario": round(
            precio_medio, 2
        ),
        "aviso": (
            "Escenario basado en precios históricos "
            "de fechas próximas dentro del año. "
            "No es una predicción validada de precios "
            "futuros. Los percentiles representan "
            "variabilidad histórica."
        ),
        "registros": resultados,
    }
