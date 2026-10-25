
# FLOTIQ | CONTINUIDAD DIARIA DE BATERIAS

import argparse
import json

from datetime import date, timedelta
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / 'data' / 'processed'

ZONA = 'Europe/Madrid'

CAPACIDAD_KWH = 60.0
SOC_MINIMO = 0.15
SOC_MAXIMO = 0.80


def guardar_continuidad(fecha_consulta):

    fecha_texto = fecha_consulta.isoformat()

    ruta_plan = PROCESSED / (
        f'planificacion_ml_48h_{fecha_texto}.parquet'
    )

    if not ruta_plan.exists():
        raise FileNotFoundError(
            f'No existe la planificacion: {ruta_plan}'
        )

    plan = pd.read_parquet(ruta_plan)

    columnas = {
        'vehicle_id',
        'datetime_utc',
        'energia_bateria_kwh',
        'soc_pct',
    }

    if not columnas.issubset(plan.columns):
        raise ValueError(
            'Faltan columnas de bateria en la planificacion'
        )

    plan['datetime_utc'] = pd.to_datetime(
        plan['datetime_utc'],
        utc=True,
    )

    if plan.duplicated(
        ['vehicle_id', 'datetime_utc']
    ).any():
        raise ValueError(
            'Hay registros duplicados en la planificacion'
        )

    # Primer dia del horizonte original

    primer_dia = fecha_consulta + timedelta(days=1)

    # Inicio del dia siguiente

    fecha_corte = fecha_consulta + timedelta(days=2)

    inicio = pd.Timestamp(
        primer_dia.isoformat(),
        tz=ZONA,
    ).tz_convert('UTC')

    corte = pd.Timestamp(
        fecha_corte.isoformat(),
        tz=ZONA,
    ).tz_convert('UTC')

    horas = pd.date_range(
        inicio,
        corte,
        freq='h',
        inclusive='left',
    )

    primer_dia_plan = plan[
        (plan['datetime_utc'] >= inicio)
        & (plan['datetime_utc'] < corte)
    ].copy()

    vehiculos = sorted(
        plan['vehicle_id'].unique().tolist()
    )

    if len(vehiculos) != 50:
        raise ValueError(
            f'Se esperaban 50 vehiculos, hay {len(vehiculos)}'
        )

    cobertura = primer_dia_plan.groupby(
        'vehicle_id'
    )['datetime_utc'].nunique()

    if (
        len(cobertura) != 50
        or (cobertura != len(horas)).any()
    ):
        raise ValueError(
            'No existe cobertura horaria completa '
            'para todos los vehiculos'
        )

    if set(
        primer_dia_plan['datetime_utc']
    ) != set(horas):
        raise ValueError(
            'Las horas no coinciden con el primer dia'
        )

    # Obtener el ultimo estado del primer dia

    finales = (
        primer_dia_plan
        .sort_values(['vehicle_id', 'datetime_utc'])
        .groupby('vehicle_id')
        .tail(1)
        .copy()
    )

    energia_minima = CAPACIDAD_KWH * SOC_MINIMO
    energia_maxima = CAPACIDAD_KWH * SOC_MAXIMO

    if (
        finales['energia_bateria_kwh'].isna().any()
        or finales['soc_pct'].isna().any()
    ):
        raise ValueError(
            'Hay estados finales de bateria vacios'
        )

    if not finales[
        'energia_bateria_kwh'
    ].between(
        energia_minima - 0.01,
        energia_maxima + 0.01,
    ).all():
        raise ValueError(
            'Hay baterias finales fuera de los limites'
        )

    # Guardar un estado inicial por vehiculo

    estados = {
        str(fila.vehicle_id): round(
            float(fila.energia_bateria_kwh),
            6,
        )
        for fila in finales.itertuples()
    }

    resultado = {
        'fecha_plan_origen': fecha_texto,
        'fecha_inicio_siguiente_plan': fecha_corte.isoformat(),
        'tipo_estado': 'estimado_por_simulacion',
        'vehiculos': len(estados),
        'soc_medio_pct': round(
            float(finales['soc_pct'].mean()),
            2,
        ),
        'soc_minimo_pct': round(
            float(finales['soc_pct'].min()),
            2,
        ),
        'energia_inicial_vehiculos': estados,
    }

    ruta_salida = PROCESSED / (
        f'estado_baterias_{fecha_corte.isoformat()}.json'
    )

    ruta_salida.write_text(
        json.dumps(
            resultado,
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    print()
    print('FLOTIQ | CONTINUIDAD DE BATERIAS')
    print('-' * 45)
    print('Plan original:', fecha_consulta)
    print('Estado estimado para:', fecha_corte)
    print('Vehiculos:', len(estados))
    print('SOC medio:', resultado['soc_medio_pct'], '%')
    print('SOC minimo:', resultado['soc_minimo_pct'], '%')
    print('Guardado:', ruta_salida)
    print()
    print('Estado estimado; no es una medicion real.')

    return ruta_salida


if __name__ == '__main__':

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--fecha-consulta',
        required=True,
    )

    args = parser.parse_args()

    guardar_continuidad(
        date.fromisoformat(args.fecha_consulta)
    )
