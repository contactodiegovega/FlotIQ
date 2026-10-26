
"""Escenarios diarios consistentes para FlotIQ.

Cada fecha usa una referencia oficial unica.
No modifica ni guarda archivos de planificacion.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from backend.optimizador import (
    CAPACIDAD_BATERIA_KWH,
    EFICIENCIA_CARGA,
    SOC_MINIMO,
    SOC_OBJETIVO,
    optimizar_recargas,
)

PROCESSED = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "processed"
)

TZ = "Europe/Madrid"

CAMPOS_COMPARACION = [
    "recarga_red_kwh",
    "energia_bateria_kwh",
    "conexion",
    "soc_pct",
    "coste_estimado_eur",
    "precio_predicho_eur_mwh",
    "energia_consumida_kwh",
    "disponible_carga",
]

CAMPOS_RESULTADO = [
    "vehicle_id",
    "hora",
    "recarga_red_kwh",
    "energia_bateria_kwh",
    "conexion",
    "soc_pct",
    "coste_estimado_eur",
]


def _horas_dia(dia):
    inicio = pd.Timestamp(
        dia, tz=TZ
    ).tz_convert("UTC")

    fin = pd.Timestamp(
        dia + timedelta(days=1), tz=TZ
    ).tz_convert("UTC")

    return pd.date_range(
        inicio,
        fin,
        freq="h",
        inclusive="left",
    )


def _extraer_dia(ruta, dia, vehiculos):
    try:
        df = pd.read_parquet(ruta)
    except Exception as error:
        raise ValueError(
            f"No se puede leer {ruta.name}: {error}"
        ) from error

    necesarias = set(CAMPOS_COMPARACION) | {
        "datetime_utc",
        "vehicle_id",
    }

    if not necesarias.issubset(df.columns):
        raise ValueError(
            f"Columnas incompletas en {ruta.name}"
        )

    df = df.copy()

    df["datetime_utc"] = pd.to_datetime(
        df["datetime_utc"], utc=True
    )

    df["vehicle_id"] = (
        df["vehicle_id"].astype(str)
    )

    df = df.loc[
        df["datetime_utc"]
        .dt.tz_convert(TZ)
        .dt.date == dia
    ].sort_values(
        ["datetime_utc", "vehicle_id"]
    ).reset_index(drop=True)

    horas = _horas_dia(dia)

    if (
        df.duplicated(
            ["datetime_utc", "vehicle_id"]
        ).any()
        or len(df) != len(horas) * len(vehiculos)
        or set(df["datetime_utc"]) != set(horas)
        or set(df["vehicle_id"]) != set(vehiculos)
        or df[CAMPOS_COMPARACION].isna().any().any()
    ):
        raise ValueError(
            f"El dia {dia} esta incompleto en {ruta.name}"
        )

    for col in CAMPOS_COMPARACION:
        if col == "disponible_carga":
            continue

        valores = pd.to_numeric(
            df[col], errors="coerce"
        )

        if not np.isfinite(valores).all():
            raise ValueError(
                f"Dato invalido {col} en {ruta.name}"
            )

    return df


def _referencia(dia, vehiculos):
    """Elegir la primera emision oficial del dia."""

    opciones = []

    for emision in (
        dia - timedelta(days=2),
        dia - timedelta(days=1),
    ):
        ruta = PROCESSED / (
            f"planificacion_ml_48h_{emision}.parquet"
        )

        if ruta.is_file():
            opciones.append(
                (
                    emision,
                    _extraer_dia(
                        ruta, dia, vehiculos
                    ),
                )
            )

    if not opciones:
        raise ValueError(
            f"No existe un plan oficial para {dia}"
        )

    # Si el dia aparece en dos planes, comprobar
    # que los datos oficiales ya son consistentes.

    if len(opciones) == 2:
        uno = opciones[0][1].set_index(
            ["vehicle_id", "datetime_utc"]
        )

        dos = opciones[1][1].set_index(
            ["vehicle_id", "datetime_utc"]
        )

        if not uno.index.equals(dos.index):
            raise ValueError(
                f"Las versiones de {dia} difieren en horas"
            )

        for col in CAMPOS_COMPARACION:
            if col == "disponible_carga":
                igual = uno[col].equals(dos[col])
            else:
                igual = np.allclose(
                    uno[col].to_numpy(dtype=float),
                    dos[col].to_numpy(dtype=float),
                    atol=0.0002,
                    rtol=0,
                )

            if not igual:
                raise ValueError(
                    f"El dia oficial {dia} difiere en {col}"
                )

    return opciones[0]


def _bordes(ref):
    """Baterias iniciales y finales oficiales del dia."""

    iniciales = {}
    finales = {}

    minimo = CAPACIDAD_BATERIA_KWH * SOC_MINIMO
    maximo = CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO

    for vehiculo, grupo in ref.groupby("vehicle_id"):
        grupo = grupo.sort_values("datetime_utc")

        primera = grupo.iloc[0]
        ultima = grupo.iloc[-1]

        inicial = (
            float(primera["energia_bateria_kwh"])
            + float(primera["energia_consumida_kwh"])
            - float(primera["recarga_red_kwh"])
            * EFICIENCIA_CARGA
        )

        final = float(
            ultima["energia_bateria_kwh"]
        )

        if not all(np.isfinite([inicial, final])):
            raise ValueError(
                f"Bateria no finita para {vehiculo}"
            )

        if not (
            minimo - 0.002
            <= inicial
            <= maximo + 0.002
        ):
            raise ValueError(
                f"Bateria inicial invalida: {vehiculo}"
            )

        if not (
            minimo - 0.002
            <= final
            <= maximo + 0.002
        ):
            raise ValueError(
                f"Bateria final invalida: {vehiculo}"
            )

        iniciales[vehiculo] = min(
            max(inicial, minimo), maximo
        )

        finales[vehiculo] = min(
            max(final, minimo), maximo
        )

    return iniciales, finales


def _precios_dia(
    modelo,
    emision,
    ref,
    resolver_precios,
):
    dia = (
        ref["datetime_utc"]
        .dt.tz_convert(TZ)
        .dt.date.iloc[0]
    )

    horas = _horas_dia(dia)

    if modelo == "hgb":
        # Usar exactamente el precio oficial del dia.
        agrupados = ref.groupby(
            "datetime_utc"
        )["precio_predicho_eur_mwh"]

        limites = agrupados.agg(["min", "max"])

        if (
            (limites["max"] - limites["min"]).abs()
            > 0.0001
        ).any():
            raise ValueError(
                "Precios oficiales diferentes por vehiculo"
            )

        valores = (
            agrupados.first()
            .reindex(horas)
            .to_numpy(dtype=float)
        )

    else:
        # Otros modelos: utilizar la emision de referencia
        # para evitar comparar predicciones distintas.

        ruta = PROCESSED / (
            f"prediccion_ml_48h_emitida_{emision}.parquet"
        )

        if not ruta.is_file():
            raise ValueError(
                f"Faltan predicciones: {ruta.name}"
            )

        datos = pd.read_parquet(ruta).copy()

        necesarias = {
            "datetime_utc",
            "precio_predicho_eur_mwh",
            "precio_baseline_eur_mwh",
        }

        if not necesarias.issubset(datos.columns):
            raise ValueError(
                f"Predicciones incompletas: {ruta.name}"
            )

        datos["datetime_utc"] = pd.to_datetime(
            datos["datetime_utc"], utc=True
        )

        horizonte = pd.date_range(
            pd.Timestamp(
                emision + timedelta(days=1), tz=TZ
            ).tz_convert("UTC"),
            pd.Timestamp(
                emision + timedelta(days=3), tz=TZ
            ).tz_convert("UTC"),
            freq="h",
            inclusive="left",
        )

        if (
            len(datos) != len(horizonte)
            or datos["datetime_utc"].duplicated().any()
            or set(datos["datetime_utc"]) != set(horizonte)
        ):
            raise ValueError(
                f"Horizonte incompleto: {ruta.name}"
            )

        predichos = resolver_precios(
            modelo, datos, horizonte
        )

        valores = (
            pd.Series(predichos, index=horizonte)
            .reindex(horas)
            .to_numpy(dtype=float)
        )

    if (
        len(valores) != len(horas)
        or not np.isfinite(valores).all()
    ):
        raise ValueError(
            "Precios invalidos del dia simulado"
        )

    return pd.DataFrame({
        "hora": horas,
        "price_eur_mwh": valores,
    })



def simular_48h_por_dias(
    *,
    fecha_consulta: date,
    vehiculos: list[str],
    modelo: str,
    cambio_demanda_pct: int,
    dia_demanda: str,
    resolver_precios,
):
    """
    Simula por fechas naturales, propagando la bateria
    entre los dos dias.

    No modifica ni guarda los planes oficiales.
    """

    dias = [
        fecha_consulta + timedelta(days=1),
        fecha_consulta + timedelta(days=2),
    ]

    fragmentos = []
    operaciones = []
    precios = []
    certificados = []

    estado_propagado = None
    cierre_oficial_anterior = None
    entrada_segundo_dia = None
    cierre_primer_dia = None

    for indice_dia, dia in enumerate(dias):

        emision, referencia = _referencia(
            dia, vehiculos
        )

        iniciales_oficiales, finales_oficiales = (
            _bordes(referencia)
        )

        horas = _horas_dia(dia)

        # Validar la continuidad de los planes oficiales.

        if cierre_oficial_anterior is not None:
            for v in vehiculos:
                if abs(
                    cierre_oficial_anterior[v]
                    - iniciales_oficiales[v]
                ) > 0.025:
                    raise ValueError(
                        "Continuidad oficial incorrecta "
                        f"entre dias: {v}"
                    )

        # El primer dia comienza con las baterias oficiales.
        # El segundo hereda las baterias del escenario.

        entrada = (
            dict(iniciales_oficiales)
            if estado_propagado is None
            else dict(estado_propagado)
        )

        if indice_dia == 1:
            entrada_segundo_dia = dict(entrada)

        precios_dia = _precios_dia(
            modelo,
            emision,
            referencia,
            resolver_precios,
        )

        opera = referencia[
            [
                "vehicle_id",
                "datetime_utc",
                "disponible_carga",
                "energia_consumida_kwh",
            ]
        ].rename(
            columns={"datetime_utc": "hora"}
        ).copy()

        opera["hora"] = pd.to_datetime(
            opera["hora"], utc=True
        )

        # Determinar si este dia tiene demanda modificada.

        afectar = (
            dia_demanda == "ambos"
            or (
                dia_demanda == "primero"
                and indice_dia == 0
            )
            or (
                dia_demanda == "segundo"
                and indice_dia == 1
            )
        )

        cambiar_consumo = (
            afectar and cambio_demanda_pct != 0
        )

        if cambiar_consumo:
            opera["energia_consumida_kwh"] *= (
                1 + cambio_demanda_pct / 100
            )

        misma_entrada = all(
            abs(
                entrada[v]
                - iniciales_oficiales[v]
            ) <= 0.002
            for v in vehiculos
        )

        # Sin cambios, reutilizar el dia oficial.
        # Si cambia el consumo, el precio o la bateria
        # de entrada, ejecutar el optimizador.

        reusar_oficial = (
            modelo == "hgb"
            and not cambiar_consumo
            and misma_entrada
        )

        if reusar_oficial:

            solucion = referencia.rename(
                columns={"datetime_utc": "hora"}
            )[CAMPOS_RESULTADO].copy()

            ruta_meta = PROCESSED / (
                f"planificacion_ml_48h_{emision}.json"
            )

            if ruta_meta.is_file():
                try:
                    meta = json.loads(
                        ruta_meta.read_text(
                            encoding="utf-8"
                        )
                    )

                except (OSError, ValueError) as error:
                    raise ValueError(
                        f"Metadatos invalidos: {ruta_meta.name}"
                    ) from error

                certificados.append(
                    bool(
                        meta.get(
                            "optimalidad_certificada",
                            False,
                        )
                    )
                )

            else:
                certificados.append(False)

        else:

            # SOC final flexible.
            # Se penaliza no alcanzar la bateria final
            # de referencia, pero no se exige igualdad.

            try:
                calculado = optimizar_recargas(
                    datos_operativos=opera,
                    precios_horarios=precios_dia,
                    energia_final_objetivo=finales_oficiales,
                    energia_inicial_vehiculos=entrada,
                    tiempo_maximo_segundos=180,
                    objetivo_final_flexible=True,
                    penalizacion_deficit_eur_kwh=1.0,
                )

            except (ValueError, RuntimeError) as error:
                raise RuntimeError(
                    "No existe un calendario fisicamente "
                    f"factible para el {dia} con demanda "
                    f"{cambio_demanda_pct:+d}% y las "
                    "baterias iniciales disponibles: "
                    f"{error}"
                ) from error

            if not calculado.get(
                "factibilidad_validada"
            ):
                raise RuntimeError(
                    f"Solucion no validada para {dia}"
                )

            solucion = calculado[
                "recargas"
            ][CAMPOS_RESULTADO].copy()

            certificados.append(
                bool(
                    calculado["optimalidad_certificada"]
                )
            )

        # Validar los registros del dia.

        solucion["hora"] = pd.to_datetime(
            solucion["hora"],
            utc=True,
        )

        solucion["vehicle_id"] = (
            solucion["vehicle_id"].astype(str)
        )

        if (
            len(solucion)
            != len(vehiculos) * len(horas)
            or solucion.duplicated(
                ["vehicle_id", "hora"]
            ).any()
            or set(solucion["hora"]) != set(horas)
            or set(solucion["vehicle_id"])
            != set(vehiculos)
        ):
            raise RuntimeError(
                f"Solucion incompleta para {dia}"
            )

        # Obtener la bateria real simulada al cierre.

        cierres = (
            solucion.sort_values("hora")
            .groupby("vehicle_id")
            .tail(1)
        )

        estado_propagado = dict(
            zip(
                cierres["vehicle_id"],
                cierres[
                    "energia_bateria_kwh"
                ].astype(float),
            )
        )

        minimo = (
            CAPACIDAD_BATERIA_KWH * SOC_MINIMO
        )

        maximo = (
            CAPACIDAD_BATERIA_KWH * SOC_OBJETIVO
        )

        if not all(
            np.isfinite(valor)
            and minimo - 0.002
            <= valor
            <= maximo + 0.002
            for valor in estado_propagado.values()
        ):
            raise RuntimeError(
                f"SOC final fuera de limites: {dia}"
            )

        if indice_dia == 0:
            cierre_primer_dia = dict(
                estado_propagado
            )

        cierre_oficial_anterior = finales_oficiales

        fragmentos.append(solucion)
        operaciones.append(opera)
        precios.append(precios_dia)

    # Comprobar continuidad fisica de la simulacion.

    for v in vehiculos:
        if abs(
            cierre_primer_dia[v]
            - entrada_segundo_dia[v]
        ) > 0.002:
            raise RuntimeError(
                "Ruptura de continuidad simulada "
                f"en {v}"
            )

    # Combinar los dos dias.

    juntos = (
        pd.concat(
            fragmentos,
            ignore_index=True,
        )
        .sort_values(
            ["hora", "vehicle_id"]
        )
        .reset_index(drop=True)
    )

    operaciones_48h = pd.concat(
        operaciones,
        ignore_index=True,
    )

    precios_48h = (
        pd.concat(
            precios,
            ignore_index=True,
        )
        .sort_values("hora")
        .reset_index(drop=True)
    )

    return {
        "recargas": juntos,
        "estado": (
            "Optimal"
            if all(certificados)
            else "Factible"
        ),
        "optimalidad_certificada": all(
            certificados
        ),
        "factibilidad_validada": True,
        "coste_estimado_eur": round(
            float(
                juntos["coste_estimado_eur"].sum()
            ),
            2,
        ),
        "energia_total_kwh": round(
            float(
                juntos["recarga_red_kwh"].sum()
            ),
            3,
        ),
        "preparacion_anticipada": None,
    }, operaciones_48h, precios_48h
