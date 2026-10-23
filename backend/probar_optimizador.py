
# FLOTIQ | VALIDAR Y PROBAR OPTIMIZACION FUTURA DE 24 HORAS

from pathlib import Path

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
LUNES_HISTORICO = pd.Timestamp("2026-09-21")
LUNES_FUTURO = pd.Timestamp("2026-11-23")
TOLERANCIA = 0.05


def comprobar_referencia(operaciones: pd.DataFrame, referencia: pd.DataFrame):
    """Verifica que la recarga histórica trasladada sigue siendo factible."""
    comparacion = operaciones.merge(
        referencia[
            ["vehicle_id", "hora", "recarga_red_kwh", "energia_bateria_kwh"]
        ],
        on=["vehicle_id", "hora"],
        how="left",
        validate="one_to_one",
    ).sort_values(["vehicle_id", "hora"])

    if comparacion[["recarga_red_kwh", "energia_bateria_kwh"]].isna().any().any():
        raise RuntimeError("Faltan registros en el plan histórico trasladado.")

    if (comparacion["recarga_red_kwh"] < -TOLERANCIA).any():
        raise RuntimeError("La referencia tiene cargas negativas.")

    if (comparacion["recarga_red_kwh"] > POTENCIA_CARGADOR_KW + TOLERANCIA).any():
        raise RuntimeError("La referencia supera 11 kWh en una hora por cargador.")

    carga_en_turno = (
        ~comparacion["disponible_carga"]
    ) & (comparacion["recarga_red_kwh"] > 0.01)
    if carga_en_turno.any():
        ejemplo = comparacion.loc[carga_en_turno, ["vehicle_id", "hora"]].head(3)
        raise RuntimeError(
            "El plan histórico carga durante turnos en la semana futura. "
            f"Ejemplos:\n{ejemplo.to_string(index=False)}"
        )

    uso_horario = comparacion.groupby("hora").agg(
        cargadores_ocupados=(
            "recarga_red_kwh", lambda serie: int((serie > 0.01).sum())
        ),
        potencia_total_kw=("recarga_red_kwh", "sum"),
    )
    if (uso_horario["cargadores_ocupados"] > NUM_CARGADORES).any():
        raise RuntimeError("La referencia necesita más de 20 cargadores.")
    if (uso_horario["potencia_total_kw"] > POTENCIA_MAX_INSTALACION_KW + TOLERANCIA).any():
        raise RuntimeError("La referencia supera 150 kW de potencia horaria.")

    grupos = comparacion.groupby("vehicle_id", sort=False)
    bateria_recalculada = (
        CAPACIDAD_BATERIA_KWH * SOC_INICIAL
        - grupos["energia_consumida_kwh"].cumsum()
        + EFICIENCIA_CARGA * grupos["recarga_red_kwh"].cumsum()
    )
    diferencia = (bateria_recalculada - comparacion["energia_bateria_kwh"]).abs()
    print("Diferencia máxima de batería con el histórico:", round(float(diferencia.max()), 4), "kWh")
    if diferencia.max() > TOLERANCIA:
        raise RuntimeError(
            "La batería no coincide con el histórico. "
            "Revisar operaciones y referencia antes de resolver."
        )

    minimo = CAPACIDAD_BATERIA_KWH * SOC_MINIMO
    maximo = CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO
    if (bateria_recalculada < minimo - TOLERANCIA).any() or (
        bateria_recalculada > maximo + TOLERANCIA
    ).any():
        raise RuntimeError("La referencia incumple los límites de batería.")

    return comparacion


def main():
    print("FLOTIQ | PRUEBA DE OPTIMIZACION FUTURA")
    print("Semana futura:", LUNES_FUTURO.date())

    preparado = preparar_planificacion(LUNES_FUTURO.date().isoformat())
    operaciones = preparado["operaciones"].copy()
    precios = preparado["precios"].sort_values("hora").head(24).copy()
    operaciones = operaciones[operaciones["hora"].isin(precios["hora"])].copy()

    if not REFERENCIA.exists():
        raise FileNotFoundError(f"No existe la referencia histórica: {REFERENCIA}")

    historico = pd.read_parquet(
        REFERENCIA,
        columns=["vehicle_id", "hora", "recarga_red_kwh", "energia_bateria_kwh"],
    )
    historico["hora"] = pd.to_datetime(historico["hora"])
    if historico["hora"].dt.tz is not None:
        historico["hora"] = (
            historico["hora"].dt.tz_convert("Europe/Madrid").dt.tz_localize(None)
        )

    # Los lunes están separados por semanas completas: mismos días y horas.
    historico["hora"] = historico["hora"] + (LUNES_FUTURO - LUNES_HISTORICO)
    historico = historico[historico["hora"].isin(precios["hora"])].copy()

    if historico.duplicated(["vehicle_id", "hora"]).any():
        raise RuntimeError("La referencia histórica contiene filas duplicadas.")
    if len(historico) != len(operaciones) or len(precios) != 24:
        raise RuntimeError(
            f"Datos incompletos: histórico={len(historico)}, "
            f"operaciones={len(operaciones)}, precios={len(precios)}"
        )

    print("Vehículos:", operaciones["vehicle_id"].nunique())
    print("Horas:", len(precios))
    print("Consumo:", round(float(operaciones["energia_consumida_kwh"].sum()), 2), "kWh")
    print("\nValidando referencia histórica trasladada...")
    comprobacion = comprobar_referencia(operaciones, historico)

    objetivos = (
        comprobacion.sort_values("hora")
        .groupby("vehicle_id")["energia_bateria_kwh"]
        .last()
        .to_dict()
    )
    print("Referencia factible: SI")
    print("Batería objetivo mínima:", round(min(objetivos.values()), 2), "kWh")
    print("Batería objetivo máxima:", round(max(objetivos.values()), 2), "kWh")
    print("\nEjecutando CBC con objetivos finales factibles...")

    resultado = optimizar_recargas(
        datos_operativos=operaciones,
        precios_horarios=precios,
        energia_final_objetivo=objetivos,
        tiempo_maximo_segundos=180,
    )

    print("\nFLOTIQ | RESULTADO")
    print("Estado CBC:", resultado["estado"])
    print("Factibilidad validada:", resultado.get("factibilidad_validada"))
    print("Optimalidad certificada:", resultado.get("optimalidad_certificada"))
    print("Vehículos:", resultado["vehiculos"])
    print("Horas:", resultado["horas"])
    print("Energía adquirida:", resultado["energia_total_kwh"], "kWh")
    print("Coste estimado:", resultado["coste_estimado_eur"], "€")
    activas = resultado["recargas"].query("recarga_red_kwh > 0.01")
    print("Recargas vehículo-hora:", len(activas))
    print("\nPrimeras recargas:")
    print(
        activas[["vehicle_id", "hora", "recarga_red_kwh", "soc_pct"]]
        .head(5)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
