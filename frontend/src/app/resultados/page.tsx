
"use client";

// FLOTIQ | DASHBOARD DE RESULTADOS HISTORICOS

import { useEffect, useState } from "react";
import Link from "next/link";

type Estrategia = {
  estrategia: string;
  coste_eur: number;
  ahorro_pct: number;
};

type RespuestaAPI = {
  tipo_datos: string;
  archivo: string;
  columnas: string[];
  registros: Estrategia[];
};

const formatoEuros = new Intl.NumberFormat("es-ES", {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const formatoPorcentaje = new Intl.NumberFormat("es-ES", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export default function ResultadosPage() {
  const [estrategias, setEstrategias] = useState<Estrategia[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function cargarResultados() {
      try {
        const respuesta = await fetch(
          "http://127.0.0.1:8000/api/resultados/semana"
        );

        if (!respuesta.ok) {
          throw new Error("No se pudieron consultar los resultados");
        }

        const datos: RespuestaAPI = await respuesta.json();

        if (!Array.isArray(datos.registros)) {
          throw new Error("La respuesta de la API no es válida");
        }

        setEstrategias(datos.registros);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Error desconocido al cargar resultados"
        );
      } finally {
        setCargando(false);
      }
    }

    cargarResultados();
  }, []);

  const inmediata = estrategias.find(
    (e) => e.estrategia === "Recarga inmediata"
  );

  const baseline = estrategias.find(
    (e) => e.estrategia === "Baseline semanal optimizado"
  );

  const ml = estrategias.find(
    (e) => e.estrategia === "HistGradientBoosting optimizado"
  );

  const menorCoste =
    estrategias.length > 0
      ? Math.min(...estrategias.map((e) => e.coste_eur))
      : 0;

  const maxCoste =
    estrategias.length > 0
      ? Math.max(...estrategias.map((e) => e.coste_eur))
      : 1;

  const ahorroEuros =
    inmediata && baseline
      ? inmediata.coste_eur - baseline.coste_eur
      : null;

  return (
    <main className="min-h-screen bg-[#FAFAFC] text-[#111827]">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <Link
            href="/"
            className="text-2xl font-bold tracking-tight"
          >
            Flot<span className="text-[#8047F8]">IQ</span>
          </Link>

          <nav className="flex items-center gap-6 text-sm text-gray-600">
            <Link
              href="/planificacion"
              className="transition hover:text-[#8047F8]"
            >
              Planificación
            </Link>
            <Link href="/" className="transition hover:text-[#8047F8]">
              Inicio
            </Link>
          </nav>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-6 py-14">
        <span className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8047F8]">
          Análisis energético
        </span>

        <h1 className="mt-4 text-4xl font-semibold tracking-tight md:text-5xl">
          Resultados de optimización
        </h1>

        <p className="mt-4 max-w-3xl leading-7 text-gray-500">
          Comparación de estrategias de recarga para una flota
          simulada de 50 vehículos eléctricos durante la semana
          del 21 al 27 de septiembre de 2026.
        </p>

        {cargando && (
          <div className="mt-12 rounded-2xl bg-white p-8 text-gray-500">
            Cargando resultados desde FlotIQ API...
          </div>
        )}

        {error && (
          <div className="mt-12 rounded-2xl border border-red-200 bg-white p-8 text-red-600">
            {error}. Comprueba que FastAPI funciona en el
            puerto 8000.
          </div>
        )}

        {!cargando && !error && estrategias.length > 0 && (
          <>
            <div className="mt-12 grid gap-5 md:grid-cols-3">
              {[
                {
                  titulo: "Recarga inmediata",
                  datos: inmediata,
                  descripcion: "Estrategia sin optimización",
                },
                {
                  titulo: "Baseline optimizado",
                  datos: baseline,
                  descripcion: "Optimización con referencia semanal",
                },
                {
                  titulo: "Machine Learning",
                  datos: ml,
                  descripcion: "Optimización con HistGradientBoosting",
                },
              ].map((tarjeta) => (
                <article
                  key={tarjeta.titulo}
                  className="rounded-3xl border border-gray-200 bg-white p-7 shadow-sm"
                >
                  <p className="text-sm font-medium text-gray-500">
                    {tarjeta.titulo}
                  </p>

                  <p className="mt-4 text-3xl font-semibold tracking-tight">
                    {tarjeta.datos
                      ? formatoEuros.format(tarjeta.datos.coste_eur)
                      : "Sin datos"}
                  </p>

                  <p className="mt-3 text-sm font-medium text-[#7541DC]">
                    {tarjeta.datos
                      ? `${formatoPorcentaje.format(
                          tarjeta.datos.ahorro_pct
                        )}% de ahorro`
                      : "—"}
                  </p>

                  <p className="mt-6 text-xs leading-5 text-gray-400">
                    {tarjeta.descripcion}
                  </p>
                </article>
              ))}
            </div>

            <section className="mt-8 rounded-3xl border border-gray-200 bg-white p-8 shadow-sm">
              <h2 className="text-xl font-semibold">
                Comparación de costes
              </h2>

              <p className="mt-2 text-sm text-gray-500">
                Coste total de electricidad por estrategia.
                Cuanto menor, mejor.
              </p>

              <div className="mt-10 space-y-8">
                {estrategias.map((estrategia) => {
                  const mejor =
                    estrategia.coste_eur === menorCoste;

                  const anchura =
                    maxCoste > 0
                      ? (estrategia.coste_eur / maxCoste) * 100
                      : 0;

                  return (
                    <div key={estrategia.estrategia}>
                      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm">
                        <span className="font-medium">
                          {estrategia.estrategia}
                          {mejor && (
                            <span className="ml-2 text-xs font-semibold text-[#7541DC]">
                              Menor coste
                            </span>
                          )}
                        </span>

                        <span className="font-semibold">
                          {formatoEuros.format(
                            estrategia.coste_eur
                          )}
                        </span>
                      </div>

                      <div className="h-4 overflow-hidden rounded-full bg-[#F0F0F4]">
                        <div
                          className={`h-full rounded-full transition-all duration-700 ${
                            mejor
                              ? "bg-[#8047F8]"
                              : "bg-[#BEC2CE]"
                          }`}
                          style={{ width: `${anchura}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="mt-8 grid gap-6 md:grid-cols-2">
              <div className="rounded-3xl border border-gray-200 bg-white p-8">
                <p className="text-sm text-gray-500">
                  Ahorro de la mejor estrategia frente a la
                  recarga inmediata
                </p>

                <p className="mt-4 text-4xl font-semibold text-[#7541DC]">
                  {ahorroEuros !== null
                    ? formatoEuros.format(ahorroEuros)
                    : "—"}
                </p>

                <p className="mt-4 text-sm leading-6 text-gray-500">
                  Ahorro calculado para la semana simulada,
                  manteniendo las condiciones de operación
                  utilizadas en la Fase 3.
                </p>
              </div>

              <div className="rounded-3xl border border-gray-200 bg-white p-8">
                <h2 className="text-lg font-semibold">
                  Sobre estos resultados
                </h2>

                <p className="mt-4 text-sm leading-7 text-gray-500">
                  Los resultados proceden de una simulación
                  histórica de FlotIQ. No son datos de una
                  flota comercial real ni constituyen una
                  garantía de ahorro futuro.
                </p>

                <p className="mt-4 text-sm leading-7 text-gray-500">
                  Las soluciones del optimizador fueron
                  comprobadas frente a las restricciones de
                  la simulación. Esto no implica que el solver
                  certificara siempre la optimalidad matemática.
                </p>
              </div>
            </section>
          </>
        )}

        {!cargando && !error && estrategias.length === 0 && (
          <p className="mt-10 text-gray-500">
            No se encontraron resultados para mostrar.
          </p>
        )}
      </div>
    </main>
  );
}
