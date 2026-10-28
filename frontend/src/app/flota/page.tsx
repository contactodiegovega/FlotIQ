
"use client";

// FLOTIQ | VISTA GENERAL DE RECARGAS DE LA FLOTA

import { useEffect, useState } from "react";
import Link from "next/link";

type Dia = {
  fecha: string;
  energia_kwh: number;
  coste_eur: number;
  horas_recarga: number;
};

type Vehiculo = {
  id: string;
  energia_kwh: number;
  coste_eur: number;
  horas_recarga: number;
  dias: Dia[];
};

type DatosFlota = {
  tipo_datos: string;
  estrategia: string;
  total_vehiculos: number;
  energia_total_kwh: number;
  coste_total_eur: number;
  fechas: string[];
  vehiculos: Vehiculo[];
};

const euros = new Intl.NumberFormat("es-ES", {
  style: "currency",
  currency: "EUR",
});

const numero = new Intl.NumberFormat("es-ES", {
  maximumFractionDigits: 2,
});

function nombreDia(fecha: string) {
  return new Date(`${fecha}T12:00:00`).toLocaleDateString(
    "es-ES",
    {
      weekday: "short",
      day: "numeric",
    }
  );
}

export default function FlotaPage() {
  const [estrategia, setEstrategia] = useState<
    "baseline" | "ml"
  >("baseline");

    const [semana, setSemana] = useState("2026-09-21");

  const [datos, setDatos] = useState<DatosFlota | null>(
    null
  );
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [busqueda, setBusqueda] = useState("");

  useEffect(() => {
    const controller = new AbortController();

    async function cargarFlota() {
      setCargando(true);
      setError("");
      setDatos(null);

      try {
        const respuesta = await fetch(
          "/api/recargas/flota" +
            `?estrategia=${estrategia}`,
          { signal: controller.signal }
        );

        if (!respuesta.ok) {
          throw new Error(
            "No se pudieron cargar las recargas"
          );
        }

        const resultado: DatosFlota =
          await respuesta.json();

        if (!Array.isArray(resultado.vehiculos)) {
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

    cargarFlota();

    return () => controller.abort();
  }, [estrategia]);

  const vehiculosFiltrados =
    datos?.vehiculos.filter((v) =>
      v.id.toLowerCase().includes(
        busqueda.trim().toLowerCase()
      )
    ) ?? [];

  return (
    <main className="min-h-screen bg-[#FAFAFC] text-[#111827]">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Link
            href="/"
            className="text-2xl font-bold tracking-tight"
          >
            Flot
            <span className="text-[#8047F8]">IQ</span>
          </Link>

          <nav className="flex items-center gap-5 text-sm text-gray-600">
            <Link
              href="/resultados"
              className="hover:text-[#8047F8]"
            >
              Resultados
            </Link>
            <Link
              href="/planificacion"
              className="hover:text-[#8047F8]"
            >
              Planificación
            </Link>
          </nav>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-6 py-12">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8047F8]">
              Simulación histórica · 21–27 septiembre 2026
            </p>

            <h1 className="mt-4 text-4xl font-semibold tracking-tight">
              Planificación de la flota
            </h1>

            <p className="mt-3 text-gray-500">
              Visualiza las recargas de los 50 Tesla
              y consulta el detalle de cada vehículo.
            </p>
          </div>

            <div>
            <label
                htmlFor="semana"
                className="block text-xs font-medium text-gray-500"
            >
                Semana de planificación
            </label>

            <input
                id="semana"
                type="date"
                value={semana}
                onChange={(e) => setSemana(e.target.value)}
                className="mt-2 min-w-52 rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm outline-none focus:border-[#8047F8]"
            />
            </div>

          <div>
            <label
              htmlFor="estrategia"
              className="block text-xs font-medium text-gray-500"
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
              className="mt-2 min-w-52 rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm outline-none focus:border-[#8047F8]"
            >
              <option value="baseline">
                Baseline optimizado
              </option>
              <option value="ml">
                Machine Learning
              </option>
            </select>
          </div>
        </div>

        {cargando && (
          <p className="mt-12 text-gray-500">
            Cargando calendario de la flota...
          </p>
        )}

        {error && (
          <div className="mt-10 rounded-2xl border border-red-200 bg-white p-6 text-sm text-red-600">
            {error}. Comprueba que FastAPI está activo.
          </div>
        )}

            {semana !== "2026-09-21" && (
        <div className="mt-10 rounded-3xl border border-gray-200 bg-white p-8">
            <h2 className="text-xl font-semibold">
            Semana pendiente de planificación
            </h2>

            <p className="mt-3 max-w-2xl leading-7 text-gray-500">
            Todavía no hemos generado una planificación energética
            para esta semana. El siguiente paso será conectar el
            selector con el motor de predicción y optimización de FlotIQ.
            </p>
        </div>
        )}

        {!cargando && datos && !error && semana === "2026-09-21" && (
          <>
            <div className="mt-10 grid gap-4 sm:grid-cols-3">
              <div className="rounded-2xl border border-gray-200 bg-white p-6">
                <p className="text-sm text-gray-500">
                  Vehículos
                </p>
                <p className="mt-3 text-3xl font-semibold">
                  {datos.total_vehiculos}
                </p>
              </div>

              <div className="rounded-2xl border border-gray-200 bg-white p-6">
                <p className="text-sm text-gray-500">
                  Energía semanal
                </p>
                <p className="mt-3 text-3xl font-semibold">
                  {numero.format(
                    datos.energia_total_kwh
                  )}
                  <span className="ml-2 text-base font-normal text-gray-400">
                    kWh
                  </span>
                </p>
              </div>

              <div className="rounded-2xl border border-gray-200 bg-white p-6">
                <p className="text-sm text-gray-500">
                  Coste total
                </p>
                <p className="mt-3 text-3xl font-semibold">
                  {euros.format(datos.coste_total_eur)}
                </p>
              </div>
            </div>

            <section className="mt-7 overflow-hidden rounded-3xl border border-gray-200 bg-white">
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-gray-100 px-6 py-6">
                <div>
                  <h2 className="text-xl font-semibold">
                    Calendario semanal
                  </h2>
                  <p className="mt-1 text-sm text-gray-500">
                    Intensidad violeta = más horas
                    de recarga durante ese día.
                  </p>
                </div>

                <input
                  type="search"
                  placeholder="Buscar vehículo..."
                  aria-label="Buscar vehículo"
                  value={busqueda}
                  onChange={(e) =>
                    setBusqueda(e.target.value)
                  }
                  className="rounded-xl border border-gray-200 px-4 py-3 text-sm outline-none focus:border-[#8047F8]"
                />
              </div>

              <div className="overflow-x-auto">
                <div className="min-w-[900px]">
                  <div className="grid grid-cols-[90px_repeat(7,minmax(0,1fr))_100px_95px] gap-2 border-b border-gray-100 bg-[#FCFCFE] px-6 py-4 text-xs font-semibold text-gray-500">
                    <span>Vehículo</span>

                    {datos.fechas.map((fecha) => (
                      <span
                        key={fecha}
                        className="text-center capitalize"
                      >
                        {nombreDia(fecha)}
                      </span>
                    ))}

                    <span className="text-right">Energía</span>
                    <span className="text-right">Coste</span>
                  </div>

                  <div className="max-h-[650px] overflow-y-auto">
                    {vehiculosFiltrados.map((vehiculo) => {
                      const diasPorFecha = new Map(
                        vehiculo.dias.map((dia) => [
                          dia.fecha,
                          dia,
                        ])
                      );

                      return (
                        <Link
                          key={vehiculo.id}
                          href={`/recargas?vehiculo=${vehiculo.id}&estrategia=${estrategia}`}
                          className="grid grid-cols-[90px_repeat(7,minmax(0,1fr))_100px_95px] items-center gap-2 border-b border-gray-100 px-6 py-2.5 transition hover:bg-[#FAF8FF]"
                        >
                          <span className="text-sm font-semibold text-[#7541DC]">
                            {vehiculo.id} →
                          </span>

                          {datos.fechas.map((fecha) => {
                            const dia =
                              diasPorFecha.get(fecha);

                            const horas =
                              dia?.horas_recarga ?? 0;

                            const intensidad =
                              horas === 0
                                ? 0
                                : Math.min(
                                    0.2 + horas / 24,
                                    1
                                  );

                            return (
                              <div
                                key={fecha}
                                title={`${fecha}: ${horas} horas de recarga · ${numero.format(dia?.energia_kwh ?? 0)} kWh`}
                                className="h-8 rounded-md"
                                style={{
                                  backgroundColor:
                                    horas > 0
                                      ? `rgba(128,71,248,${intensidad})`
                                      : "#F0F0F4",
                                }}
                              />
                            );
                          })}

                          <span className="text-right text-xs font-medium">
                            {numero.format(
                              vehiculo.energia_kwh
                            )} kWh
                          </span>

                          <span className="text-right text-xs font-medium">
                            {euros.format(
                              vehiculo.coste_eur
                            )}
                          </span>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              </div>

              {vehiculosFiltrados.length === 0 && (
                <p className="px-6 py-8 text-sm text-gray-500">
                  No se encontraron vehículos.
                </p>
              )}

              <div className="border-t border-gray-100 px-6 py-4 text-xs text-gray-500">
                Selecciona una fila para ver las
                168 horas del vehículo.
              </div>
            </section>

            <p className="mt-6 text-xs leading-6 text-gray-500">
              Resultados simulados de la Fase 3.
              Esta pantalla consulta recargas históricas
              optimizadas; todavía no genera
              planificaciones para semanas futuras.
            </p>
          </>
        )}
      </div>
    </main>
  );
}
