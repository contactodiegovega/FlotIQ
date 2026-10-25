
# FLOTIQ | API DE PLANIFICACIONES DE 48 HORAS

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException


router = APIRouter(
    prefix='/api/48h',
    tags=['Planificacion 48h'],
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = PROJECT_ROOT / 'data' / 'processed'
ZONA = 'Europe/Madrid'


def _ruta(tipo, fecha, extension='parquet'):

    nombres = {
        'plan': f'planificacion_ml_48h_{fecha}',
        'precios': f'prediccion_ml_48h_emitida_{fecha}',
        'operaciones': f'prevision_operaciones_48h_emitida_{fecha}',
        'baterias': f'estado_baterias_{fecha}',
    }

    return PROCESSED / f'{nombres[tipo]}.{extension}'


def _leer_json(ruta):

    if not ruta.exists():
        raise HTTPException(
            status_code=404,
            detail=f'Archivo no disponible: {ruta.name}',
        )

    try:
        datos = json.loads(
            ruta.read_text(encoding='utf-8')
        )
    except (OSError, json.JSONDecodeError):
        raise HTTPException(
            status_code=500,
            detail=f'No se pudo leer {ruta.name}',
        )

    if not isinstance(datos, dict):
        raise HTTPException(
            status_code=500,
            detail=f'JSON no valido: {ruta.name}',
        )

    return datos


def _leer_tabla(ruta, columnas):

    if not ruta.exists():
        raise HTTPException(
            status_code=404,
            detail=f'Archivo no disponible: {ruta.name}',
        )

    try:
        datos = pd.read_parquet(ruta)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail=f'No se pudo leer {ruta.name}',
        )

    if datos.empty or not set(columnas).issubset(datos.columns):
        raise HTTPException(
            status_code=500,
            detail=f'Datos incompletos: {ruta.name}',
        )

    try:
        datos['datetime_utc'] = pd.to_datetime(
            datos['datetime_utc'],
            utc=True,
            errors='raise',
        )
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=500,
            detail=f'Fechas incorrectas: {ruta.name}',
        )

    if datos['datetime_utc'].isna().any():
        raise HTTPException(
            status_code=500,
            detail=f'Fechas vacias: {ruta.name}',
        )

    if datos[list(columnas)].isna().any().any():
        raise HTTPException(
            status_code=500,
            detail=f'Valores vacios: {ruta.name}',
        )

    return datos


def _hora_local(valor):

    return pd.Timestamp(valor).tz_convert(ZONA).isoformat()


# Consultar fechas disponibles

@router.get('/disponibles')
def fechas_disponibles():

    fechas = []

    archivos = PROCESSED.glob(
        'planificacion_ml_48h_????-??-??.parquet'
    )

    for archivo in archivos:

        texto = archivo.stem.removeprefix(
            'planificacion_ml_48h_'
        )

        try:
            fecha = date.fromisoformat(texto)
        except ValueError:
            continue

        siguiente = fecha + timedelta(days=2)

        necesarios = [
            _ruta('plan', texto, 'json'),
            _ruta('precios', texto),
            _ruta('operaciones', texto),
            _ruta('baterias', siguiente.isoformat(), 'json'),
        ]

        if all(ruta.exists() for ruta in necesarios):
            fechas.append(texto)

    return {
        'tipo_datos': 'escenario_simulado_ml',
        'fechas': sorted(fechas, reverse=True),
        'nota': (
            'Se comprueba la presencia de archivos, '
            'no su validacion completa.'
        ),
    }


# Resumen de una planificacion

@router.get('/{fecha_consulta}/resumen')
def resumen_48h(fecha_consulta: date):

    texto = fecha_consulta.isoformat()

    meta = _leer_json(
        _ruta('plan', texto, 'json')
    )

    if not _ruta('plan', texto).exists():
        raise HTTPException(
            status_code=404,
            detail='No existe el plan horario.',
        )

    if meta.get('fecha_consulta') != texto:
        raise HTTPException(
            status_code=409,
            detail='La fecha del resumen no coincide.',
        )

    siguiente = (
        fecha_consulta + timedelta(days=2)
    ).isoformat()

    ruta_estado = _ruta(
        'baterias',
        siguiente,
        'json',
    )

    baterias = None

    if ruta_estado.exists():

        estado = _leer_json(ruta_estado)

        if estado.get('fecha_plan_origen') == texto:
            baterias = {
                'fecha': siguiente,
                'soc_medio_pct': estado.get('soc_medio_pct'),
                'soc_minimo_pct': estado.get('soc_minimo_pct'),
                'tipo_estado': estado.get('tipo_estado'),
            }

    return {
        'fecha_consulta': texto,
        'inicio': meta.get('fecha_inicio'),
        'fin_exclusivo': meta.get('fecha_fin_exclusiva'),
        'vehiculos': meta.get('vehiculos'),
        'horas': meta.get('horas'),
        'coste_estimado_eur': meta.get('coste_estimado_eur'),
        'energia_red_kwh': meta.get('energia_recargada_red_kwh'),
        'estado_solver': meta.get('estado_solver'),
        'factibilidad_validada': meta.get('factibilidad_validada'),
        'optimalidad_certificada': meta.get('optimalidad_certificada'),
        'continuidad': baterias,
        'tipo_datos': 'escenario_simulado_ml',
        'aviso': (
            'Precios ML, operaciones y baterias estimadas. '
            'No son resultados reales.'
        ),
    }


# Prediccion de precios hora a hora

@router.get('/{fecha_consulta}/precios')
def precios_48h(fecha_consulta: date):

    datos = _leer_tabla(
        _ruta('precios', fecha_consulta.isoformat()),
        {
            'datetime_utc',
            'precio_predicho_eur_mwh',
        },
    ).sort_values('datetime_utc')

    registros = []

    for fila in datos.itertuples(index=False):

        registros.append({
            'fecha_local': _hora_local(fila.datetime_utc),
            'precio_predicho_eur_mwh': round(
                float(fila.precio_predicho_eur_mwh),
                4,
            ),
        })

    return {
        'fecha_consulta': fecha_consulta.isoformat(),
        'tipo_datos': 'prediccion_ml',
        'horas': len(datos),
        'registros': registros,
    }


def _plan_48h(fecha_consulta):

    return _leer_tabla(
        _ruta('plan', fecha_consulta.isoformat()),
        {
            'vehicle_id',
            'datetime_utc',
            'recarga_red_kwh',
            'coste_estimado_eur',
            'soc_pct',
            'conexion',
            'energia_consumida_kwh',
            'disponible_carga',
        },
    )


# Vista general horaria de toda la flota

@router.get('/{fecha_consulta}/flota')
def flota_48h(fecha_consulta: date):

    plan = _plan_48h(fecha_consulta)

    plan['recargando'] = (
        plan['recarga_red_kwh'] > 0.001
    ).astype(int)

    horas = (
        plan.groupby('datetime_utc', as_index=False)
        .agg(
            energia_red_kwh=('recarga_red_kwh', 'sum'),
            coste_estimado_eur=('coste_estimado_eur', 'sum'),
            cargadores_ocupados=('recargando', 'sum'),
            soc_medio_pct=('soc_pct', 'mean'),
            soc_minimo_pct=('soc_pct', 'min'),
        )
        .sort_values('datetime_utc')
    )

    registros = []

    for fila in horas.itertuples(index=False):

        registros.append({
            'fecha_local': _hora_local(fila.datetime_utc),
            'energia_red_kwh': round(
                float(fila.energia_red_kwh), 3
            ),
            'coste_estimado_eur': round(
                float(fila.coste_estimado_eur), 4
            ),
            'cargadores_ocupados': int(
                round(fila.cargadores_ocupados)
            ),
            'soc_medio_pct': round(
                float(fila.soc_medio_pct), 2
            ),
            'soc_minimo_pct': round(
                float(fila.soc_minimo_pct), 2
            ),
        })

    return {
        'fecha_consulta': fecha_consulta.isoformat(),
        'tipo_datos': 'escenario_simulado_ml',
        'vehiculos': int(plan['vehicle_id'].nunique()),
        'horas': len(horas),
        'registros': registros,
    }


# Plan horario de un vehiculo concreto

@router.get('/{fecha_consulta}/vehiculos/{vehiculo}')
def vehiculo_48h(fecha_consulta: date, vehiculo: str):

    plan = _plan_48h(fecha_consulta)

    datos = plan.loc[
        plan['vehicle_id'] == vehiculo
    ].sort_values('datetime_utc')

    if datos.empty:
        raise HTTPException(
            status_code=404,
            detail='Vehiculo no encontrado en la planificacion.',
        )

    registros = []

    for fila in datos.itertuples(index=False):

        registros.append({
            'fecha_local': _hora_local(fila.datetime_utc),
            'recarga_red_kwh': round(
                float(fila.recarga_red_kwh), 3
            ),
            'consumo_kwh': round(
                float(fila.energia_consumida_kwh), 3
            ),
            'disponible_carga': bool(fila.disponible_carga),
            'conexion': bool(fila.recarga_red_kwh > 0.001),
            'soc_pct': round(
                float(fila.soc_pct), 3
            ),
            'coste_estimado_eur': round(
                float(fila.coste_estimado_eur), 4
            ),
        })

    return {
        'fecha_consulta': fecha_consulta.isoformat(),
        'vehiculo': vehiculo,
        'tipo_datos': 'escenario_simulado_ml',
        'horas': len(datos),
        'energia_total_red_kwh': round(
            float(datos['recarga_red_kwh'].sum()), 3
        ),
        'coste_estimado_eur': round(
            float(datos['coste_estimado_eur'].sum()), 4
        ),
        'registros': registros,
    }

# FLOTIQ | CALENDARIO DE VEHICULOS Y CARGADORES

@router.get('/{fecha_consulta}/calendario')
def calendario_48h(fecha_consulta: date):

    plan = _plan_48h(fecha_consulta).sort_values(
        ['datetime_utc', 'vehicle_id']
    )

    if plan.duplicated(
        ['vehicle_id', 'datetime_utc']
    ).any():
        raise HTTPException(
            status_code=500,
            detail='Hay registros horarios duplicados.',
        )

    vehiculos = sorted(
        plan['vehicle_id'].unique().tolist()
    )

    horas = sorted(
        plan['datetime_utc'].unique().tolist()
    )

    if len(plan) != len(vehiculos) * len(horas):
        raise HTTPException(
            status_code=500,
            detail='La planificacion esta incompleta.',
        )

    cargadores = [
        f'C{i:02d}'
        for i in range(1, 21)
    ]

    registros = []

    # Conservamos el cargador cuando una recarga
    # continua durante varias horas seguidas.

    asignacion_anterior = {}

    for hora, grupo in plan.groupby(
        'datetime_utc',
        sort=True,
    ):

        filas = list(
            grupo.itertuples(index=False)
        )

        activos = sorted(
            str(fila.vehicle_id)
            for fila in filas
            if float(fila.recarga_red_kwh) > 0.001
        )

        if len(activos) > len(cargadores):
            raise HTTPException(
                status_code=500,
                detail='Se superan los 20 cargadores.',
            )

        asignacion_actual = {
            vehiculo: asignacion_anterior[vehiculo]
            for vehiculo in activos
            if vehiculo in asignacion_anterior
        }

        libres = [
            cargador
            for cargador in cargadores
            if cargador not in asignacion_actual.values()
        ]

        for vehiculo in activos:

            if vehiculo not in asignacion_actual:
                asignacion_actual[vehiculo] = libres.pop(0)

        for fila in filas:

            vehiculo = str(fila.vehicle_id)

            energia = float(
                fila.recarga_red_kwh
            )

            disponible = bool(
                fila.disponible_carga
            )

            cargando = energia > 0.001

            if cargando and not disponible:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        f'El vehiculo {vehiculo} tiene '
                        'una recarga fuera de disponibilidad.'
                    ),
                )

            if cargando:
                estado = 'cargando'
            elif not disponible:
                estado = 'trabajando'
            else:
                estado = 'disponible'

            registros.append({
                'vehicle_id': vehiculo,
                'fecha_local': _hora_local(
                    fila.datetime_utc
                ),
                'estado': estado,
                'cargador_id': (
                    asignacion_actual.get(vehiculo)
                    if cargando
                    else None
                ),
                'energia_red_kwh': round(energia, 3),
                'energia_consumida_kwh': round(
                    float(fila.energia_consumida_kwh),
                    3,
                ),
                'soc_pct': round(
                    float(fila.soc_pct),
                    2,
                ),
            })

        asignacion_anterior = asignacion_actual

    dias = sorted({
        registro['fecha_local'][:10]
        for registro in registros
    })

    return {
        'fecha_consulta': fecha_consulta.isoformat(),
        'tipo_datos': 'escenario_simulado_ml',
        'tipo_asignacion': 'cargadores_virtuales',
        'dias': dias,
        'vehiculos': vehiculos,
        'cargadores': cargadores,
        'registros': registros,
        'advertencia': (
            'Los horarios de trabajo son estimaciones '
            'derivadas de patrones historicos. '
            'Los cargadores C01-C20 son asignaciones '
            'propuestas, no puestos fisicos confirmados.'
        ),
    }
