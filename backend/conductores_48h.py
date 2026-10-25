
# FLOTIQ | CONDUCTORES Y TURNOS ESTIMADOS A 48 HORAS

import os

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from sqlalchemy import create_engine, text


router = APIRouter(
    prefix='/api/48h',
    tags=['Conductores 48h'],
)

ROOT = Path(__file__).resolve().parents[1]
SEMANA_HISTORICA = date(2026, 9, 21)
ZONA = 'Europe/Madrid'


@router.get('/{fecha_consulta}/conductores')
def obtener_conductores_48h(fecha_consulta: date):

    load_dotenv(ROOT / '.env')

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        raise HTTPException(
            status_code=503,
            detail='No esta configurada la conexion a la base de datos.',
        )

    consulta = text(
        'SELECT '
        's.shift_id, '
        's.shift_date, '
        's.shift_type, '
        's.start_time, '
        's.end_time, '
        's.driver_id, '
        'd.full_name, '
        'a.vehicle_id '
        'FROM shifts s '
        'INNER JOIN drivers d ON d.driver_id = s.driver_id '
        'INNER JOIN assignments a ON a.shift_id = s.shift_id '
        'WHERE s.shift_date >= :inicio '
        'AND s.shift_date <= :fin '
        'ORDER BY s.start_time, s.driver_id'
    )

    try:
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
        )

        try:
            with engine.connect() as conexion:
                historico = pd.read_sql(
                    consulta,
                    conexion,
                    params={
                        'inicio': SEMANA_HISTORICA,
                        'fin': SEMANA_HISTORICA + timedelta(days=6),
                    },
                )
        finally:
            engine.dispose()

    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=(
                'No se pudieron consultar los turnos historicos. '
                f'{type(error).__name__}'
            ),
        )

    if historico.empty:
        raise HTTPException(
            status_code=404,
            detail='No existen turnos en la semana historica.',
        )

    inicio_plan = fecha_consulta + timedelta(days=1)

    turnos = []

    try:
        for desplazamiento in range(2):

            dia_futuro = (
                inicio_plan + timedelta(days=desplazamiento)
            )

            inicio_dia = pd.Timestamp(
                dia_futuro,
                tz=ZONA,
            )

            fin_dia = pd.Timestamp(
                dia_futuro + timedelta(days=1),
                tz=ZONA,
            )

            # Incluir turnos que empezaron el dia anterior
            # y continuan durante el dia consultado.

            for retroceso in (1, 0):

                fecha_origen_futura = (
                    dia_futuro - timedelta(days=retroceso)
                )

                fecha_historica = (
                    SEMANA_HISTORICA
                    + timedelta(
                        days=fecha_origen_futura.weekday()
                    )
                )

                seleccion = historico.loc[
                    pd.to_datetime(
                        historico['shift_date']
                    ).dt.date == fecha_historica
                ]

                for fila in seleccion.itertuples(index=False):

                    origen = pd.Timestamp(
                        fila.start_time
                    )

                    fin_origen = pd.Timestamp(
                        fila.end_time
                    )

                    if origen.tzinfo is not None:
                        raise ValueError(
                            'Los turnos historicos deben tener '
                            'fechas locales sin zona horaria.'
                        )

                    salto = (
                        fecha_origen_futura - fecha_historica
                    ).days

                    inicio_estimado = (
                        origen + pd.Timedelta(days=salto)
                    ).tz_localize(ZONA)

                    fin_estimado = (
                        fin_origen + pd.Timedelta(days=salto)
                    ).tz_localize(ZONA)

                    if fin_estimado <= inicio_estimado:
                        raise ValueError(
                            'Existe un turno con duracion invalida.'
                        )

                    inicio_visible = max(
                        inicio_estimado,
                        inicio_dia,
                    )

                    fin_visible = min(
                        fin_estimado,
                        fin_dia,
                    )

                    if fin_visible <= inicio_visible:
                        continue

                    conductor = str(fila.driver_id)

                    nombre = (
                        str(fila.full_name)
                        if pd.notna(fila.full_name)
                        else conductor
                    )

                    turnos.append({
                        'dia': dia_futuro.isoformat(),
                        'conductor_id': conductor,
                        'nombre': nombre,
                        'vehiculo_id': str(fila.vehicle_id),
                        'tipo_turno': str(fila.shift_type),
                        'inicio_local': inicio_visible.isoformat(),
                        'fin_local': fin_visible.isoformat(),
                        'horas': round(
                            (
                                fin_visible - inicio_visible
                            ).total_seconds() / 3600,
                            2,
                        ),
                        'turno_historico_id': str(fila.shift_id),
                    })

    except (ValueError, TypeError) as error:
        raise HTTPException(
            status_code=500,
            detail=f'Error proyectando los turnos: {error}',
        )

    turnos.sort(
        key=lambda t: (
            t['dia'],
            t['inicio_local'],
            t['conductor_id'],
        )
    )

    return {
        'fecha_consulta': fecha_consulta.isoformat(),
        'tipo_datos': 'replica_historica_simulada',
        'semana_historica': '2026-09-21 a 2026-09-27',
        'total_turnos': len(turnos),
        'total_conductores': len({
            t['conductor_id'] for t in turnos
        }),
        'turnos': turnos,
        'advertencia': (
            'Los conductores y horarios proceden de una '
            'semana historica replicada por dia de la semana. '
            'No son turnos futuros confirmados ni se ha '
            'validado su coincidencia exacta con el escenario '
            'horario utilizado por el optimizador.'
        ),
    }
