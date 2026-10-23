
# FLOTIQ | GENERAR OPERACIONES SIMULADAS PARA UNA SEMANA FUTURA

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SEMANA_ORIGEN = pd.Timestamp("2026-09-21")
FIN_SEMANA_ORIGEN = SEMANA_ORIGEN + pd.Timedelta(days=7)

ZONA_HORARIA = "Europe/Madrid"
NUM_VEHICULOS = 50


def cargar_operaciones_historicas():
    """
    Recupera de Supabase los turnos y viajes de
    la simulación del 21 al 27 de septiembre de 2026.
    No modifica ningún registro de la base de datos.
    """

    load_dotenv(PROJECT_ROOT / ".env")

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "No se encontró DATABASE_URL en el archivo .env"
        )

    consulta = text("""
        SELECT
            a.vehicle_id,
            s.shift_id,
            s.start_time AS inicio_turno,
            s.end_time AS fin_turno,
            t.trip_id,
            t.start_time AS inicio_viaje,
            t.end_time AS fin_viaje,
            t.distance_km,
            t.energy_consumed_kwh
        FROM assignments a
        INNER JOIN shifts s
            ON a.shift_id = s.shift_id
        LEFT JOIN trips t
            ON a.assignment_id = t.assignment_id
        WHERE
            s.start_time >= :inicio
            AND s.start_time < :fin
        ORDER BY
            a.vehicle_id,
            s.start_time,
            t.start_time
    """)

    engine = create_engine(database_url)

    try:
        with engine.connect() as conexion:
            operaciones = pd.read_sql(
                consulta,
                conexion,
                params={
                    "inicio": SEMANA_ORIGEN.to_pydatetime(),
                    "fin": FIN_SEMANA_ORIGEN.to_pydatetime(),
                },
            )
    finally:
        engine.dispose()

    if operaciones.empty:
        raise ValueError(
            "No hay operaciones para la semana histórica."
        )

    columnas_fecha = [
        "inicio_turno",
        "fin_turno",
        "inicio_viaje",
        "fin_viaje",
    ]

    for columna in columnas_fecha:
        operaciones[columna] = pd.to_datetime(
            operaciones[columna]
        )

        if operaciones[columna].dt.tz is not None:
            raise ValueError(
                "Las fechas históricas deben estar en "
                "hora local sin zona horaria, como en el notebook."
            )

    if operaciones["vehicle_id"].nunique() != NUM_VEHICULOS:
        raise ValueError(
            "La plantilla no contiene los 50 vehículos."
        )

    return operaciones


def generar_operaciones_semana(fecha_inicio):
    """
    Proyecta el patrón histórico de operaciones
    sobre otra semana.

    Devuelve una fila por vehículo y hora con:
      vehicle_id
      hora
      disponible_carga
      energia_consumida_kwh

    Es una simulación, no una previsión real de viajes.
    """

    lunes = pd.Timestamp(fecha_inicio)

    if lunes.tzinfo is not None:
        raise ValueError(
            "Indica la fecha como AAAA-MM-DD."
        )

    if lunes != lunes.normalize() or lunes.weekday() != 0:
        raise ValueError(
            "La fecha de inicio debe ser un lunes."
        )

    inicio_local = lunes.tz_localize(ZONA_HORARIA)

    fin_local = (
        lunes + pd.Timedelta(days=7)
    ).tz_localize(ZONA_HORARIA)

    horas_reales = pd.date_range(
        start=inicio_local,
        end=fin_local,
        freq="h",
        inclusive="left",
    )

    # Primera versión: el optimizador semanal actual
    # utiliza siete días de 24 horas.
    if len(horas_reales) != 168:
        raise ValueError(
            "Esta semana tiene un cambio horario. "
            "Todavía debemos adaptar el optimizador "
            "para trabajar con 167 o 169 horas."
        )

    operaciones = cargar_operaciones_historicas()

    # Cambiar las fechas sin alterar duraciones,
    # vehículos, turnos ni energía de los viajes.
    desplazamiento = lunes - SEMANA_ORIGEN

    for columna in [
        "inicio_turno",
        "fin_turno",
        "inicio_viaje",
        "fin_viaje",
    ]:
        operaciones[columna] = (
            operaciones[columna] + desplazamiento
        )

    vehiculos = sorted(
        operaciones["vehicle_id"].unique()
    )

    horas = pd.date_range(
        start=lunes,
        periods=168,
        freq="h",
    )

    # Matriz completa de vehículos y horas.
    disponibilidad = (
        pd.MultiIndex.from_product(
            [vehiculos, horas],
            names=["vehicle_id", "hora"],
        )
        .to_frame(index=False)
    )

    disponibilidad["disponible_carga"] = True

    # Bloquear cualquier hora que coincida con un turno.
    turnos = (
        operaciones[
            [
                "vehicle_id",
                "shift_id",
                "inicio_turno",
                "fin_turno",
            ]
        ]
        .drop_duplicates()
    )

    if not (
        turnos["fin_turno"] > turnos["inicio_turno"]
    ).all():
        raise ValueError(
            "La plantilla contiene turnos inválidos."
        )

    for turno in turnos.itertuples(index=False):
        bloqueado = (
            (
                disponibilidad["vehicle_id"]
                == turno.vehicle_id
            )
            & (
                disponibilidad["hora"]
                < turno.fin_turno
            )
            & (
                disponibilidad["hora"]
                + pd.Timedelta(hours=1)
                > turno.inicio_turno
            )
        )

        disponibilidad.loc[
            bloqueado,
            "disponible_carga",
        ] = False

    # Distribuir la energía de los viajes por hora.
    registros_consumo = []

    for viaje in operaciones.itertuples(index=False):

        # LEFT JOIN permite turnos sin viajes.
        if pd.isna(viaje.trip_id):
            continue

        inicio = pd.Timestamp(viaje.inicio_viaje)
        fin = pd.Timestamp(viaje.fin_viaje)

        energia = float(viaje.energy_consumed_kwh)

        duracion = (fin - inicio).total_seconds()

        if duracion <= 0 or energia < 0:
            raise ValueError(
                f"Viaje inválido: {viaje.trip_id}"
            )

        momento = inicio

        while momento < fin:
            hora = momento.floor("h")

            fin_bloque = min(
                hora + pd.Timedelta(hours=1),
                fin,
            )

            segundos = (
                fin_bloque - momento
            ).total_seconds()

            energia_bloque = (
                energia * segundos / duracion
            )

            registros_consumo.append({
                "vehicle_id": viaje.vehicle_id,
                "hora": hora,
                "energia_consumida_kwh": energia_bloque,
            })

            momento = fin_bloque

    if not registros_consumo:
        raise ValueError(
            "La plantilla histórica no contiene viajes."
        )

    consumo_horario = (
        pd.DataFrame(registros_consumo)
        .groupby(
            ["vehicle_id", "hora"],
            as_index=False,
        )["energia_consumida_kwh"]
        .sum()
    )

    # Unir disponibilidad con demanda energética.
    resultado = disponibilidad.merge(
        consumo_horario,
        on=["vehicle_id", "hora"],
        how="left",
        validate="one_to_one",
    )

    resultado["energia_consumida_kwh"] = (
        resultado["energia_consumida_kwh"]
        .fillna(0.0)
    )

    # Validaciones de integridad.
    energia_original = float(
        operaciones["energy_consumed_kwh"].sum()
    )

    energia_horaria = float(
        resultado["energia_consumida_kwh"].sum()
    )

    if abs(energia_original - energia_horaria) > 0.01:
        raise ValueError(
            "Se ha perdido energía al distribuir los viajes."
        )

    inconsistencias = resultado[
        resultado["disponible_carga"]
        & (resultado["energia_consumida_kwh"] > 0.001)
    ]

    if not inconsistencias.empty:
        raise ValueError(
            "Hay consumo de vehículos durante horas "
            "marcadas como disponibles para cargar."
        )

    if len(resultado) != NUM_VEHICULOS * 168:
        raise ValueError(
            "La matriz de operaciones está incompleta."
        )

    return (
        resultado.sort_values(
            ["vehicle_id", "hora"]
        )
        .reset_index(drop=True)
    )
