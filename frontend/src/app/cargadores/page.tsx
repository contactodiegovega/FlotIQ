
"use client";

// FLOTIQ | CENTRO DE CONTROL DE CARGADORES

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

type Hora = {
  hora: string;
  potencia_kw: number;
  energia_kwh: number;
  cargadores_ocupados: number;
  ocupacion_pct: number;
  uso_potencia_pct: number;
};

type RespuestaAPI = {
  tipo_datos: string;
  estrategia: string;
  total_cargadores: number;
  potencia_maxima_kw: number;
  max_cargadores_simultaneos: number;
  max_potencia_kw: number;
  horas: Hora[];
};

const formato = new Intl.NumberFormat("es-ES", {
  maximumFractionDigits: 2,
});

function nombreDia(fecha: string) {
  return new Date(`${fecha}T12:00:00`).toLocaleDateString(
    "es-ES",
    {
      weekday: "long",
      day: "numeric",
      month: "short",
    }
  );
}

export default function CargadoresPage() {
  const [estrategia, setEstrategia] = useState<
    "baseline" | "ml"
  >("baseline");

  const [datos, setDatos] = useState<RespuestaAPI | null>(
    null
  );

  const [dia, setDia] = useState("2026-09-21");
  const [seleccion, setSeleccion] = useState<Hora | null>(
    null
  );
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();

    async function cargar() {
      setCargando(true);
      setError("");
      setDatos(null);
      setSeleccion(null);

      try {
        const respuesta = await fetch(
          `/api/cargadores/ocupacion?estrategia=${estrategia}`,
          { signal: controller.signal }
        );

        if (!respuesta.ok) {
          throw new Error("No se pudo consultar FastAPI");
        }

        const resultado: RespuestaAPI =
          await respuesta.json();

        if (!Array.isArray(resultado.horas)) {
          throw new Error("Respuesta de API incorrecta");
        }

        setDatos(resultado);
      } catch (err) {
        if (controller.signal.aborted) return;

        setError(
          err instanceof Error
            ? err.message
            : "Error de conexión"
        );
      } finally {
        if (!controller.signal.aborted) {
          setCargando(false);
        }
      }
    }

    cargar();

    return () => controller.abort();
  }, [estrategia]);

  const dias = useMemo(
    () =>
      Array.from(
        new Set(
          datos?.horas.map((h) => h.hora.slice(0, 10)) ??
            []
        )
      ),
    [datos]
  );

  const horasDia = useMemo(
    () =>
      datos?.horas.filter(
        (h) => h.hora.slice(0, 10) === dia
      ) ?? [],
    [datos, dia]
  );

  const totalEnergia = useMemo(
    () =>
      datos?.horas.reduce(
        (suma, h) => suma + h.energia_kwh,
        0
      ) ?? 0,
    [datos]
  );

  const horasLimite = useMemo(
    () =>
      datos?.horas.filter(
        (h) =>
          h.potencia_kw >=
          datos.potencia_maxima_kw - 0.01
      ).length ?? 0,
    [datos]
  );

  return (
    <main className="min-h-screen bg-[#FAFAFC] text-[#111827]">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <Link
            href="/"
            className="text-2xl font-bold tracking-tight"
          >
            Flot
            <span className="text-[#8047F8]">IQ</span>
          </Link>

          <nav className="flex gap-5 text-sm text-gray-600">
            <Link
              href="/flota"
              className="hover:text-[#8047F8]"
            >
              Flota
            </Link>
            <Link
              href="/resultados"
              className="hover:text-[#8047F8]"
            >
              Resultados
            </Link>
          </nav>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-6 py-12">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8047F8]">
          Infraestructura energética
        </p>

        <h1 className="mt-4 text-4xl font-semibold tracking-tight">
          Centro de carga
        </h1>

        <p className="mt-4 max-w-2xl text-gray-500">
          Consulta cómo se distribuyen las recargas entre
          los 20 cargadores y el uso de la potencia disponible.
        </p>

        <div className="mt-9 flex flex-wrap gap-5">
          <div>
            <label
              htmlFor="estrategia"
              className="block text-sm font-medium text-gray-600"
            >
              Estrategia
            </label>

            <select
              id="estrategia"
              value={estrategia}
              onChange={(e) =>
                setEstrategia(
                  e.target.value as "baseline" | "ml"
                )
              }
              className="mt-2 rounded-xl border border-gray-200 bg-white px-5 py-3 outline-none focus:border-[#8047F8]"
            >
              <option value="baseline">
                Baseline semanal
              </option>
              <option value="ml">
                Machine Learning
              </option>
            </select>
          </div>

          <div>
            <label
              htmlFor="dia"
              className="block text-sm font-medium text-gray-600"
            >
              Día de la simulación
            </label>

            <select
              id="dia"
              value={dia}
              onChange={(e) => {
                setDia(e.target.value);
                setSeleccion(null);
              }}
              className="mt-2 rounded-xl border border-gray-200 bg-white px-5 py-3 outline-none focus:border-[#8047F8]"
            >
              {dias.map((fecha) => (
                <option key={fecha} value={fecha}>
                  {nombreDia(fecha)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {cargando && (
          <p className="mt-10 text-gray-500">
            Cargando datos de infraestructura...
          </p>
        )}

        {error && (
          <div className="mt-10 rounded-2xl border border-red-200 bg-white p-6 text-red-600">
            {error}. Comprueba el puerto 8000.
          </div>
        )}

        {!cargando && datos && !error && (
          <>
            <section className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                {
                  titulo: "Cargadores disponibles",
                  valor: String(datos.total_cargadores),
                  unidad: "unidades",
                },
                {
                  titulo: "Máximo simultáneo",
                  valor: String(
                    datos.max_cargadores_simultaneos
                  ),
                  unidad: "cargadores",
                },
                {
                  titulo: "Potencia máxima utilizada",
                  valor: formato.format(datos.max_potencia_kw),
                  unidad: "kW",
                },
                {
                  titulo: "Energía semanal",
                  valor: formato.format(totalEnergia),
                  unidad: "kWh",
                },
              ].map((item) => (
                <div
                  key={item.titulo}
                  className="rounded-2xl border border-gray-200 bg-white p-6"
                >
                  <p className="text-sm text-gray-500">
                    {item.titulo}
                  </p>

                  <p className="mt-4 text-3xl font-semibold">
                    {item.valor}
                  </p>

                  <p className="mt-1 text-xs text-gray-400">
                    {item.unidad}
                  </p>
                </div>
              ))}
            </section>

            <section className="mt-7 rounded-3xl border border-gray-200 bg-white p-6 sm:p-8">
              <h2 className="text-xl font-semibold">
                Ocupación por hora
              </h2>

              <p className="mt-2 text-sm text-gray-500">
                Número de cargadores ocupados durante el
                día seleccionado. Pulsa una fila para ver
                el detalle.
              </p>

              <div className="mt-8 space-y-3">
                {horasDia.map((h) => {
                  const porcentaje =
                    (h.cargadores_ocupados /
                      datos.total_cargadores) *
                    100;

                  const activa =
                    seleccion?.hora === h.hora;

                  return (
                    <button
                      type="button"
                      key={h.hora}
                      onClick={() => setSeleccion(h)}
                      className={`flex w-full items-center gap-4 rounded-lg p-2 text-left transition hover:bg-[#F7F5FC] ${
                        activa
                          ? "bg-[#F7F5FC] ring-1 ring-[#DCCEFF]"
                          : ""
                      }`}
                    >
                      <span className="w-14 text-xs font-medium tabular-nums text-gray-500">
                        {h.hora.slice(11, 16)}
                      </span>

                      <div className="h-4 flex-1 overflow-hidden rounded-full bg-[#F0F0F4]">
                        <div
                          className="h-full rounded-full bg-[#8047F8] transition-all duration-500"
                          style={{
                            width: `${porcentaje}%`,
                          }}
                        />
                      </div>

                      <span className="w-14 text-right text-xs font-semibold tabular-nums">
                        {h.cargadores_ocupados}/
                        {datos.total_cargadores}
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="mt-7 rounded-3xl border border-gray-200 bg-white p-6 sm:p-8">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <h2 className="text-xl font-semibold">
                  Potencia de la instalación
                </h2>

                <span className="rounded-full bg-[#F2EDFF] px-3 py-2 text-xs font-semibold text-[#7541DC]">
                  Límite: {datos.potencia_maxima_kw} kW
                </span>
              </div>

              <p className="mt-2 text-sm text-gray-500">
                Potencia media horaria utilizada frente al
                máximo contratado para la simulación.
              </p>

              <div className="mt-9 flex h-52 items-end gap-1 border-b border-gray-200 pb-1">
                {horasDia.map((h) => (
                  <button
                    type="button"
                    key={h.hora}
                    onClick={() => setSeleccion(h)}
                    title={`${h.hora.slice(11, 16)} · ${formato.format(h.potencia_kw)} kW`}
                    aria-label={`${h.hora.slice(11, 16)}, ${formato.format(h.potencia_kw)} kW`}
                    className="group flex h-full min-w-0 flex-1 items-end"
                  >
                    <div
                      className={`w-full rounded-t transition hover:opacity-75 ${
                        seleccion?.hora === h.hora
                          ? "bg-[#4F259E]"
                          : "bg-[#A88AFF]"
                      }`}
                      style={{
                        height: `${h.uso_potencia_pct}%`,
                        minHeight:
                          h.potencia_kw > 0
                            ? "3px"
                            : "0px",
                      }}
                    />
                  </button>
                ))}
              </div>

              <div className="mt-3 flex justify-between text-xs text-gray-400">
                <span>00:00</span>
                <span>06:00</span>
                <span>12:00</span>
                <span>18:00</span>
                <span>23:00</span>
              </div>

              <p className="mt-6 text-sm text-gray-500">
                Durante la semana, la instalación alcanzó
                el límite de potencia en{" "}
                <strong className="text-gray-900">
                  {horasLimite} horas
                </strong>.
              </p>
            </section>

            {seleccion && (
              <section className="mt-7 rounded-3xl border border-[#DFD4FA] bg-white p-7">
                <h2 className="text-lg font-semibold">
                  Detalle · {seleccion.hora.replace("T", " ")}
                </h2>

                <div className="mt-6 grid gap-5 sm:grid-cols-3">
                  <div>
                    <p className="text-sm text-gray-500">
                      Cargadores ocupados
                    </p>
                    <p className="mt-2 text-2xl font-semibold">
                      {seleccion.cargadores_ocupados}/20
                    </p>
                  </div>

                  <div>
                    <p className="text-sm text-gray-500">
                      Potencia utilizada
                    </p>
                    <p className="mt-2 text-2xl font-semibold">
                      {formato.format(seleccion.potencia_kw)}
                      <span className="ml-1 text-sm text-gray-400">
                        kW
                      </span>
                    </p>
                  </div>

                  <div>
                    <p className="text-sm text-gray-500">
                      Uso de potencia
                    </p>
                    <p className="mt-2 text-2xl font-semibold">
                      {formato.format(
                        seleccion.uso_potencia_pct
                      )}
                      %
                    </p>
                  </div>
                </div>
              </section>
            )}

            <p className="mt-7 text-xs leading-6 text-gray-500">
              Resultados de la simulación histórica del 21
              al 27 de septiembre de 2026. La potencia
              representa la media de cada intervalo horario,
              no picos eléctricos instantáneos.
            </p>
          </>
        )}
      </div>
    </main>
  );
}
