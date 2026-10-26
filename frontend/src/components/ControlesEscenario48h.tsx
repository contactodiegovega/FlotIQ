
"use client";

import { useEffect, useState } from "react";

const API =
  process.env.NEXT_PUBLIC_FLOTIQ_API_URL ||
  "http://127.0.0.1:8000";

type Modelo = "baseline" | "hgb" | "ridge" | "rf" | "xgb";
type DiaDemanda = "primero" | "segundo" | "ambos";

type Respuesta = {
  cambio_demanda_pct: number;
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

type Props = {
  fechaConsulta: string;
  planActivo: string;
  deshabilitado: boolean;
  onEstadoCalculo: (activo: boolean) => void;
  onRestablecer: () => void;
  onAplicar: (
    plan: Respuesta,
    descripcion: string
  ) => void;
};

const nombres: Record<Modelo, string> = {
  baseline: "Baseline semanal",
  hgb: "HistGradientBoosting",
  ridge: "Ridge Regression",
  rf: "Random Forest",
  xgb: "XGBoost",
};

export default function ControlesEscenario48h({
  fechaConsulta,
  planActivo,
  deshabilitado,
  onEstadoCalculo,
  onRestablecer,
  onAplicar,
}: Props) {
  const [modelo, setModelo] = useState<Modelo>("hgb");

  const [diaDemanda, setDiaDemanda] =
    useState<DiaDemanda>("ambos");

  const [demanda, setDemanda] = useState(0);
  const [maximo, setMaximo] = useState<number | null>(null);
  const [calculandoLimite, setCalculandoLimite] =
    useState(false);

  const [simulando, setSimulando] = useState(false);
  const [mensaje, setMensaje] = useState("");

  const [disponibles, setDisponibles] = useState<Modelo[]>(
    ["hgb", "baseline"]
  );

  // Cargar modelos disponibles.

  useEffect(() => {
    const control = new AbortController();

    fetch(`${API}/api/escenarios/modelos`, {
      signal: control.signal,
    })
      .then((respuesta) => respuesta.json())
      .then(
        (datos: {
          modelos?: {
            id: Modelo;
            disponible: boolean;
          }[];
        }) => {
          if (control.signal.aborted || !datos.modelos) {
            return;
          }

          setDisponibles(
            datos.modelos
              .filter((m) => m.disponible)
              .map((m) => m.id)
          );
        }
      )
      .catch(() => {});

    return () => control.abort();
  }, []);

  // Calcular el limite factible al cambiar
  // de fecha, modelo o dia seleccionado.

  useEffect(() => {
    if (!fechaConsulta) return;

    const control = new AbortController();

    setDemanda(0);
    setMaximo(null);
    setMensaje("");
    setCalculandoLimite(true);

    const params = new URLSearchParams({
      fecha_consulta: fechaConsulta,
      modelo,
      dia_demanda: diaDemanda,
    });

    fetch(
      `${API}/api/escenarios/limite-demanda?${params}`,
      {
        signal: control.signal,
        cache: "no-store",
      }
    )
      .then(async (respuesta) => {
        if (!respuesta.ok) {
          throw new Error("Limite no disponible");
        }

        return (await respuesta.json()) as {
          maximo_pct: number;
        };
      })
      .then((datos) => {
        if (control.signal.aborted) return;

        setMaximo(
          Math.max(0, Math.floor(datos.maximo_pct))
        );
      })
      .catch(() => {
        if (control.signal.aborted) return;

        // Sin un limite comprobado no permitimos
        // lanzar nuevas simulaciones.

        setMaximo(null);
        setMensaje(
          "No está disponible el cálculo de capacidad en este momento."
        );
      })
      .finally(() => {
        if (!control.signal.aborted) {
          setCalculandoLimite(false);
        }
      });

    return () => control.abort();
  }, [fechaConsulta, modelo, diaDemanda]);

  // Generar escenario sin guardar cambios.

  async function aplicar() {
    if (
      !fechaConsulta ||
      maximo === null ||
      simulando ||
      deshabilitado
    ) {
      return;
    }

    setSimulando(true);
    onEstadoCalculo(true);
    setMensaje("");

    const solicitado = Math.max(
      -30,
      Math.min(demanda, maximo)
    );

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
            cambio_demanda_pct: solicitado,
            dia_demanda: diaDemanda,
          }),
        }
      );

      if (!respuesta.ok) {
        throw new Error("Simulacion no disponible");
      }

      const plan = (await respuesta.json()) as Respuesta;

      // El backend informa del porcentaje
      // realmente aplicado.

      const porcentaje = plan.cambio_demanda_pct;
      setDemanda(porcentaje);

      const signo = porcentaje > 0 ? "+" : "";

      const diaTexto =
        diaDemanda === "ambos"
          ? "ambos los días"
          : diaDemanda === "primero"
          ? "primer día"
          : "segundo día";

      onAplicar(
        plan,
        `${nombres[modelo]} · ${diaTexto} · ${signo}${porcentaje} % demanda`
      );
    } catch {
      // Nunca sustituir un plan correcto
      // por un escenario no disponible.

      setMensaje(
        "No se ha podido completar esta simulación. La planificación anterior se conserva."
      );
    } finally {
      setSimulando(false);
      onEstadoCalculo(false);
    }
  }

  const bloqueado =
    deshabilitado ||
    simulando ||
    calculandoLimite ||
    maximo === null;

  return (
    <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900">
            Simulador de demanda
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            Ajusta la actividad dentro de la capacidad
            de la flota.
          </p>
        </div>

        <button
          type="button"
          disabled={simulando}
          onClick={() => {
            setDemanda(0);
            setMensaje("");
            onRestablecer();
          }}
          className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          Restablecer plan
        </button>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <label className="text-sm font-semibold text-slate-700">
          Modelo de precios

          <select
            value={modelo}
            disabled={simulando}
            onChange={(e) =>
              setModelo(e.target.value as Modelo)
            }
            className="mt-2 block w-full rounded-xl border border-slate-200 bg-white px-3 py-3 font-normal"
          >
            {disponibles.map((id) => (
              <option key={id} value={id}>
                {nombres[id]}
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm font-semibold text-slate-700">
          Aplicar el cambio a

          <select
            value={diaDemanda}
            disabled={simulando}
            onChange={(e) =>
              setDiaDemanda(
                e.target.value as DiaDemanda
              )
            }
            className="mt-2 block w-full rounded-xl border border-slate-200 bg-white px-3 py-3 font-normal"
          >
            <option value="ambos">Ambos días</option>
            <option value="primero">Primer día</option>
            <option value="segundo">Segundo día</option>
          </select>
        </label>
      </div>

      <div className="mt-5 rounded-xl bg-violet-50 p-5">
        <div className="flex items-center justify-between gap-3">
          <label
            htmlFor="demanda-flotiq"
            className="text-sm font-semibold text-violet-950"
          >
            Variación de demanda
          </label>

          <span className="text-xl font-bold tabular-nums text-violet-950">
            {demanda > 0 ? "+" : ""}
            {demanda} %
          </span>
        </div>

        <input
          id="demanda-flotiq"
          type="range"
          min={-30}
          max={maximo ?? 0}
          step={1}
          value={demanda}
          onChange={(e) =>
            setDemanda(Number(e.target.value))
          }
          disabled={bloqueado}
          className="mt-4 w-full accent-violet-600 disabled:opacity-50"
        />

        <div className="mt-2 flex justify-between text-xs text-violet-700">
          <span>−30 %</span>

          <span>
            {calculandoLimite
              ? "Calculando capacidad…"
              : maximo === null
              ? "Capacidad no disponible"
              : `Máximo viable: +${maximo} %`}
          </span>
        </div>
      </div>

      <p className="mt-2 text-xs text-slate-500">
        Para comparar una fecha entre dos planes,
        selecciona ese día en cada ventana.
      </p>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={bloqueado}
          onClick={aplicar}
          className="rounded-xl bg-violet-600 px-5 py-3 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {simulando
            ? "Calculando escenario…"
            : "Aplicar simulación"}
        </button>

        <span className="text-xs text-slate-500">
          {planActivo}
        </span>
      </div>

      {mensaje && (
        <p className="mt-3 text-xs text-slate-500">
          {mensaje}
        </p>
      )}
    </section>
  );
}
