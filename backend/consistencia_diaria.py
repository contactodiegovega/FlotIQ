
"""FLOTIQ: consistencia de planificaciones diarias."""

from __future__ import annotations

import json
import math
import os
import shutil
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from backend.optimizador import (
    CAPACIDAD_BATERIA_KWH,
    EFICIENCIA_CARGA,
    SOC_MINIMO,
    SOC_OBJETIVO,
    optimizar_recargas,
)

BASE = Path(__file__).resolve().parents[1] / "data" / "processed"
BACKUPS = Path(__file__).resolve().parents[2] / "FlotIQ_respaldo_consistencia"
ZONA = "Europe/Madrid"

COLUMNAS = [
    "vehicle_id",
    "hora",
    "recarga_red_kwh",
    "energia_bateria_kwh",
    "conexion",
    "soc_pct",
    "coste_estimado_eur",
]


def _normalizar(df):
    resultado = df.copy()
    resultado["hora"] = pd.to_datetime(resultado["hora"], utc=True)

    if resultado["hora"].isna().any():
        raise ValueError("Horas incompletas")

    return resultado


def _dia(series):
    return series.dt.tz_convert(ZONA).dt.date


def _anterior(fecha, vehiculos, horas_primero):
    fecha_ant = fecha - timedelta(days=1)

    ruta = BASE / f"planificacion_ml_48h_{fecha_ant}.parquet"

    if not ruta.is_file():
        # El primer plan puede iniciar la cadena.
        # Los planes posteriores no pueden saltarse días.
        hay_historico = any(
            p.stem[-10:] < str(fecha_ant)
            for p in BASE.glob("planificacion_ml_48h_????-??-??.parquet")
        )

        if hay_historico:
            raise RuntimeError(
                f"Falta el plan consecutivo: {ruta.name}"
            )

        return None, None

    resumen = ruta.with_suffix(".json")

    if not resumen.is_file():
        raise RuntimeError(
            f"Falta el resumen de {ruta.name}"
        )

    meta = json.loads(
        resumen.read_text(encoding="utf-8")
    )

    if not meta.get("factibilidad_validada"):
        raise RuntimeError(
            "El plan anterior no está validado"
        )

    if meta.get("fecha_consulta") != str(fecha_ant):
        raise RuntimeError(
            "El plan anterior tiene otra fecha"
        )

    df = pd.read_parquet(ruta)

    necesarias = (set(COLUMNAS) - {"hora"}) | {
        "datetime_utc",
        "precio_predicho_eur_mwh",
        "energia_consumida_kwh",
        "disponible_carga",
    }

    if not necesarias.issubset(df.columns):
        raise RuntimeError(
            "Faltan columnas en el plan anterior"
        )

    df["datetime_utc"] = pd.to_datetime(
        df["datetime_utc"], utc=True
    )
    df["vehicle_id"] = df["vehicle_id"].astype(str)

    compartido = df.loc[
        _dia(df["datetime_utc"])
        == fecha + timedelta(days=1)
    ].copy()

    compartido = compartido.sort_values(
        ["datetime_utc", "vehicle_id"]
    )

    if (
        compartido.empty
        or compartido.duplicated(
            ["datetime_utc", "vehicle_id"]
        ).any()
        or set(compartido["vehicle_id"]) != set(vehiculos)
        or set(compartido["datetime_utc"]) != horas_primero
        or len(compartido)
        != len(vehiculos) * len(horas_primero)
    ):
        raise RuntimeError(
            "El día compartido está incompleto"
        )

    campos_numericos = [
        "recarga_red_kwh",
        "energia_bateria_kwh",
        "conexion",
        "soc_pct",
        "coste_estimado_eur",
        "precio_predicho_eur_mwh",
        "energia_consumida_kwh",
    ]

    for campo in campos_numericos:
        valores = pd.to_numeric(
            compartido[campo], errors="coerce"
        )

        if not np.isfinite(valores).all():
            raise RuntimeError(
                f"Dato inválido del día oficial: {campo}"
            )

    if compartido["disponible_carga"].isna().any():
        raise RuntimeError(
            "Disponibilidades no válidas"
        )

    return compartido, meta


def optimizar_48h_consistente(
    *,
    fecha_consulta: date,
    datos_operativos: pd.DataFrame,
    precios_horarios: pd.DataFrame,
    energia_final_objetivo: dict,
    energia_inicial_vehiculos: dict,
    tiempo_maximo_segundos: int = 180,
    soc_objetivo_primer_dia: float = 0.60,
    penalizacion_intermedia_eur_kwh: float = 0.25,
):
    """
    Conserva el día compartido y optimiza el nuevo día.

    Devuelve:
      resultado
      precios_efectivos
      informacion_consistencia
    """

    oper = _normalizar(datos_operativos)
    precios = _normalizar(precios_horarios)

    oper["vehicle_id"] = oper["vehicle_id"].astype(str)
    vehiculos = sorted(oper["vehicle_id"].unique())

    if set(vehiculos) != set(energia_inicial_vehiculos):
        raise ValueError(
            "Baterías iniciales incompletas"
        )

    primero = fecha_consulta + timedelta(days=1)
    segundo = fecha_consulta + timedelta(days=2)

    mask1 = _dia(oper["hora"]) == primero
    mask2 = _dia(oper["hora"]) == segundo

    horas1 = set(oper.loc[mask1, "hora"])
    horas2 = set(oper.loc[mask2, "hora"])

    if (
        not horas1
        or not horas2
        or set(oper["hora"]) != horas1 | horas2
        or set(precios["hora"]) != horas1 | horas2
        or precios["hora"].duplicated().any()
        or oper.duplicated(["vehicle_id", "hora"]).any()
        or len(oper)
        != len(vehiculos) * (len(horas1) + len(horas2))
    ):
        raise RuntimeError(
            "El horizonte de 48 horas está incompleto"
        )

    dia_fijo, meta = _anterior(
        fecha_consulta, vehiculos, horas1
    )

    # CASO 1: primer plan de toda la cadena
    if dia_fijo is None:
        resultado = optimizar_recargas(
            datos_operativos=oper,
            precios_horarios=precios,
            energia_final_objetivo=energia_final_objetivo,
            energia_inicial_vehiculos=energia_inicial_vehiculos,
            tiempo_maximo_segundos=tiempo_maximo_segundos,
            objetivo_final_flexible=True,
            penalizacion_deficit_eur_kwh=1.0,
            soc_objetivo_primer_dia=soc_objetivo_primer_dia,
            penalizacion_intermedia_eur_kwh=penalizacion_intermedia_eur_kwh,
        )

        return resultado, precios, {
            "dia_fijo": None,
            "origen": None,
        }

    # CASO 2: existe un plan anterior.
    # Debemos conservar exactamente el día compartido.

    actuales = oper.loc[
        mask1,
        [
            "vehicle_id",
            "hora",
            "energia_consumida_kwh",
            "disponible_carga",
        ],
    ]

    oficiales = dia_fijo.rename(
        columns={"datetime_utc": "hora"}
    )[
        [
            "vehicle_id",
            "hora",
            "energia_consumida_kwh",
            "disponible_carga",
        ]
    ]

    pareja = actuales.merge(
        oficiales,
        on=["vehicle_id", "hora"],
        validate="one_to_one",
        suffixes=("_actual", "_oficial"),
        how="outer",
        indicator=True,
    )

    if (
        not pareja["_merge"].eq("both").all()
        or not np.allclose(
            pareja["energia_consumida_kwh_actual"],
            pareja["energia_consumida_kwh_oficial"],
            atol=1e-5,
            rtol=0,
        )
        or not pareja["disponible_carga_actual"].equals(
            pareja["disponible_carga_oficial"]
        )
    ):
        raise RuntimeError(
            "El consumo o la disponibilidad del día "
            "ya publicado han cambiado"
        )

    # Comprobar continuidad inicial de batería.

    inicios = (
        dia_fijo.sort_values("datetime_utc")
        .groupby("vehicle_id")
        .head(1)
    )

    for fila in inicios.itertuples(index=False):
        energia_inicio = (
            float(fila.energia_bateria_kwh)
            + float(fila.energia_consumida_kwh)
            - float(fila.recarga_red_kwh)
            * EFICIENCIA_CARGA
        )

        if abs(
            energia_inicio
            - float(energia_inicial_vehiculos[fila.vehicle_id])
        ) > 0.025:
            raise RuntimeError(
                f"Continuidad incompatible en {fila.vehicle_id}"
            )

    # También debemos conservar el precio aplicado
    # para que coincidan los costes del día.

    por_hora = dia_fijo.groupby(
        "datetime_utc"
    )["precio_predicho_eur_mwh"].agg(
        ["min", "max", "first"]
    )

    if (
        (por_hora["max"] - por_hora["min"]).abs()
        > 1e-6
    ).any():
        raise RuntimeError(
            "Precios diferentes entre vehículos"
        )

    efectivos = precios.set_index("hora").copy()

    efectivos.loc[
        por_hora.index, "price_eur_mwh"
    ] = por_hora["first"].to_numpy()

    efectivos = efectivos.reset_index()

    # Recuperar los registros exactos del día oficial.

    fijos = dia_fijo.rename(
        columns={"datetime_utc": "hora"}
    )[COLUMNAS].copy()

    # Baterías reales simuladas al terminar el día fijo.

    ultimos = (
        dia_fijo.sort_values("datetime_utc")
        .groupby("vehicle_id")
        .tail(1)
    )

    bateria_dia2 = dict(
        zip(
            ultimos["vehicle_id"],
            ultimos["energia_bateria_kwh"].astype(float),
        )
    )

    # Optimizar solamente el día nuevo.

    nuevo = optimizar_recargas(
        datos_operativos=oper.loc[mask2].copy(),
        precios_horarios=efectivos.loc[
            _dia(efectivos["hora"]) == segundo
        ].copy(),
        energia_final_objetivo=energia_final_objetivo,
        energia_inicial_vehiculos=bateria_dia2,
        tiempo_maximo_segundos=tiempo_maximo_segundos,
        objetivo_final_flexible=True,
        penalizacion_deficit_eur_kwh=1.0,
    )

    if not nuevo.get("factibilidad_validada"):
        raise RuntimeError(
            "El segundo día no tiene un plan factible"
        )

    # Unir día oficial + día nuevo.

    juntos = pd.concat(
        [fijos, nuevo["recargas"][COLUMNAS]],
        ignore_index=True,
    )

    juntos["hora"] = pd.to_datetime(
        juntos["hora"], utc=True
    )

    juntos = juntos.sort_values(
        ["hora", "vehicle_id"]
    ).reset_index(drop=True)

    if (
        len(juntos)
        != len(vehiculos) * (len(horas1) + len(horas2))
        or juntos.duplicated(
            ["vehicle_id", "hora"]
        ).any()
    ):
        raise RuntimeError(
            "Plan combinado incompleto"
        )

    resultado = {
        **nuevo,
        "recargas": juntos,
        "vehiculos": len(vehiculos),
        "horas": len(horas1) + len(horas2),
        "coste_estimado_eur": round(
            float(juntos["coste_estimado_eur"].sum()), 2
        ),
        "energia_total_kwh": round(
            float(juntos["recarga_red_kwh"].sum()), 2
        ),
        "optimalidad_certificada": (
            bool(meta.get("optimalidad_certificada"))
            and bool(nuevo["optimalidad_certificada"])
        ),
        "factibilidad_validada": True,
    }

    return resultado, efectivos, {
        "dia_fijo": str(primero),
        "origen": str(
            fecha_consulta - timedelta(days=1)
        ),
    }


def publicar_consistente(
    plan: pd.DataFrame,
    resumen: dict,
    fecha: date,
    info: dict,
) -> Path:
    """Publica el plan y el estado de baterías del siguiente día."""

    siguiente = BASE / (
        f"planificacion_ml_48h_"
        f"{fecha + timedelta(days=1)}.parquet"
    )

    if siguiente.exists():
        raise RuntimeError(
            f"Existe {siguiente.name}. "
            "No se puede modificar un plan con sucesores."
        )

    dia1 = fecha + timedelta(days=1)
    dia2 = fecha + timedelta(days=2)

    df = plan.copy()
    df["datetime_utc"] = pd.to_datetime(
        df["datetime_utc"], utc=True
    )

    cierres = (
        df.loc[_dia(df["datetime_utc"]) == dia1]
        .sort_values("datetime_utc")
        .groupby("vehicle_id")
        .tail(1)
    )

    if len(cierres) != resumen["vehiculos"]:
        raise RuntimeError(
            "Faltan estados de batería del primer día"
        )

    energias = dict(
        zip(
            cierres["vehicle_id"].astype(str),
            cierres["energia_bateria_kwh"].astype(float),
        )
    )

    minimo = CAPACIDAD_BATERIA_KWH * SOC_MINIMO
    maximo = CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO

    if not all(
        math.isfinite(e)
        and minimo - 0.025 <= e <= maximo + 0.025
        for e in energias.values()
    ):
        raise RuntimeError(
            "Baterías fuera de límites"
        )

    ruta_plan = BASE / (
        f"planificacion_ml_48h_{fecha}.parquet"
    )

    ruta_resumen = ruta_plan.with_suffix(".json")

    ruta_estado = BASE / (
        f"estado_baterias_{dia2}.json"
    )

    estado = (
        json.loads(
            ruta_estado.read_text(encoding="utf-8")
        )
        if ruta_estado.exists()
        else {}
    )

    if not isinstance(estado, dict):
        raise RuntimeError(
            "JSON de continuidad inválido"
        )

    estado.update({
        "fecha_plan_origen": str(fecha),
        "fecha_inicio_siguiente_plan": str(dia2),
        "tipo_estado": "estimado_por_simulacion",
        "energia_inicial_vehiculos": energias,
        "soc_medio_pct": round(
            float(cierres["soc_pct"].mean()), 2
        ),
        "soc_minimo_pct": round(
            float(cierres["soc_pct"].min()), 2
        ),
        "origen": "planificacion_diaria_consistente",
    })

    metadatos = dict(resumen)
    metadatos.update({
        "politica_consistencia": "dia_solapado_inmutable",
        "dia_conservado": info["dia_fijo"],
        "plan_origen_conservacion": info["origen"],
    })

    rutas = [
        ruta_plan,
        ruta_resumen,
        ruta_estado,
    ]

    # Guardar copias de seguridad fuera del repositorio.

    existentes = [
        ruta for ruta in rutas if ruta.exists()
    ]

    if existentes:
        destino = BACKUPS / (
            f"{fecha}_{uuid4().hex[:8]}"
        )

        destino.mkdir(
            parents=True, exist_ok=False
        )

        for ruta in existentes:
            shutil.copy2(
                ruta, destino / ruta.name
            )

        print("Copia de seguridad:", destino)

    temporales = [
        ruta_plan.with_name(
            ruta_plan.name + ".tmp.parquet"
        ),
        ruta_resumen.with_name(
            ruta_resumen.name + ".tmp"
        ),
        ruta_estado.with_name(
            ruta_estado.name + ".tmp"
        ),
    ]

    try:
        df.to_parquet(
            temporales[0], index=False
        )

        temporales[1].write_text(
            json.dumps(
                metadatos,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        temporales[2].write_text(
            json.dumps(
                estado,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        for origen, destino in zip(temporales, rutas):
            os.replace(origen, destino)

    finally:
        for temporal in temporales:
            temporal.unlink(missing_ok=True)

    return ruta_plan
