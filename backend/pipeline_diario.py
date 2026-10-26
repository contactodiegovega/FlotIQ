
# FLOTIQ | PIPELINE DIARIO AUTOMATIZADO

import argparse
import math
import shutil
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from backend.actualizar_precios import actualizar_precios
from backend.prediccion_48h import run as generar_precios
from backend.prevision_operaciones_48h import crear_escenario
from backend.planificacion_48h import planificar_48h



ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / 'data' / 'processed'
ZONA = 'Europe/Madrid'


def verificar_cobertura_omie(fecha_consulta):

    ruta = PROCESSED / 'omie_precios_actualizados.parquet'

    if not ruta.exists():
        raise FileNotFoundError(
            f'No existe el archivo de precios OMIE: {ruta}'
        )

    precios = pd.read_parquet(ruta)

    columnas = {
        'datetime_utc',
        'price_eur_mwh',
    }

    if not columnas.issubset(precios.columns):
        raise ValueError(
            'El archivo OMIE no tiene las columnas necesarias.'
        )

    precios['datetime_utc'] = pd.to_datetime(
        precios['datetime_utc'],
        utc=True,
        errors='coerce',
    )

    precios['price_eur_mwh'] = pd.to_numeric(
        precios['price_eur_mwh'],
        errors='coerce',
    )

    if precios.empty:
        raise ValueError('El archivo OMIE esta vacio.')

    if precios['datetime_utc'].isna().any():
        raise ValueError('OMIE contiene fechas invalidas.')

    if precios['datetime_utc'].duplicated().any():
        raise ValueError('OMIE contiene horas duplicadas.')

    if not precios['price_eur_mwh'].map(math.isfinite).all():
        raise ValueError('OMIE contiene precios invalidos.')

    # Dos proximos dias naturales de Madrid

    inicio = pd.Timestamp(
        fecha_consulta + timedelta(days=1),
        tz=ZONA,
    )

    fin = pd.Timestamp(
        fecha_consulta + timedelta(days=3),
        tz=ZONA,
    )

    horas_futuras = pd.date_range(
        inicio.tz_convert('UTC'),
        fin.tz_convert('UTC'),
        freq='h',
        inclusive='left',
    )

    # El modelo ML utiliza estos dos retardos:
    # 72 horas y 168 horas

    disponibles = set(
        precios['datetime_utc'].tolist()
    )

    faltantes = []

    for hora in horas_futuras:

        for lag in (72, 168):

            hora_historica = (
                hora - pd.Timedelta(hours=lag)
            )

            if hora_historica not in disponibles:
                faltantes.append(
                    (lag, hora_historica)
                )

    if faltantes:

        ejemplos = ', '.join(
            f'lag {lag}h: {hora}'
            for lag, hora in faltantes[:5]
        )

        raise RuntimeError(
            f'Faltan {len(faltantes)} referencias '
            f'historicas de OMIE. {ejemplos}'
        )

    ultima_hora = precios['datetime_utc'].max()
    ultima_local = ultima_hora.tz_convert(ZONA)

    hoy = datetime.now(ZoneInfo(ZONA)).date()

    # En una ejecucion real de hoy exigimos precios de hoy

    if (
        fecha_consulta == hoy
        and ultima_local.date() < hoy
    ):
        raise RuntimeError(
            'Los precios OMIE no llegan hasta hoy. '
            'La planificacion diaria queda detenida.'
        )

    print('Cobertura historica OMIE: correcta')
    print('Horas futuras comprobadas:', len(horas_futuras))
    print('Ultima hora OMIE:', ultima_local)


def ejecutar_pipeline(
    fecha_consulta,
    recalcular=False,
    sin_actualizar_omie=False,
):

    fecha_texto = fecha_consulta.isoformat()

    # Impedir recalculos que rompan una cadena publicada.

    fecha_siguiente = (
        fecha_consulta + timedelta(days=1)
    ).isoformat()

    plan_siguiente = PROCESSED / (
        f'planificacion_ml_48h_{fecha_siguiente}.parquet'
    )

    if recalcular and plan_siguiente.exists():
        raise RuntimeError(
            'No se puede recalcular esta planificacion '
            'porque existe un plan posterior que depende '
            'de ella. Es necesario reconstruir la cadena '
            'de forma controlada.'
        )


    inicio_plan = (
        fecha_consulta + timedelta(days=1)
    ).isoformat()

    siguiente_estado = (
        fecha_consulta + timedelta(days=2)
    ).isoformat()

    # Comprobar estado inicial de las baterias

    ruta_estado_inicial = PROCESSED / (
        f'estado_baterias_{inicio_plan}.json'
    )

    if not ruta_estado_inicial.exists():
        raise FileNotFoundError(
            f'No existe el estado inicial: {ruta_estado_inicial}. '
            'Es necesario inicializar las baterias '
            'antes de ejecutar el pipeline.'
        )

    # Identificar resultados existentes

    archivos_salida = [
        PROCESSED / (
            f'prediccion_ml_48h_emitida_{fecha_texto}.parquet'
        ),
        PROCESSED / (
            f'prediccion_ml_48h_emitida_{fecha_texto}.json'
        ),
        PROCESSED / (
            f'prevision_operaciones_48h_emitida_{fecha_texto}.parquet'
        ),
        PROCESSED / (
            f'prevision_operaciones_48h_emitida_{fecha_texto}.json'
        ),
        PROCESSED / (
            f'planificacion_ml_48h_{fecha_texto}.parquet'
        ),
        PROCESSED / (
            f'planificacion_ml_48h_{fecha_texto}.json'
        ),
        PROCESSED / (
            f'estado_baterias_{siguiente_estado}.json'
        ),
    ]

    existentes = [
        ruta
        for ruta in archivos_salida
        if ruta.exists()
    ]

    
    if existentes and not recalcular:

        if len(existentes) != len(archivos_salida):
            raise FileExistsError(
                'Hay resultados parciales para esta fecha. '
                'No se sobrescribiran automaticamente. '
                'Revisa los archivos antes de recalcular.'
            )

        ruta_plan_existente = PROCESSED / (
            f'planificacion_ml_48h_{fecha_texto}.parquet'
        )

        ruta_resumen = PROCESSED / (
            f'planificacion_ml_48h_{fecha_texto}.json'
        )

        ruta_estado_siguiente = PROCESSED / (
            f'estado_baterias_{siguiente_estado}.json'
        )

        resumen = json.loads(
            ruta_resumen.read_text(encoding='utf-8')
        )

        estado = json.loads(
            ruta_estado_siguiente.read_text(
                encoding='utf-8'
            )
        )

        if (
            resumen.get('fecha_consulta') != fecha_texto
            or resumen.get('factibilidad_validada') is not True
        ):
            raise ValueError(
                'La planificacion guardada no esta validada.'
            )

        if (
            estado.get('fecha_plan_origen') != fecha_texto
            or estado.get('fecha_inicio_siguiente_plan')
            != siguiente_estado
            or estado.get('tipo_estado')
            != 'estimado_por_simulacion'
            or len(
                estado.get('energia_inicial_vehiculos', {})
            ) != 50
        ):
            raise ValueError(
                'La continuidad de baterias no es valida.'
            )

        inicio = pd.Timestamp(
            fecha_consulta + timedelta(days=1),
            tz=ZONA,
        )

        fin = pd.Timestamp(
            fecha_consulta + timedelta(days=3),
            tz=ZONA,
        )

        horas_esperadas = pd.date_range(
            inicio.tz_convert('UTC'),
            fin.tz_convert('UTC'),
            freq='h',
            inclusive='left',
        )

        plan = pd.read_parquet(ruta_plan_existente)

        columnas = {'vehicle_id', 'datetime_utc'}

        if not columnas.issubset(plan.columns):
            raise ValueError(
                'Faltan columnas en el plan guardado.'
            )

        horas_plan = pd.to_datetime(
            plan['datetime_utc'],
            utc=True,
        )

        if (
            len(plan) != 50 * len(horas_esperadas)
            or plan['vehicle_id'].nunique() != 50
            or plan.duplicated(
                ['vehicle_id', 'datetime_utc']
            ).any()
            or set(horas_plan) != set(horas_esperadas)
        ):
            raise ValueError(
                'El plan guardado esta incompleto.'
            )

        print()
        print('FLOTIQ | PLAN YA DISPONIBLE')
        print('Fecha:', fecha_texto)
        print('Vehiculos:', 50)
        print('Horas:', len(horas_esperadas))
        print('Factibilidad: validada')
        print('No se han sobrescrito archivos.')

        return ruta_plan_existente


    # Proteger los resultados anteriores

    if existentes and recalcular:

        marca = datetime.now(
            ZoneInfo(ZONA)
        ).strftime('%Y%m%d_%H%M%S_%f')

        carpeta_backup = (
            PROCESSED
            / 'backups_pipeline'
            / f'{fecha_texto}_{marca}'
        )

        carpeta_backup.mkdir(
            parents=True,
            exist_ok=False,
        )

        for ruta in existentes:
            shutil.copy2(
                ruta,
                carpeta_backup / ruta.name,
            )

        print('Backup guardado:', carpeta_backup)

    print()
    print('FLOTIQ | PIPELINE DIARIO')
    print('-' * 45)
    print('Fecha de consulta:', fecha_consulta)
    print('Primer dia:', inicio_plan)
    print(
        'Segundo dia:',
        (fecha_consulta + timedelta(days=2)).isoformat(),
    )

    hoy = datetime.now(ZoneInfo(ZONA)).date()

    if fecha_consulta > hoy:
        print(
            'AVISO: fecha de consulta futura. '
            'Esta ejecucion es una simulacion anticipada.'
        )

    # PASO 0: ACTUALIZAR LOS PRECIOS REALES OMIE

    print()
    print('PASO 0 | Actualizacion de precios OMIE')

    if sin_actualizar_omie:

        print(
            'Actualizacion omitida: se utilizaran '
            'los precios ya almacenados.'
        )

    else:

        actualizar_precios()

    # Comprobar los datos antes del ML

    verificar_cobertura_omie(fecha_consulta)

    # PASO 1: PREDICCION MACHINE LEARNING

    print()
    print('PASO 1 | Prediccion ML de precios')

    generar_precios(
        fecha_consulta,
        ROOT,
    )

    # PASO 2: PREVISION OPERATIVA

    print()
    print('PASO 2 | Prevision operativa')

    crear_escenario(
        fecha_consulta,
    )

    # PASO 3: OPTIMIZACION DE RECARGAS

    print()
    print('PASO 3 | Optimizacion de recargas')

    ruta_plan = planificar_48h(
        fecha_consulta,
        tiempo_maximo=180,
    )

    # PASO 4: VALIDAR CONTINUIDAD DE BATERIAS
    print()
    print('PASO 4 | Validacion de continuidad de baterias')

    dia_primero = fecha_consulta + timedelta(days=1)
    dia_siguiente = fecha_consulta + timedelta(days=2)

    ruta_estado = PROCESSED / (
        f'estado_baterias_{dia_siguiente}.json'
    )

    if not ruta_estado.is_file():
        raise RuntimeError(
            f'Falta el estado de continuidad: {ruta_estado.name}'
        )

    estado = json.loads(
        ruta_estado.read_text(encoding='utf-8')
    )

    if (
        estado.get('fecha_plan_origen')
        != fecha_consulta.isoformat()
        or estado.get('fecha_inicio_siguiente_plan')
        != dia_siguiente.isoformat()
        or estado.get('tipo_estado')
        != 'estimado_por_simulacion'
    ):
        raise RuntimeError(
            'Metadatos de continuidad incorrectos'
        )

    plan_validacion = pd.read_parquet(ruta_plan)

    plan_validacion['datetime_utc'] = pd.to_datetime(
        plan_validacion['datetime_utc'],
        utc=True,
    )

    primer_dia = plan_validacion.loc[
        plan_validacion['datetime_utc']
        .dt.tz_convert(ZONA)
        .dt.date == dia_primero
    ]

    finales = (
        primer_dia.sort_values('datetime_utc')
        .groupby('vehicle_id')
        .tail(1)
    )

    baterias_guardadas = estado.get(
        'energia_inicial_vehiculos'
    )

    if (
        not isinstance(baterias_guardadas, dict)
        or len(finales) != 50
        or set(finales['vehicle_id'])
        != set(baterias_guardadas)
    ):
        raise RuntimeError(
            'Continuidad incompleta para los 50 vehiculos'
        )

    for fila in finales.itertuples(index=False):
        energia_plan = float(fila.energia_bateria_kwh)
        energia_guardada = float(
            baterias_guardadas[fila.vehicle_id]
        )

        if abs(energia_plan - energia_guardada) > 0.025:
            raise RuntimeError(
                f'Continuidad incorrecta: {fila.vehicle_id}'
            )

    print('Continuidad validada: 50 vehiculos')
    print('Estado existente conservado:', ruta_estado.name)


    print()
    print('FLOTIQ | PIPELINE FINALIZADO')
    print('-' * 45)
    print('Planificacion:', ruta_plan)
    print('Estado siguiente jornada:', ruta_estado)
    print('Resultado: escenario simulado generado')

    return ruta_plan


if __name__ == '__main__':

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--fecha-consulta',
        default=None,
    )

    parser.add_argument(
        '--recalcular',
        action='store_true',
    )

    parser.add_argument(
        '--sin-actualizar-omie',
        action='store_true',
    )

    args = parser.parse_args()

    fecha = (
        date.fromisoformat(args.fecha_consulta)
        if args.fecha_consulta
        else datetime.now(ZoneInfo(ZONA)).date()
    )

    ejecutar_pipeline(
        fecha,
        recalcular=args.recalcular,
        sin_actualizar_omie=args.sin_actualizar_omie,
    )
