
# FLOTIQ | PLANIFICACION DE RECARGAS A 48 HORAS


import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import math
import pandas as pd

from backend.optimizador import (
    optimizar_recargas,
    CAPACIDAD_BATERIA_KWH,
    SOC_INICIAL,
    SOC_MINIMO,
    SOC_OBJETIVO,
)


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
ZONA = "Europe/Madrid"


def planificar_48h(fecha_consulta, tiempo_maximo=180):

    fecha_texto = fecha_consulta.isoformat()

    ruta_precios = PROCESSED / (
        f"prediccion_ml_48h_emitida_{fecha_texto}.parquet"
    )

    ruta_operaciones = PROCESSED / (
        f"prevision_operaciones_48h_emitida_{fecha_texto}.parquet"
    )

    # -------------------------------------------
    # 1. COMPROBAR ARCHIVOS
    # -------------------------------------------

    for ruta in [ruta_precios, ruta_operaciones]:
        if not ruta.exists():
            raise FileNotFoundError(
                f"No existe el archivo: {ruta}\n"
                "Genera primero las predicciones "
                "y el escenario operativo."
            )

    predicciones = pd.read_parquet(ruta_precios)
    operaciones = pd.read_parquet(ruta_operaciones)

    columnas_precios = {
        "datetime_utc",
        "precio_predicho_eur_mwh",
    }

    columnas_operaciones = {
        "datetime_utc",
        "vehicle_id",
        "disponible_carga",
        "energia_consumida_kwh",
    }

    if not columnas_precios.issubset(predicciones.columns):
        raise ValueError(
            "Faltan columnas en las predicciones ML"
        )

    if not columnas_operaciones.issubset(operaciones.columns):
        raise ValueError(
            "Faltan columnas en las operaciones"
        )

    # -------------------------------------------
    # 2. VALIDAR EL HORIZONTE DE 48 HORAS
    # -------------------------------------------

    inicio = pd.Timestamp(
        fecha_consulta + timedelta(days=1),
        tz=ZONA,
    )

    fin = pd.Timestamp(
        fecha_consulta + timedelta(days=3),
        tz=ZONA,
    )

    horas_esperadas = pd.date_range(
        inicio.tz_convert("UTC"),
        fin.tz_convert("UTC"),
        freq="h",
        inclusive="left",
    )

    predicciones["datetime_utc"] = pd.to_datetime(
        predicciones["datetime_utc"],
        utc=True,
    )

    operaciones["datetime_utc"] = pd.to_datetime(
        operaciones["datetime_utc"],
        utc=True,
    )

    if predicciones["datetime_utc"].duplicated().any():
        raise ValueError(
            "Existen horas duplicadas en las predicciones"
        )

    if (
        len(predicciones) != len(horas_esperadas)
        or set(predicciones["datetime_utc"])
        != set(horas_esperadas)
    ):
        raise ValueError(
            "Las predicciones no cubren exactamente "
            "los dos dias solicitados."
        )

    if operaciones.duplicated(
        ["vehicle_id", "datetime_utc"]
    ).any():
        raise ValueError(
            "Existen operaciones duplicadas"
        )

    vehiculos = sorted(
        operaciones["vehicle_id"].unique().tolist()
    )

    if len(vehiculos) != 50:
        raise ValueError(
            f"Se esperaban 50 vehiculos, hay {len(vehiculos)}"
        )

    if len(operaciones) != (
        len(vehiculos) * len(horas_esperadas)
    ):
        raise ValueError(
            "La matriz vehiculo-hora esta incompleta"
        )

    if set(operaciones["datetime_utc"]) != set(horas_esperadas):
        raise ValueError(
            "Las horas operativas no coinciden con las predicciones"
        )

    cobertura = operaciones.groupby(
        "vehicle_id"
    )["datetime_utc"].nunique()

    if (cobertura != len(horas_esperadas)).any():
        raise ValueError(
            "Algun vehiculo no tiene todas sus horas"
        )

    # -------------------------------------------
    # 3. PREPARAR ENTRADAS DEL OPTIMIZADOR
    # -------------------------------------------

    precios_horarios = predicciones[
        ["datetime_utc", "precio_predicho_eur_mwh"]
    ].rename(
        columns={
            "datetime_utc": "hora",
            "precio_predicho_eur_mwh": "price_eur_mwh",
        }
    )

    datos_operativos = operaciones[
        [
            "vehicle_id",
            "datetime_utc",
            "disponible_carga",
            "energia_consumida_kwh",
        ]
    ].rename(
        columns={"datetime_utc": "hora"}
    )

    # Estados de bateria SIMULADOS.
    # En produccion se sustituiran por mediciones reales
    # o por un estado propagado y validado.

    
    # Cargar las baterias estimadas al inicio del horizonte

    fecha_inicio_plan = (
        fecha_consulta + timedelta(days=1)
    ).isoformat()

    ruta_estado = PROCESSED / (
        f'estado_baterias_{fecha_inicio_plan}.json'
    )

    if not ruta_estado.exists():
        raise FileNotFoundError(
            f'No existe el estado inicial: {ruta_estado}. '
            'No se reinician automaticamente las baterias al 80%.'
        )

    with open(ruta_estado, 'r', encoding='utf-8') as archivo:
        estado_guardado = json.load(archivo)

    # Comprobar que pertenece al dia correcto

    fecha_origen_esperada = (
        fecha_consulta - timedelta(days=1)
    ).isoformat()

    if (
        estado_guardado.get('fecha_inicio_siguiente_plan')
        != fecha_inicio_plan
        or estado_guardado.get('fecha_plan_origen')
        != fecha_origen_esperada
    ):
        raise ValueError(
            'El estado de baterias no corresponde '
            'a la planificacion anterior.'
        )

    if estado_guardado.get('tipo_estado') != 'estimado_por_simulacion':
        raise ValueError(
            'El origen del estado de baterias no es el esperado.'
        )

    estados = estado_guardado.get('energia_inicial_vehiculos')

    if not isinstance(estados, dict):
        raise ValueError(
            'El archivo de baterias no contiene estados validos.'
        )

    if set(estados.keys()) != set(str(v) for v in vehiculos):
        raise ValueError(
            'Los vehiculos del estado guardado no coinciden.'
        )

    energia_inicial = {}

    minimo = CAPACIDAD_BATERIA_KWH * SOC_MINIMO
    maximo = CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO

    for vehiculo in vehiculos:

        energia = float(estados[str(vehiculo)])

        if not math.isfinite(energia) or not minimo <= energia <= maximo:
            raise ValueError(
                f'Bateria inicial fuera de limites: {vehiculo}'
            )

        energia_inicial[vehiculo] = energia

    print()
    print('Estados iniciales recuperados correctamente')
    print('Archivo:', ruta_estado.name)
    print('Vehiculos:', len(energia_inicial))
    print('SOC medio inicial:', estado_guardado['soc_medio_pct'], '%')


    energia_objetivo = {
        v: CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO
        for v in vehiculos
    }

    # -------------------------------------------
    # 4. EJECUTAR OPTIMIZADOR EXISTENTE
    # -------------------------------------------

    print()
    print("FLOTIQ | OPTIMIZACION ML DE RECARGAS")
    print("-" * 45)
    print("Fecha consulta:", fecha_consulta)
    print("Desde:", inicio)
    print("Hasta:", fin, "(exclusivo)")
    print("Vehiculos:", len(vehiculos))
    print("Horas:", len(horas_esperadas))
    print("Escenario: operaciones historicas simuladas")
    print("Precios: prediccion Machine Learning")
    print()
    print("Ejecutando optimizador...")

    
    # Identificar el final del primer dia natural

    corte_local = pd.Timestamp(
        fecha_consulta + timedelta(days=2),
        tz=ZONA,
    )

    horas_primer_dia = int(
        (
            horas_esperadas
            < corte_local.tz_convert('UTC')
        ).sum()
    )

    indice_fin_primer_dia = horas_primer_dia - 1

    # Optimizar con reserva intermedia flexible

    resultado = optimizar_recargas(
        datos_operativos=datos_operativos,
        precios_horarios=precios_horarios,
        energia_final_objetivo=energia_objetivo,
        energia_inicial_vehiculos=energia_inicial,
        tiempo_maximo_segundos=tiempo_maximo,
        objetivo_final_flexible=True,
        penalizacion_deficit_eur_kwh=1.0,
        indice_fin_primer_dia=indice_fin_primer_dia,
        soc_objetivo_intermedio=0.40,
        penalizacion_intermedia_eur_kwh=2.0,
    )

    print(
        'Deficit objetivo intermedio:',
        resultado['deficit_objetivo_intermedio_kwh'],
        'kWh',
    )


    if not resultado["factibilidad_validada"]:
        raise RuntimeError(
            "El optimizador no ha validado la solucion"
        )

    # -------------------------------------------
    # 5. PREPARAR PLANIFICACION
    # -------------------------------------------

    plan = resultado["recargas"].copy()

    # El optimizador devuelve horas UTC sin zona.
    plan = plan.rename(
        columns={"hora": "datetime_utc"}
    )

    plan["datetime_utc"] = pd.to_datetime(
        plan["datetime_utc"],
        utc=True,
    )

    plan["fecha_local"] = (
        plan["datetime_utc"].dt.tz_convert(ZONA)
    )

    # Incorporar los precios utilizados.
    plan = plan.merge(
        precios_horarios.rename(
            columns={
                "hora": "datetime_utc",
                "price_eur_mwh": "precio_predicho_eur_mwh",
            }
        ),
        on="datetime_utc",
        how="left",
        validate="many_to_one",
    )

    # Incorporar consumo y disponibilidad.
    plan = plan.merge(
        operaciones[
            [
                "vehicle_id",
                "datetime_utc",
                "energia_consumida_kwh",
                "disponible_carga",
            ]
        ],
        on=["vehicle_id", "datetime_utc"],
        how="left",
        validate="one_to_one",
    )

    if plan.isna().any().any():
        raise RuntimeError(
            "La planificacion contiene valores nulos"
        )

    plan["fecha_consulta"] = fecha_texto
    plan["tipo_plan"] = "escenario_simulado_ml"

    plan = plan.sort_values(
        ["datetime_utc", "vehicle_id"]
    ).reset_index(drop=True)

    # -------------------------------------------
    # 6. GUARDAR RESULTADOS
    # -------------------------------------------

    PROCESSED.mkdir(
        parents=True,
        exist_ok=True,
    )

    ruta_salida = PROCESSED / (
        f"planificacion_ml_48h_{fecha_texto}.parquet"
    )

    plan.to_parquet(
        ruta_salida,
        index=False,
    )

    resumen = {
        "fecha_consulta": fecha_texto,
        "fecha_inicio": str(inicio),
        "fecha_fin_exclusiva": str(fin),
        "vehiculos": int(resultado["vehiculos"]),
        "horas": int(resultado["horas"]),
        "energia_recargada_red_kwh": float(
            resultado["energia_total_kwh"]
        ),
        "coste_estimado_eur": float(
            resultado["coste_estimado_eur"]
        ),
        "estado_solver": str(resultado["estado"]),
        "factibilidad_validada": bool(
            resultado["factibilidad_validada"]
        ),
        "optimalidad_certificada": bool(
            resultado["optimalidad_certificada"]
        ),
        "origen_precios": "prediccion_ml_48h",
        "origen_operaciones": "replica_historica_semanal",
        "soc_inicial_simulado": SOC_INICIAL,
        "soc_objetivo": SOC_OBJETIVO,
        "advertencia": (
            "Planificacion basada en precios ML y "
            "operaciones simuladas. "
            "No representa turnos ni baterias "
            "confirmados en tiempo real."
        ),
    }

    ruta_json = ruta_salida.with_suffix(".json")

    ruta_json.write_text(
        json.dumps(
            resumen,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # -------------------------------------------
    # 7. MOSTRAR RESULTADOS
    # -------------------------------------------

    print()
    print("FLOTIQ | RESULTADO PLANIFICACION 48H")
    print("-" * 45)

    print("Estado solver:", resultado["estado"])

    print(
        "Factibilidad validada:",
        resultado["factibilidad_validada"],
    )

    print(
        "Optimalidad certificada:",
        resultado["optimalidad_certificada"],
    )

    print(
        "Energia total de red:",
        resultado["energia_total_kwh"],
        "kWh",
    )

    print(
        "Coste estimado:",
        resultado["coste_estimado_eur"],
        "EUR",
    )

    print("Registros generados:", len(plan))
    print("Guardado:", ruta_salida)

    print()
    print(
        plan[
            [
                "vehicle_id",
                "fecha_local",
                "recarga_red_kwh",
                "soc_pct",
                "coste_estimado_eur",
            ]
        ].head(10).to_string(index=False)
    )

    print()
    print(
        "AVISO: precios ML y operaciones simuladas. "
        "El coste es una estimacion."
    )

    return ruta_salida


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--fecha-consulta",
        default=None,
        help="Fecha YYYY-MM-DD",
    )

    parser.add_argument(
        "--tiempo-maximo",
        type=int,
        default=180,
        help="Limite de calculo del optimizador",
    )

    args = parser.parse_args()

    fecha = (
        date.fromisoformat(args.fecha_consulta)
        if args.fecha_consulta
        else datetime.now(ZoneInfo(ZONA)).date()
    )

    planificar_48h(
        fecha,
        tiempo_maximo=args.tiempo_maximo,
    )
