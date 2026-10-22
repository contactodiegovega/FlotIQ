
# FLOTIQ | ESCENARIOS DE PRECIOS PARA SEMANAS FUTURAS

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, Query


router = APIRouter(prefix="/api/escenarios", tags=["Escenarios"])

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RUTA_PRECIOS = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "omie_ml_hourly.parquet"
)

ZONA_HORARIA = "Europe/Madrid"


@router.get("/precios")
def generar_escenario_precios(
    fecha: date = Query(
        ...,
        description="Lunes de la semana: AAAA-MM-DD",
    )
):
    # Solo trabajamos con semanas completas.
    if fecha.weekday() != 0:
        raise HTTPException(
            status_code=400,
            detail="Selecciona un lunes como inicio de semana.",
        )

    hoy = pd.Timestamp.now(tz=ZONA_HORARIA).date()
    lunes_actual = hoy - timedelta(days=hoy.weekday())

    if fecha < lunes_actual:
        raise HTTPException(
            status_code=400,
            detail="Selecciona la semana actual o una futura.",
        )

    if not RUTA_PRECIOS.exists():
        raise HTTPException(
            status_code=404,
            detail="No se encuentra el dataset de precios OMIE.",
        )

    df = pd.read_parquet(
        RUTA_PRECIOS,
        columns=["datetime_utc", "price_eur_mwh"],
    )

    df["datetime_utc"] = pd.to_datetime(
        df["datetime_utc"],
        utc=True,
    )

    df["price_eur_mwh"] = pd.to_numeric(
        df["price_eur_mwh"],
        errors="coerce",
    )

    # Solo observaciones anteriores a la emisión.
    ahora_utc = pd.Timestamp.now(tz="UTC")

    df = df[
        (df["datetime_utc"] < ahora_utc)
        & df["price_eur_mwh"].notna()
    ].copy()

    if df.empty:
        raise HTTPException(
            status_code=422,
            detail="No hay precios históricos disponibles.",
        )

    # Identificar día y hora en España.
    hora_local = df["datetime_utc"].dt.tz_convert(
        ZONA_HORARIA
    )

    df["dia_semana"] = hora_local.dt.dayofweek
    df["hora_dia"] = hora_local.dt.hour

    # Construir perfiles históricos por día y hora.
    perfiles = (
        df.groupby(["dia_semana", "hora_dia"])
        .agg(
            central=("price_eur_mwh", "median"),
            bajo=(
                "price_eur_mwh",
                lambda x: x.quantile(0.25),
            ),
            alto=(
                "price_eur_mwh",
                lambda x: x.quantile(0.75),
            ),
            muestras=("price_eur_mwh", "size"),
        )
    )

    # Semana futura en hora local.
    inicio = pd.Timestamp(fecha).tz_localize(
        ZONA_HORARIA
    )
    fin = inicio + pd.DateOffset(days=7)

    horas_futuras = pd.date_range(
        start=inicio,
        end=fin,
        freq="h",
        inclusive="left",
    )

    resultado = []

    for instante in horas_futuras:
        clave = (instante.weekday(), instante.hour)

        if clave not in perfiles.index:
            raise HTTPException(
                status_code=422,
                detail=f"Faltan datos históricos para {clave}.",
            )

        perfil = perfiles.loc[clave]

        resultado.append({
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

    return {
        "tipo_datos": "escenario_historico",
        "metodo": "percentiles_por_dia_y_hora",
        "semana_inicio": fecha.isoformat(),
        "semana_fin": (
            fecha + timedelta(days=6)
        ).isoformat(),
        "horas": len(resultado),
        "precio_medio_escenario": round(
            sum(
                r["precio_central_eur_mwh"]
                for r in resultado
            ) / len(resultado),
            2,
        ),
        "aviso": (
            "Escenario basado en distribuciones historicas. "
            "No es una prediccion validada de precios futuros. "
            "Los percentiles no son intervalos de confianza."
        ),
        "registros": resultado,
    }
