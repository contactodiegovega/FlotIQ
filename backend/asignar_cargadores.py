
# FLOTIQ | ASIGNACION DE CARGADORES A RECARGAS OPTIMIZADAS

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "processed"

NUM_CARGADORES = 20
POTENCIA_CARGADOR_KW = 11
POTENCIA_MAXIMA_KW = 150
TOL = 0.01


def asignar_cargadores(nombre_archivo):
    ruta_entrada = DATA_DIR / nombre_archivo

    df = pd.read_parquet(ruta_entrada).copy()

    columnas = [
        "vehicle_id",
        "hora",
        "recarga_red_kwh",
        "conectado",
    ]

    if not all(col in df.columns for col in columnas):
        raise ValueError("Faltan columnas necesarias.")

    df["hora"] = pd.to_datetime(df["hora"])

    if df.duplicated(["vehicle_id", "hora"]).any():
        raise ValueError(
            "Existen registros duplicados por vehículo y hora."
        )

    df = df.sort_values(
        ["hora", "vehicle_id"]
    ).reset_index(drop=True)

    if (
        df["recarga_red_kwh"].isna().any()
        or df["conectado"].isna().any()
    ):
        raise ValueError("Hay datos de carga incompletos.")

    df["cargador_id"] = None

    cargadores = [
        f"C{i:02d}"
        for i in range(1, NUM_CARGADORES + 1)
    ]

    # Recordar el cargador de la hora anterior.
    asignaciones_anteriores = {}

    for hora, grupo in df.groupby("hora", sort=True):
        activos = grupo[
            grupo["recarga_red_kwh"] > TOL
        ].copy()

        if len(activos) > NUM_CARGADORES:
            raise ValueError(
                f"Exceso de vehículos cargando a las {hora}: "
                f"{len(activos)}"
            )

        if (
            activos["recarga_red_kwh"]
            > POTENCIA_CARGADOR_KW + TOL
        ).any():
            raise ValueError(
                f"Exceso de potencia por cargador: {hora}"
            )

        energia_hora = activos["recarga_red_kwh"].sum()

        if energia_hora > POTENCIA_MAXIMA_KW + TOL:
            raise ValueError(
                f"Exceso de potencia de la instalación: {hora}"
            )

        if (activos["conectado"] < 0.5).any():
            raise ValueError(
                f"Vehículo cargando sin conexión: {hora}"
            )

        ocupados = set()
        nuevas_asignaciones = {}

        # Priorizar continuidad en el mismo cargador.
        for indice, fila in activos.iterrows():
            vehiculo = fila["vehicle_id"]

            anterior = asignaciones_anteriores.get(vehiculo)

            if anterior and anterior not in ocupados:
                nuevas_asignaciones[vehiculo] = anterior
                ocupados.add(anterior)
                df.at[indice, "cargador_id"] = anterior

        # Asignar el primer cargador disponible
        # a quienes todavía no tienen uno.
        for indice, fila in activos.iterrows():
            vehiculo = fila["vehicle_id"]

            if vehiculo in nuevas_asignaciones:
                continue

            disponibles = [
                c for c in cargadores
                if c not in ocupados
            ]

            if not disponibles:
                raise ValueError(
                    f"No quedan cargadores libres: {hora}"
                )

            elegido = disponibles[0]

            nuevas_asignaciones[vehiculo] = elegido
            ocupados.add(elegido)
            df.at[indice, "cargador_id"] = elegido

        asignaciones_anteriores = nuevas_asignaciones

    # Auditoría final de asignaciones.
    activos_final = df[
        df["recarga_red_kwh"] > TOL
    ]

    if activos_final["cargador_id"].isna().any():
        raise ValueError(
            "Hay recargas sin cargador asignado."
        )

    if activos_final.duplicated(
        ["hora", "cargador_id"]
    ).any():
        raise ValueError(
            "Dos vehículos comparten cargador en una hora."
        )

    if df.loc[
        df["recarga_red_kwh"] <= TOL,
        "cargador_id",
    ].notna().any():
        raise ValueError(
            "Se asignaron cargadores a horas sin recarga."
        )

    nombre_salida = (
        Path(nombre_archivo).stem
        + "_con_cargadores.parquet"
    )

    ruta_salida = DATA_DIR / nombre_salida

    df.to_parquet(ruta_salida, index=False)

    print(f"\nARCHIVO: {nombre_archivo}")
    print("Registros:", len(df))
    print(
        "Vehículos:",
        df["vehicle_id"].nunique()
    )
    print(
        "Máximo simultáneo:",
        activos_final.groupby("hora").size().max()
    )
    print(
        "Cargadores utilizados:",
        activos_final["cargador_id"].nunique()
    )
    print(
        "Horas de recarga asignadas:",
        len(activos_final)
    )
    print("Validación: correcta")
    print("Guardado en:", ruta_salida)

    return df


if __name__ == "__main__":
    asignar_cargadores(
        "recargas_baseline_semana.parquet"
    )

    asignar_cargadores(
        "recargas_ml_semana.parquet"
    )
