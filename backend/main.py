
# FLOTIQ | API PRINCIPAL

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="FlotIQ API",
    description="Predicción energética y optimización de recargas",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/")
def inicio():
    return {
        "aplicacion": "FlotIQ",
        "estado": "operativa",
        "mensaje": "Backend conectado correctamente",
    }


@app.get("/api/flota")
def obtener_flota():
    return {
        "vehiculos": 50,
        "conductores": 80,
        "cargadores": 20,
        "potencia_maxima_kw": 150,
        "capacidad_bateria_kwh": 60,
        "tipo_datos": "configuracion_simulada",
    }

# FLOTIQ | RESULTADOS DE OPTIMIZACION SEMANAL

from pathlib import Path

import pandas as pd
from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RESULTADOS_SEMANA = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "comparacion_recargas_semana.csv"
)


@app.get("/api/resultados/semana")
def obtener_resultados_semana():
    if not RESULTADOS_SEMANA.exists():
        raise HTTPException(
            status_code=404,
            detail="No se encuentra el archivo de resultados.",
        )

    try:
        df = pd.read_csv(RESULTADOS_SEMANA)

        # Devolvemos el contenido tal como está guardado.
        # No inventamos métricas ni modificamos resultados.
        return {
            "tipo_datos": "simulacion_historica",
            "archivo": RESULTADOS_SEMANA.name,
            "columnas": df.columns.tolist(),
            "registros": df.where(
                pd.notna(df), None
            ).to_dict(orient="records"),
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Error leyendo resultados: {error}",
        )

# FLOTIQ | CONSULTAR CALENDARIO DE RECARGAS

from typing import Literal
from fastapi import Query

@app.get("/api/recargas")
def obtener_recargas(
    estrategia: Literal["baseline", "ml"] = "baseline",
    vehiculo: str = Query(default="V001", pattern=r"^V\d{3}$"),
):
    archivos = {
        "baseline": "recargas_baseline_semana_con_cargadores.parquet",
        "ml": "recargas_ml_semana_con_cargadores.parquet",
    }

    ruta = (
        PROJECT_ROOT
        / "data"
        / "processed"
        / archivos[estrategia]
    )

    if not ruta.exists():
        raise HTTPException(
            status_code=404,
            detail="No se encontró el archivo de recargas.",
        )

    df = pd.read_parquet(ruta)

    vehiculos = sorted(df["vehicle_id"].unique().tolist())

    if vehiculo not in vehiculos:
        raise HTTPException(
            status_code=404,
            detail=f"Vehículo {vehiculo} no encontrado.",
        )

    datos = (
        df.loc[df["vehicle_id"] == vehiculo]
        .sort_values("hora")
        .copy()
    )

    registros = []

    for fila in datos.itertuples(index=False):
       # FLOTIQ | DEVOLVER RECARGAS CON CARGADOR ASIGNADO

        registros.append({
            "hora": pd.Timestamp(fila.hora).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            "recarga_red_kwh": float(fila.recarga_red_kwh),
            "energia_bateria_kwh": float(
                fila.energia_bateria_kwh
            ),
            "soc_pct": float(fila.soc_pct),
            "conectado": float(fila.conectado),
            "coste_real_eur": float(fila.coste_real_eur),
            "cargador_id": (
                str(fila.cargador_id)
                if pd.notna(fila.cargador_id)
                else None
            ),
        })
    return {
        "tipo_datos": "simulacion_historica",
        "estrategia": estrategia,
        "vehiculo": vehiculo,
        "vehiculos_disponibles": vehiculos,
        "horas": len(registros),
        "energia_total_kwh": round(
            float(datos["recarga_red_kwh"].sum()), 2
        ),
        "coste_total_eur": round(
            float(datos["coste_real_eur"].sum()), 2
        ),
        "registros": registros,
    }

# FLOTIQ | VISTA GENERAL DE RECARGAS DE LA FLOTA

@app.get("/api/recargas/flota")
def obtener_calendario_flota(
    estrategia: Literal["baseline", "ml"] = "baseline",
):
    archivos = {
        "baseline": "recargas_baseline_semana.parquet",
        "ml": "recargas_ml_semana.parquet",
    }

    ruta = (
        PROJECT_ROOT
        / "data"
        / "processed"
        / archivos[estrategia]
    )

    if not ruta.exists():
        raise HTTPException(
            status_code=404,
            detail="No se encontraron los datos de recarga.",
        )

    df = pd.read_parquet(ruta).copy()

    df["hora"] = pd.to_datetime(df["hora"])
    df["fecha"] = df["hora"].dt.strftime("%Y-%m-%d")
    df["recargando"] = (
        df["recarga_red_kwh"] > 0.001
    ).astype(int)

    resumen = (
        df.groupby(["vehicle_id", "fecha"], as_index=False)
        .agg(
            energia_kwh=("recarga_red_kwh", "sum"),
            coste_eur=("coste_real_eur", "sum"),
            horas_recarga=("recargando", "sum"),
        )
    )

    vehiculos = []

    for vehiculo, datos in resumen.groupby(
        "vehicle_id", sort=True
    ):
        datos = datos.sort_values("fecha")

        vehiculos.append({
            "id": vehiculo,
            "energia_kwh": round(
                float(datos["energia_kwh"].sum()), 2
            ),
            "coste_eur": round(
                float(datos["coste_eur"].sum()), 2
            ),
            "horas_recarga": int(
                datos["horas_recarga"].sum()
            ),
            "dias": [
                {
                    "fecha": fila.fecha,
                    "energia_kwh": round(
                        float(fila.energia_kwh), 2
                    ),
                    "coste_eur": round(
                        float(fila.coste_eur), 2
                    ),
                    "horas_recarga": int(
                        fila.horas_recarga
                    ),
                }
                for fila in datos.itertuples(index=False)
            ],
        })

    return {
        "tipo_datos": "simulacion_historica",
        "estrategia": estrategia,
        "total_vehiculos": len(vehiculos),
        "energia_total_kwh": round(
            float(df["recarga_red_kwh"].sum()), 2
        ),
        "coste_total_eur": round(
            float(df["coste_real_eur"].sum()), 2
        ),
        "fechas": sorted(df["fecha"].unique().tolist()),
        "vehiculos": vehiculos,
    }

# FLOTIQ | OCUPACION HORARIA DE CARGADORES

@app.get("/api/cargadores/ocupacion")
def obtener_ocupacion_cargadores(
    estrategia: Literal["baseline", "ml"] = "baseline",
):
    archivos = {
        "baseline": "recargas_baseline_semana_con_cargadores.parquet",
        "ml": "recargas_ml_semana_con_cargadores.parquet",
    }

    ruta = (
        PROJECT_ROOT
        / "data"
        / "processed"
        / archivos[estrategia]
    )

    if not ruta.exists():
        raise HTTPException(
            status_code=404,
            detail="No se encontró el archivo de cargadores.",
        )

    df = pd.read_parquet(ruta).copy()
    df["hora"] = pd.to_datetime(df["hora"])

    activos = df[df["recarga_red_kwh"] > 0.01].copy()

    if activos["cargador_id"].isna().any():
        raise HTTPException(
            status_code=500,
            detail="Existen recargas sin cargador asignado.",
        )

    if activos.duplicated(["hora", "cargador_id"]).any():
        raise HTTPException(
            status_code=500,
            detail="Se detectaron cargadores duplicados por hora.",
        )

    ocupacion = (
        df.groupby("hora", as_index=False)
        .agg(
            potencia_kw=("recarga_red_kwh", "sum"),
            energia_kwh=("recarga_red_kwh", "sum"),
        )
        .sort_values("hora")
    )

    conteos = (
        activos.groupby("hora")["cargador_id"]
        .nunique()
        .to_dict()
    )

    horas = []

    for fila in ocupacion.itertuples(index=False):
        potencia = float(fila.potencia_kw)
        cargadores = int(conteos.get(fila.hora, 0))

        horas.append({
            "hora": pd.Timestamp(fila.hora).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            "potencia_kw": round(potencia, 2),
            "energia_kwh": round(
                float(fila.energia_kwh), 2
            ),
            "cargadores_ocupados": cargadores,
            "ocupacion_pct": round(
                cargadores / 20 * 100, 2
            ),
            "uso_potencia_pct": round(
                potencia / 150 * 100, 2
            ),
        })

    return {
        "tipo_datos": "simulacion_historica",
        "estrategia": estrategia,
        "total_cargadores": 20,
        "potencia_maxima_kw": 150,
        "max_cargadores_simultaneos": max(
            h["cargadores_ocupados"] for h in horas
        ),
        "max_potencia_kw": max(
            h["potencia_kw"] for h in horas
        ),
        "horas": horas,
    }
from backend.escenarios import router as escenarios_router

app.include_router(escenarios_router)