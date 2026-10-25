# FLOTIQ: escenario operativo de los dos días siguientes.


import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

TZ = "Europe/Madrid"
ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "processed"


def crear_escenario(fecha_consulta):
    load_dotenv(ROOT / ".env")

    url = os.getenv("DATABASE_URL")

    if not url:
        raise RuntimeError(
            "Falta DATABASE_URL en el archivo .env"
        )

    query = text("""
        SELECT
            a.vehicle_id,
            s.shift_id,
            s.start_time AS inicio_turno,
            s.end_time AS fin_turno,
            t.trip_id,
            t.start_time AS inicio_viaje,
            t.end_time AS fin_viaje,
            t.energy_consumed_kwh
        FROM assignments a
        JOIN shifts s ON s.shift_id = a.shift_id
        LEFT JOIN trips t
            ON t.assignment_id = a.assignment_id
    """)

    engine = create_engine(url)

    try:
        with engine.connect() as con:
            operaciones = pd.read_sql(query, con)
    finally:
        engine.dispose()

    if operaciones.empty:
        raise RuntimeError(
            "No hay operaciones historicas"
        )

    # Convertir las fechas.

    columnas_fecha = [
        "inicio_turno",
        "fin_turno",
        "inicio_viaje",
        "fin_viaje",
    ]

    for col in columnas_fecha:
        operaciones[col] = pd.to_datetime(
            operaciones[col]
        )

        if operaciones[col].dt.tz is not None:
            operaciones[col] = (
                operaciones[col]
                .dt.tz_convert(TZ)
                .dt.tz_localize(None)
            )

    vehiculos = sorted(
        operaciones["vehicle_id"].dropna().unique()
    )

    if len(vehiculos) != 50:
        raise RuntimeError(
            f"Esperaba 50 vehiculos, encuentro {len(vehiculos)}"
        )

    # Separar turnos y viajes sin duplicados.

    turnos = operaciones[
        [
            "vehicle_id",
            "shift_id",
            "inicio_turno",
            "fin_turno",
        ]
    ].drop_duplicates()

    viajes = (
        operaciones
        .dropna(subset=["trip_id"])
        .drop_duplicates(subset=["trip_id"])
    )

    if (
        turnos["fin_turno"]
        <= turnos["inicio_turno"]
    ).any():
        raise ValueError(
            "Hay turnos con duracion incorrecta"
        )

    # Seleccionar la ultima semana historica
    # de lunes a domingo.

    ultimo_instante = (
        turnos["fin_turno"].max()
        - pd.Timedelta(microseconds=1)
    )

    lunes = (
        ultimo_instante.normalize()
        - pd.Timedelta(days=ultimo_instante.dayofweek)
    )

    proximo_lunes = lunes + pd.Timedelta(days=7)

    horas_base = pd.date_range(
        lunes,
        proximo_lunes,
        freq="h",
        inclusive="left",
    )

    if len(horas_base) != 168:
        raise RuntimeError(
            "La semana historica no tiene 168 horas"
        )

    # Crear disponibilidad horaria por vehiculo.

    plantilla = pd.MultiIndex.from_product(
        [vehiculos, horas_base],
        names=["vehicle_id", "hora_base"],
    ).to_frame(index=False)

    plantilla["disponible_carga"] = True

    for t in turnos.itertuples(index=False):
        inicio = max(t.inicio_turno, lunes)
        fin = min(t.fin_turno, proximo_lunes)

        if inicio >= fin:
            continue

        mascara = (
            (plantilla["vehicle_id"] == t.vehicle_id)
            & (plantilla["hora_base"] < fin)
            & (
                plantilla["hora_base"]
                + pd.Timedelta(hours=1)
                > inicio
            )
        )

        plantilla.loc[
            mascara, "disponible_carga"
        ] = False

    # Distribuir el consumo de cada viaje
    # proporcionalmente entre las horas.

    consumos = []

    for v in viajes.itertuples(index=False):
        if (
            pd.isna(v.inicio_viaje)
            or pd.isna(v.fin_viaje)
            or pd.isna(v.energy_consumed_kwh)
        ):
            raise ValueError(
                f"Viaje {v.trip_id} sin datos"
            )

        duracion = (
            v.fin_viaje - v.inicio_viaje
        ).total_seconds()

        energia = float(v.energy_consumed_kwh)

        if duracion <= 0 or energia < 0:
            raise ValueError(
                f"Viaje {v.trip_id} incorrecto"
            )

        instante = max(v.inicio_viaje, lunes)
        fin = min(v.fin_viaje, proximo_lunes)

        while instante < fin:
            hora = instante.floor("h")

            tramo_fin = min(
                hora + pd.Timedelta(hours=1),
                fin,
            )

            energia_hora = (
                energia
                * (tramo_fin - instante).total_seconds()
                / duracion
            )

            consumos.append(
                (
                    v.vehicle_id,
                    hora,
                    energia_hora,
                )
            )

            instante = tramo_fin

    if not consumos:
        raise RuntimeError(
            "No hay viajes en la semana seleccionada"
        )

    energia_hora = pd.DataFrame(
        consumos,
        columns=[
            "vehicle_id",
            "hora_base",
            "energia_consumida_kwh",
        ],
    )

    energia_hora = (
        energia_hora
        .groupby(
            ["vehicle_id", "hora_base"],
            as_index=False,
        )["energia_consumida_kwh"]
        .sum()
    )

    plantilla = plantilla.merge(
        energia_hora,
        on=["vehicle_id", "hora_base"],
        how="left",
        validate="one_to_one",
    )

    plantilla["energia_consumida_kwh"] = (
        plantilla["energia_consumida_kwh"].fillna(0)
    )

    # Validar que no haya consumo fuera de turno.

    inconsistencias = (
        plantilla["disponible_carga"]
        & (plantilla["energia_consumida_kwh"] > 0.001)
    )

    if inconsistencias.any():
        raise RuntimeError(
            "Hay consumo en horas marcadas como libres"
        )

    # Construir el perfil semanal.

    plantilla["dia_semana"] = (
        plantilla["hora_base"].dt.dayofweek
    )

    plantilla["hora_local"] = (
        plantilla["hora_base"].dt.hour
    )

    plantilla = plantilla.drop(
        columns="hora_base"
    )

    # Generar los dos siguientes dias naturales.

    inicio = pd.Timestamp(
        fecha_consulta + timedelta(days=1),
        tz=TZ,
    )

    fin = pd.Timestamp(
        fecha_consulta + timedelta(days=3),
        tz=TZ,
    )

    horas_futuras = pd.date_range(
        inicio,
        fin,
        freq="h",
        inclusive="left",
    )

    base_futura = pd.DataFrame({
        "fecha_local": horas_futuras,
        "datetime_utc": horas_futuras.tz_convert("UTC"),
        "dia_semana": horas_futuras.dayofweek,
        "hora_local": horas_futuras.hour,
    })

    # Asignar el perfil correspondiente
    # a cada uno de los 50 vehiculos.

    indices = pd.MultiIndex.from_product(
        [vehiculos, range(len(base_futura))],
        names=["vehicle_id", "paso"],
    ).to_frame(index=False)

    indices = indices.merge(
        base_futura.reset_index(names="paso"),
        on="paso",
        how="left",
        validate="many_to_one",
    )

    resultado = indices.merge(
        plantilla,
        on=[
            "vehicle_id",
            "dia_semana",
            "hora_local",
        ],
        how="left",
        validate="many_to_one",
    )

    resultado = resultado.drop(
        columns=[
            "paso",
            "dia_semana",
            "hora_local",
        ]
    )

    # Validaciones finales.

    columnas_criticas = [
        "disponible_carga",
        "energia_consumida_kwh",
    ]

    if resultado[columnas_criticas].isna().any().any():
        raise RuntimeError(
            "Faltan datos para algunos vehiculos u horas"
        )

    if resultado.duplicated(
        ["vehicle_id", "datetime_utc"]
    ).any():
        raise RuntimeError(
            "Hay horas UTC duplicadas"
        )

    resultado["tipo_escenario"] = (
        "replica_historico_semanal"
    )

    resultado = (
        resultado
        .sort_values(["vehicle_id", "datetime_utc"])
        .reset_index(drop=True)
    )

    # Guardar resultados.

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    ruta = OUTPUT / (
        "prevision_operaciones_48h_emitida_"
        f"{fecha_consulta.isoformat()}.parquet"
    )

    resultado.to_parquet(
        ruta,
        index=False,
    )

    metadata = {
        "fecha_consulta": fecha_consulta.isoformat(),
        "semana_base_inicio": str(lunes),
        "semana_base_fin_exclusivo": str(proximo_lunes),
        "vehiculos": len(vehiculos),
        "horas_horizonte": len(horas_futuras),
        "energia_prevista_kwh": round(
            float(resultado["energia_consumida_kwh"].sum()),
            2,
        ),
        "tipo": (
            "escenario_simulado; "
            "no son turnos futuros confirmados"
        ),
    }

    ruta.with_suffix(".json").write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Mostrar resumen.

    print()
    print("FLOTIQ | ESCENARIO OPERATIVO 48H")
    print("-" * 45)
    print("Consulta:", fecha_consulta)
    print(
        "Semana historica:",
        lunes.date(),
        "a",
        (proximo_lunes - pd.Timedelta(days=1)).date(),
    )
    print("Vehiculos:", len(vehiculos))
    print("Horas futuras:", len(horas_futuras))
    print("Registros:", len(resultado))
    print(
        "Consumo estimado:",
        round(resultado["energia_consumida_kwh"].sum(), 2),
        "kWh",
    )
    print("Guardado:", ruta)
    print(
        "AVISO: se han replicado patrones historicos, "
        "no turnos confirmados"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--fecha-consulta",
        default=None,
        help="YYYY-MM-DD; por defecto hoy en Madrid",
    )

    args = parser.parse_args()

    fecha = (
        date.fromisoformat(args.fecha_consulta)
        if args.fecha_consulta
        else datetime.now(ZoneInfo(TZ)).date()
    )

    crear_escenario(fecha)
