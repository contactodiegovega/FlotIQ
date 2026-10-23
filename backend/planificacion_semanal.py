# FLOTIQ | PLANIFICACION SEMANAL CON CONTINUIDAD DE BATERIA

from datetime import date
from pathlib import Path
import argparse
import json

import numpy as np
import pandas as pd

from backend.optimizador import (
    CAPACIDAD_BATERIA_KWH,
    EFICIENCIA_CARGA,
    NUM_CARGADORES,
    POTENCIA_CARGADOR_KW,
    POTENCIA_MAX_INSTALACION_KW,
    SOC_INICIAL,
    SOC_MINIMO,
    SOC_OBJETIVO,
    optimizar_recargas,
)
from backend.preparar_planificacion import preparar_planificacion


RAIZ = Path(__file__).resolve().parents[1]
REFERENCIA = RAIZ / "data" / "processed" / "recargas_baseline_semana.parquet"
SALIDA = RAIZ / "data" / "processed"
LUNES_HISTORICO = pd.Timestamp("2026-09-21")
TOLERANCIA_REFERENCIA = 0.05


def cargar_referencia(fecha_inicio: str, operaciones: pd.DataFrame) -> pd.DataFrame:
    """Traslada y valida el plan histórico como referencia factible, no como predicción."""
    if not REFERENCIA.exists():
        raise FileNotFoundError(f"No existe la referencia histórica: {REFERENCIA}")

    referencia = pd.read_parquet(
        REFERENCIA,
        columns=["vehicle_id", "hora", "recarga_red_kwh", "energia_bateria_kwh"],
    ).copy()
    referencia["hora"] = pd.to_datetime(referencia["hora"])
    if referencia["hora"].dt.tz is not None:
        referencia["hora"] = (
            referencia["hora"].dt.tz_convert("Europe/Madrid").dt.tz_localize(None)
        )
    referencia["hora"] += pd.Timestamp(fecha_inicio) - LUNES_HISTORICO

    if referencia.duplicated(["vehicle_id", "hora"]).any():
        raise ValueError("Referencia histórica con vehículo y hora duplicados.")
    if (referencia["recarga_red_kwh"] < -TOLERANCIA_REFERENCIA).any():
        raise ValueError("Referencia histórica con cargas negativas.")

    conjunto = operaciones.merge(
        referencia,
        on=["vehicle_id", "hora"],
        how="left",
        validate="one_to_one",
    ).sort_values(["vehicle_id", "hora"])

    if len(conjunto) != len(operaciones) or conjunto[
        ["recarga_red_kwh", "energia_bateria_kwh"]
    ].isna().any().any():
        raise ValueError("Referencia incompleta para los vehículos y horas futuros.")

    if (
        (~conjunto["disponible_carga"])
        & (conjunto["recarga_red_kwh"] > 0.01)
    ).any():
        raise ValueError("La referencia incluye recargas durante turnos.")
    if (conjunto["recarga_red_kwh"] > POTENCIA_CARGADOR_KW + TOLERANCIA_REFERENCIA).any():
        raise ValueError("La referencia excede 11 kWh por vehículo y hora.")

    por_hora = conjunto.groupby("hora").agg(
        cargadores=("recarga_red_kwh", lambda x: int((x > 0.01).sum())),
        potencia=("recarga_red_kwh", "sum"),
    )
    if (por_hora["cargadores"] > NUM_CARGADORES).any():
        raise ValueError("La referencia supera los 20 cargadores.")
    if (por_hora["potencia"] > POTENCIA_MAX_INSTALACION_KW + TOLERANCIA_REFERENCIA).any():
        raise ValueError("La referencia supera los 150 kW.")

    grupos = conjunto.groupby("vehicle_id", sort=False)
    bateria_calculada = (
        CAPACIDAD_BATERIA_KWH * SOC_INICIAL
        - grupos["energia_consumida_kwh"].cumsum()
        + EFICIENCIA_CARGA * grupos["recarga_red_kwh"].cumsum()
    )
    diferencia = (bateria_calculada - conjunto["energia_bateria_kwh"]).abs()
    if diferencia.max() > TOLERANCIA_REFERENCIA:
        raise ValueError(
            "La batería de la referencia no coincide con consumos y cargas. "
            f"Diferencia máxima: {diferencia.max():.4f} kWh."
        )
    if (
        (bateria_calculada < CAPACIDAD_BATERIA_KWH * SOC_MINIMO - TOLERANCIA_REFERENCIA)
        | (bateria_calculada > CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO + TOLERANCIA_REFERENCIA)
    ).any():
        raise ValueError("La referencia incumple los límites de batería.")

    print("Referencia histórica trasladada: FACTIBLE", flush=True)
    return conjunto


def asignar_cargadores(resultados: pd.DataFrame) -> pd.DataFrame:
    """Asigna un cargador físico a cada intervalo con carga efectiva."""
    df = resultados.sort_values(["hora", "vehicle_id"]).copy()
    df["cargador_id"] = None
    anteriores = {}
    hora_anterior = None

    for hora, bloque in df.groupby("hora", sort=True):
        activos = bloque.index[bloque["recarga_red_kwh"] > 0.01].tolist()
        if len(activos) > NUM_CARGADORES:
            raise RuntimeError(f"Más de {NUM_CARGADORES} recargas en {hora}.")
        if hora_anterior is None or hora - hora_anterior != pd.Timedelta(hours=1):
            anteriores = {}

        asignados = {}
        usados = set()
        # Conservar el mismo cargador para quienes continúan cargando.
        for indice in activos:
            vehiculo = df.at[indice, "vehicle_id"]
            if vehiculo in anteriores:
                cargador = anteriores[vehiculo]
                asignados[vehiculo] = cargador
                usados.add(cargador)

        disponibles = [f"C{i:02d}" for i in range(1, NUM_CARGADORES + 1)
                       if f"C{i:02d}" not in usados]
        for indice in activos:
            vehiculo = df.at[indice, "vehicle_id"]
            if vehiculo not in asignados:
                asignados[vehiculo] = disponibles.pop(0)
            df.at[indice, "cargador_id"] = asignados[vehiculo]

        anteriores = asignados
        hora_anterior = hora

    return df.sort_values(["vehicle_id", "hora"]).reset_index(drop=True)


def generar_planificacion_semanal(
    fecha_inicio: str,
    tiempo_maximo_dia: int = 180,
    guardar: bool = True,
):
    inicio = date.fromisoformat(fecha_inicio)
    if inicio.weekday() != 0:
        raise ValueError("La fecha elegida debe ser un lunes.")

    preparados = preparar_planificacion(fecha_inicio)
    operaciones = preparados["operaciones"]
    precios = preparados["precios"].sort_values("hora")
    if len(precios) != 168:
        raise ValueError("Esta versión semanal requiere exactamente 168 horas.")

    referencia = cargar_referencia(fecha_inicio, operaciones)
    vehiculos = sorted(operaciones["vehicle_id"].unique())
    iniciales = {v: CAPACIDAD_BATERIA_KWH * SOC_INICIAL for v in vehiculos}
    planes = []
    resumen_diario = []

    for dia in range(7):
        horas_dia = precios.iloc[dia * 24:(dia + 1) * 24].copy()
        operaciones_dia = operaciones[
            operaciones["hora"].isin(horas_dia["hora"])
        ].copy()
        referencia_dia = referencia[
            referencia["hora"].isin(horas_dia["hora"])
        ].copy()
       
        # FLOTIQ | VALIDAR Y NORMALIZAR OBJETIVOS DE BATERIA

        objetivos = (
            referencia_dia.sort_values("hora")
            .groupby("vehicle_id")["energia_bateria_kwh"]
            .last()
            .to_dict()
        )

        if set(objetivos) != set(vehiculos):
            raise ValueError(
                f"Faltan objetivos de batería para el día {dia + 1}."
            )

        energia_min = CAPACIDAD_BATERIA_KWH * SOC_MINIMO
        energia_max = CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO

        objetivos_corregidos = {}

        for vehiculo, valor in objetivos.items():
            objetivo_original = float(valor)

            if not np.isfinite(objetivo_original):
                raise ValueError(
                    f"Objetivo de batería no válido: {vehiculo}"
                )

            objetivo_corregido = min(
                max(objetivo_original, energia_min),
                energia_max,
            )

            diferencia = abs(
                objetivo_original - objetivo_corregido
            )

            if diferencia > TOLERANCIA_REFERENCIA:
                raise ValueError(
                    f"Objetivo fuera de límites en {vehiculo}: "
                    f"{objetivo_original:.8f} kWh. "
                    f"Rango permitido: {energia_min:.2f}-"
                    f"{energia_max:.2f} kWh."
                )

            if diferencia > 0.000001:
                print(
                    f"  Ajuste de precisión {vehiculo}: "
                    f"{objetivo_original:.8f} -> "
                    f"{objetivo_corregido:.8f} kWh",
                    flush=True,
                )

            objetivos_corregidos[vehiculo] = objetivo_corregido

        objetivos = objetivos_corregidos


        print(f"Día {dia + 1}/7 · {horas_dia.iloc[0]['hora']:%Y-%m-%d}: optimizando", flush=True)
        solucion = optimizar_recargas(
            datos_operativos=operaciones_dia,
            precios_horarios=horas_dia,
            energia_final_objetivo=objetivos,
            energia_inicial_vehiculos=iniciales,
            tiempo_maximo_segundos=tiempo_maximo_dia,
        )
        if not solucion["factibilidad_validada"]:
            raise RuntimeError(f"Día {dia + 1}: solución sin factibilidad validada.")
        tabla = solucion["recargas"].copy()
        tabla["dia_planificacion"] = dia + 1
        planes.append(tabla)

        finales = (
            tabla.sort_values("hora")
            .groupby("vehicle_id")["energia_bateria_kwh"]
            .last().to_dict()
        )
        if any(abs(finales[v] - objetivos[v]) > 0.01 for v in vehiculos):
            raise RuntimeError(f"Día {dia + 1}: objetivos finales incumplidos.")
        iniciales = finales  # El siguiente día empieza donde termina éste.

        resumen_diario.append({
            "dia": str(horas_dia.iloc[0]["hora"].date()),
            "estado": solucion["estado"],
            "optimalidad_certificada": bool(solucion["optimalidad_certificada"]),
            "coste_estimado_eur": solucion["coste_estimado_eur"],
            "energia_total_kwh": solucion["energia_total_kwh"],
        })
        print(
            f"  {solucion['estado']} | coste: {solucion['coste_estimado_eur']:.2f} € "
            f"| energía: {solucion['energia_total_kwh']:.2f} kWh",
            flush=True,
        )

    semana = asignar_cargadores(pd.concat(planes, ignore_index=True))
    if len(semana) != len(vehiculos) * 168:
        raise RuntimeError("El resultado semanal no contiene todas las horas.")
    if semana["recarga_red_kwh"].gt(0.01).sum() != semana["cargador_id"].notna().sum():
        raise RuntimeError("Hay asignaciones de cargadores inconsistentes.")
    if semana.loc[semana["cargador_id"].notna()].duplicated(["hora", "cargador_id"]).any():
        raise RuntimeError("Un cargador está asignado a dos vehículos en una hora.")

    resumen = {
        "tipo_datos": "planificacion_simulada_futura",
        "metodo_precios": "escenario_historico_central",
        "semana_inicio": fecha_inicio,
        "vehiculos": len(vehiculos),
        "horas": 168,
        "energia_total_kwh": round(float(semana["recarga_red_kwh"].sum()), 2),
        "coste_estimado_eur": round(float(semana["coste_estimado_eur"].sum()), 2),
        "factibilidad_validada": True,
        "optimalidad_semanal_certificada": False,
        "dias": resumen_diario,
        "advertencia": (
            "Se reutiliza un patrón histórico de viajes y se aplican precios de escenario; "
            "no son viajes ni precios reales futuros. La optimización es diaria con "
            "objetivos de batería fijados por la referencia histórica; no es un óptimo semanal global."
        ),
    }

    if guardar:
        SALIDA.mkdir(parents=True, exist_ok=True)
        ruta = SALIDA / f"planificacion_{fecha_inicio}.parquet"
        ruta_json = SALIDA / f"planificacion_{fecha_inicio}_resumen.json"
        semana.to_parquet(ruta, index=False)
        ruta_json.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Planificación guardada: {ruta}", flush=True)
        print(f"Resumen guardado: {ruta_json}", flush=True)

    return {"resumen": resumen, "recargas": semana}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Planificación semanal de FlotIQ")
    parser.add_argument("--semana", default="2026-11-23")
    parser.add_argument("--tiempo-dia", type=int, default=180)
    args = parser.parse_args()
    resultado = generar_planificacion_semanal(args.semana, args.tiempo_dia)
    print("\nFLOTIQ | PLANIFICACION SEMANAL", flush=True)
    print(json.dumps(resultado["resumen"], ensure_ascii=False, indent=2), flush=True)
