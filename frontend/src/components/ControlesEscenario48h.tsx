
"use client";

import { useEffect, useState } from "react";

const API =
  process.env.NEXT_PUBLIC_FLOTIQ_API_URL ||
  "http://127.0.0.1:8000";

type Modelo = {
  id: string;
  nombre: string;
  disponible: boolean;
};

type DiaDemanda = "ambos" | "primero" | "segundo";

export type PlanEscenario = {
  resumen: {
    fecha_consulta: string;
    inicio: string;
    fin_exclusivo: string;
    vehiculos: number;
    horas: number;
    coste_estimado_eur: number;
    energia_red_kwh: number;
    estado_solver: string;
    factibilidad_validada: boolean;
    optimalidad_certificada: boolean;
    continuidad: {
      fecha: string;
      soc_medio_pct: number;
      soc_minimo_pct: number;
    } | null;
  };

  precios: {
    registros: {
      fecha_local: string;
      precio_predicho_eur_mwh: number;
    }[];
  };

  flota: {
    registros: {
      fecha_local: string;
      energia_red_kwh: number;
      coste_estimado_eur: number;
      cargadores_ocupados: number;
      soc_medio_pct: number;
      soc_minimo_pct: number;
    }[];
  };

  calendario: {
    dias: string[];
    vehiculos: string[];
    cargadores: string[];
    registros: {
      vehicle_id: string;
      fecha_local: string;
      estado: "cargando" | "trabajando" | "disponible";
      cargador_id: string | null;
      energia_red_kwh: number;
      energia_consumida_kwh: number;
      soc_pct: number;
    }[];
    advertencia: string;
  };
};

type RespuestaEscenario = PlanEscenario & {
  modelo: string;
  nombre_modelo: string;
  cambio_demanda_pct: number;
  dia_demanda: DiaDemanda;
};

type Props = {
  fechaConsulta: string;
  planActivo: string;
  deshabilitado?: boolean;
  onAplicar: (
    plan: PlanEscenario,
    etiqueta: string
  ) => void;
  onRestablecer: () => void;
  onEstadoCalculo: (calculando: boolean) => void;
};

export default function ControlesEscenario48h({
  fechaConsulta,
  planActivo,
  deshabilitado = false,
  onAplicar,
  onRestablecer,
  onEstadoCalculo,
}: Props) {
  const [modelos, setModelos] = useState<Modelo[]>([]);
  const [modelo, setModelo] = useState("hgb");
  const [demanda, setDemanda] = useState(0);
  const [diaDemanda, setDiaDemanda] =
    useState<DiaDemanda>("ambos");

  const [calculando, setCalculando] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const controlador = new AbortController();

    fetch(`${API}/api/escenarios/modelos`, {
      signal: controlador.signal,
    })
      .then(async (respuesta) => {
        if (!respuesta.ok) {
          throw new Error(
            "No se pudieron consultar los modelos"
          );
        }

        return respuesta.json();
      })
      .then((datos: { modelos: Modelo[] }) => {
        if (!controlador.signal.aborted) {
          setModelos(datos.modelos);
        }
      })
      .catch((fallo: unknown) => {
        if (!controlador.signal.aborted) {
          setError(
            fallo instanceof Error
              ? fallo.message
              : "Error al cargar los modelos"
          );
        }
      });

    return () => controlador.abort();
  }, []);

  useEffect(() => {
    setModelo("hgb");
    setDemanda(0);
    setDiaDemanda("ambos");
    setError("");
  }, [fechaConsulta]);

  async function ejecutarSimulacion() {
    if (!fechaConsulta || calculando) return;

    setCalculando(true);
    onEstadoCalculo(true);
    setError("");

    try {
      const respuesta = await fetch(
        `${API}/api/escenarios/simular`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            fecha_consulta: fechaConsulta,
            modelo,
            cambio_demanda_pct: demanda,
            dia_demanda: diaDemanda,
          }),
        }
      );

      const resultado = await respuesta.json();

      if (!respuesta.ok) {
        throw new Error(
          typeof resultado.detail === "string"
            ? resultado.detail
            : "No se pudo calcular el escenario"
        );
      }

      const nuevoPlan =
        resultado as RespuestaEscenario;

      if (
        !nuevoPlan.resumen?.factibilidad_validada ||
        !nuevoPlan.calendario?.registros ||
        nuevoPlan.calendario.registros.length !==
          nuevoPlan.resumen.vehiculos *
            nuevoPlan.resumen.horas
      ) {
        throw new Error(
          "El nuevo escenario no tiene un calendario válido"
        );
      }

      const variacion =
        demanda > 0 ? `+${demanda}%` : `${demanda}%`;

      const descripcion =
        `${nuevoPlan.nombre_modelo} · Demanda ${variacion}` +
        (demanda !== 0
          ? ` · Día: ${
              diaDemanda === "ambos"
                ? "ambos"
                : diaDemanda === "primero"
                  ? "primero"
                  : "segundo"
            }`
          : "");

      onAplicar(nuevoPlan, descripcion);
    } catch (fallo: unknown) {
      setError(
        fallo instanceof Error
          ? fallo.message
          : "Error al ejecutar la simulación"
      );
    } finally {
      setCalculando(false);
      onEstadoCalculo(false);
    }
  }

  function restaurar() {
    setModelo("hgb");
    setDemanda(0);
    setDiaDemanda("ambos");
    setError("");
    onRestablecer();
  }

  const bloqueado =
    calculando || deshabilitado || !fechaConsulta;

  return (
    <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900">
            Configurar planificación
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            Elige el modelo y ajusta la demanda
            para calcular un escenario alternativo.
          </p>
        </div>

        <span className="rounded-full bg-violet-50 px-3 py-2 text-xs font-semibold text-violet-800">
          Mostrando: {planActivo}
        </span>
      </div>

      <div className="mt-5 grid gap-5 md:grid-cols-3">
        <label className="block text-sm font-semibold text-slate-700">
          Modelo de predicción

          <select
            value={modelo}
            disabled={bloqueado}
            onChange={(e) => setModelo(e.target.value)}
            className="mt-2 block w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-normal disabled:opacity-50"
          >
            {modelos.length === 0 && (
              <option value="hgb">
                Cargando modelos...
              </option>
            )}

            {modelos.map((m) => (
              <option
                key={m.id}
                value={m.id}
                disabled={!m.disponible}
              >
                {m.nombre}
                {!m.disponible
                  ? " · No disponible"
                  : ""}
              </option>
            ))}
          </select>

          <span className="mt-2 block text-xs font-normal text-slate-500">
            Baseline, HGB, Ridge, Random Forest y XGBoost.
          </span>
        </label>

        <div>
          <label
            htmlFor="flotiq-demanda"
            className="flex justify-between text-sm font-semibold text-slate-700"
          >
            <span>Cambio de demanda</span>

            <span className="text-violet-700">
              {demanda > 0 ? "+" : ""}
              {demanda}%
            </span>
          </label>

          <input
            id="flotiq-demanda"
            type="range"
            min={-30}
            max={50}
            step={5}
            disabled={bloqueado}
            value={demanda}
            onChange={(e) =>
              setDemanda(Number(e.target.value))
            }
            className="mt-6 w-full accent-violet-600 disabled:opacity-50"
          />

          <div className="mt-2 flex justify-between text-xs text-slate-500">
            <span>−30%</span>
            <span>Normal</span>
            <span>+50%</span>
          </div>
        </div>

        <label className="block text-sm font-semibold text-slate-700">
          Día afectado por la demanda

          <select
            value={diaDemanda}
            disabled={bloqueado || demanda === 0}
            onChange={(e) =>
              setDiaDemanda(e.target.value as DiaDemanda)
            }
            className="mt-2 block w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-normal disabled:opacity-50"
          >
            <option value="ambos">
              Ambos días
            </option>

            <option value="primero">
              Primer día
            </option>

            <option value="segundo">
              Segundo día
            </option>
          </select>

          <span className="mt-2 block text-xs font-normal text-slate-500">
            Permite simular un evento o festivo
            en una jornada concreta.
          </span>
        </label>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={ejecutarSimulacion}
          disabled={
            bloqueado ||
            modelos.length === 0 ||
            !modelos.some(
              (m) => m.id === modelo && m.disponible
            )
          }
          className="rounded-xl bg-violet-600 px-5 py-3 text-sm font-bold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {calculando
            ? "Calculando escenario..."
            : "Recalcular planificación"}
        </button>

        <button
          type="button"
          onClick={restaurar}
          disabled={bloqueado}
          className="rounded-xl border border-slate-200 px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          Volver al plan original
        </button>
      </div>

      {calculando && (
        <p className="mt-3 text-sm text-slate-500">
          El optimizador está calculando una nueva
          planificación. El plan anterior se conserva
          hasta que termine correctamente.
        </p>
      )}

      {error && (
        <p
          role="alert"
          className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          {error}
        </p>
      )}

      <p className="mt-4 text-xs leading-5 text-slate-500">
        El ajuste de demanda modifica el consumo
        energético simulado. No cambia automáticamente
        el número de viajes ni los turnos.
        Los nuevos planes no sobrescriben los originales.
      </p>
    </section>
  );
}
