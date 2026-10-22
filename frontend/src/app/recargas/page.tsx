
"use client";

// FLOTIQ | CALENDARIO SEMANAL DE RECARGAS

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import Link from "next/link";

type Registro = {
  hora: string;
  recarga_red_kwh: number;
  energia_bateria_kwh: number;
  soc_pct: number;
  conectado: number;
  coste_real_eur: number;
   cargador_id: string | null;
};

type Respuesta = {
  estrategia: string;
  vehiculo: string;
  vehiculos_disponibles: string[];
  horas: number;
  energia_total_kwh: number;
  coste_total_eur: number;
  registros: Registro[];
};

const euros = new Intl.NumberFormat("es-ES", {
  style: "currency",
  currency: "EUR",
});

const numero = new Intl.NumberFormat("es-ES", {
  maximumFractionDigits: 2,
});

const HORAS = Array.from({ length: 24 }, (_, i) => i);

function nombreDia(fecha: string) {
  return new Date(`${fecha}T12:00:00`).toLocaleDateString(
    "es-ES",
    { weekday: "short", day: "numeric", month: "short" }
  );
}

function RecargasContenido() {
  const parametros = useSearchParams();

  const vehiculoInicial = parametros.get("vehiculo") ?? "V001";

  const estrategiaInicial =
    parametros.get("estrategia") === "ml" ? "ml" : "baseline";

  const [vehiculo, setVehiculo] = useState(vehiculoInicial);

  const [estrategia, setEstrategia] = useState<
    "baseline" | "ml"
  >(estrategiaInicial);

  const [datos, setDatos] = useState<Respuesta | null>(null);
  const [seleccion, setSeleccion] = useState<Registro | null>(
    null
  );
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controlador = new AbortController();

    async function consultar() {
      setCargando(true);
      setError("");
      setSeleccion(null);

      try {
        const parametros = new URLSearchParams({
          estrategia,
          vehiculo,
        });

        const respuesta = await fetch(
          `http://127.0.0.1:8000/api/recargas?${parametros}`,
          { signal: controlador.signal }
        );

        if (!respuesta.ok) {
          throw new Error(
            "No se pudieron recuperar las recargas"
          );
        }

        const resultado: Respuesta = await respuesta.json();

        if (!Array.isArray(resultado.registros)) {
          throw new Error("Formato de respuesta incorrecto");
        }

        setDatos(resultado);
      } catch (err) {
        if (controlador.signal.aborted) return;

        setError(
          err instanceof Error
            ? err.message
            : "Error de conexión"
        );
      } finally {
        if (!controlador.signal.aborted) {
          setCargando(false);
        }
      }
    }

    consultar();

    return () => controlador.abort();
  }, [vehiculo, estrategia]);

  const dias = datos
    ? Array.from(
        new Set(datos.registros.map((r) => r.hora.slice(0, 10)))
      )
    : [];

  const porHora = new Map(
    datos?.registros.map((r) => [r.hora.slice(0, 13), r]) ?? []
  );

  const registrosCargando =
    datos?.registros.filter(
      (r) => r.recarga_red_kwh > 0.001
    ) ?? [];

  const socFinal =
    datos && datos.registros.length
      ? datos.registros[datos.registros.length - 1].soc_pct
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

          <Link
            href="/resultados"
            className="text-sm font-medium text-gray-500 hover:text-[#8047F8]"
          >
            ← Ver resultados
          </Link>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-6 py-12">
        <span className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8047F8]">
          Flota eléctrica · Simulación histórica
        </span>

        <h1 className="mt-4 text-4xl font-semibold tracking-tight">
          Calendario de recargas
        </h1>

        <p className="mt-4 max-w-2xl text-gray-500">
          Consulta la planificación horaria de cada vehículo
          durante la semana del 21 al 27 de septiembre de 2026.
        </p>

        <section className="mt-10 flex flex-wrap gap-5 rounded-2xl border border-gray-200 bg-white p-6">
          <div className="min-w-[180px] flex-1">
            <label
              htmlFor="vehiculo"
              className="block text-sm font-medium text-gray-600"
            >
              Vehículo
            </label>

            <select
              id="vehiculo"
              value={vehiculo}
              onChange={(e) => setVehiculo(e.target.value)}
              className="mt-2 w-full rounded-xl border border-gray-200 bg-white px-4 py-3 outline-none focus:border-[#8047F8]"
            >
              {Array.from({ length: 50 }, (_, i) => {
                const id = `V${String(i + 1).padStart(3, "0")}`;
                return (
                  <option key={id} value={id}>
                    Tesla {id}
                  </option>
                );
              })}
            </select>
          </div>

          <div className="min-w-[220px] flex-1">
            <label
              htmlFor="estrategia"
              className="block text-sm font-medium text-gray-600"
            >
              Estrategia de optimización
            </label>

            <select
              id="estrategia"
              value={estrategia}
              onChange={(e) =>
                setEstrategia(
                  e.target.value as "baseline" | "ml"
                )
              }
              className="mt-2 w-full rounded-xl border border-gray-200 bg-white px-4 py-3 outline-none focus:border-[#8047F8]"
            >
              <option value="baseline">
                Baseline semanal
              </option>
              <option value="ml">
                Machine Learning
              </option>
            </select>
          </div>
        </section>

        {cargando && (
          <p className="mt-10 text-sm text-gray-500">
            Cargando planificación del vehículo...
          </p>
        )}

        {error && (
          <p className="mt-10 rounded-xl border border-red-200 bg-white p-5 text-sm text-red-600">
            {error}. Comprueba que FastAPI sigue funcionando.
          </p>
        )}

        {!cargando && datos && !error && (
          <>
            <section className="mt-6 grid gap-4 sm:grid-cols-3">
              <div className="rounded-2xl border border-gray-200 bg-white p-6">
                <p className="text-sm text-gray-500">
                  Energía recargada
                </p>
                <p className="mt-3 text-3xl font-semibold">
                  {numero.format(datos.energia_total_kwh)}
                  <span className="ml-2 text-base font-normal text-gray-400">
                    kWh
                  </span>
                </p>
              </div>

              <div className="rounded-2xl border border-gray-200 bg-white p-6">
                <p className="text-sm text-gray-500">
                  Coste eléctrico
                </p>
                <p className="mt-3 text-3xl font-semibold">
                  {euros.format(datos.coste_total_eur)}
                </p>
              </div>

              <div className="rounded-2xl border border-gray-200 bg-white p-6">
                <p className="text-sm text-gray-500">
                  Estado final de batería
                </p>
                <p className="mt-3 text-3xl font-semibold">
                  {socFinal === null
                    ? "—"
                    : `${numero.format(socFinal)}%`}
                </p>
              </div>
            </section>

            <section className="mt-6 rounded-3xl border border-gray-200 bg-white p-5 shadow-sm sm:p-8">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-xl font-semibold">
                    Semana de carga · {vehiculo}
                  </h2>
                  <p className="mt-2 text-sm text-gray-500">
                    Cada casilla representa una hora.
                    Pulsa una para ver sus datos.
                  </p>
                </div>

                <span className="rounded-full bg-[#F3EDFF] px-3 py-2 text-xs font-medium text-[#7541DC]">
                  {registrosCargando.length} horas con recarga
                </span>
              </div>

              <div className="mt-9 overflow-x-auto pb-3">
                <div className="min-w-[700px]">
                  <div className="mb-3 grid grid-cols-[100px_repeat(24,minmax(0,1fr))] gap-1">
                    <div />
                    {HORAS.map((h) => (
                      <div
                        key={h}
                        className="text-center text-[10px] text-gray-400"
                      >
                        {String(h).padStart(2, "0")}
                      </div>
                    ))}
                  </div>

                  <div className="space-y-2">
                    {dias.map((dia) => (
                      <div
                        key={dia}
                        className="grid grid-cols-[100px_repeat(24,minmax(0,1fr))] gap-1"
                      >
                        <span className="self-center text-xs capitalize text-gray-500">
                          {nombreDia(dia)}
                        </span>

                        {HORAS.map((h) => {
                          const clave = `${dia}T${String(h).padStart(2, "0")}`;

                          const registro = porHora.get(clave);
                          const cargando =
                            (registro?.recarga_red_kwh ?? 0) > 0.001;

                          const activo =
                            seleccion?.hora === registro?.hora &&
                            !!registro;

                          return (
                            <button
                              key={clave}
                              type="button"
                              disabled={!registro}
                              onClick={() =>
                                setSeleccion(registro ?? null)
                              }
                              title={
                                registro
                                  ? `${registro.hora}: ${numero.format(
                                      registro.recarga_red_kwh
                                    )} kWh`
                                  : "Sin datos"
                              }
                              aria-label={
                                registro
                                  ? `${nombreDia(dia)}, ${h}:00, ${
                                      cargando
                                        ? "recargando"
                                        : "sin recarga"
                                    }`
                                  : `Sin datos: ${dia} ${h}:00`
                              }
                              className={`h-9 rounded-[5px] transition hover:scale-110 focus:outline-none focus:ring-2 focus:ring-[#8047F8] ${
                                activo
                                  ? "ring-2 ring-[#111827]"
                                  : ""
                              } ${
                                !registro
                                  ? "bg-gray-100"
                                  : cargando
                                  ? "bg-[#8047F8] hover:bg-[#6735D4]"
                                  : "bg-[#ECECF2] hover:bg-[#DCD9E8]"
                              }`}
                            />
                          );
                        })}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="mt-6 flex flex-wrap items-center gap-5 text-xs text-gray-500">
                <span className="flex items-center gap-2">
                  <span className="h-3 w-3 rounded-sm bg-[#8047F8]" />
                  Recargando
                </span>
                <span className="flex items-center gap-2">
                  <span className="h-3 w-3 rounded-sm bg-[#ECECF2]" />
                  Sin recarga
                </span>
              </div>

              {seleccion && (
                <div className="mt-7 rounded-2xl bg-[#F7F5FC] p-6">
                  <h3 className="font-semibold">
                    Detalle · {seleccion.hora.replace("T", " ")}
                  </h3>

                  <div className="mt-5 grid gap-5 sm:grid-cols-4">
                    {[
                        [
                            "Cargador asignado",
                            seleccion.cargador_id ?? "Sin recarga",
                        ],
                        [
                            "Recarga",
                            `${numero.format(seleccion.recarga_red_kwh)} kWh`,
                        ],
                        [
                            "Batería",
                            `${numero.format(seleccion.soc_pct)}%`,
                        ],
                        [
                            "Energía almacenada",
                            `${numero.format(seleccion.energia_bateria_kwh)} kWh`,
                        ],
                        [
                            "Coste",
                            euros.format(seleccion.coste_real_eur),
                        ],
                        ].map(([titulo, valor]) => (
                      <div key={titulo}>
                        <p className="text-xs text-gray-500">
                          {titulo}
                        </p>
                        <p className="mt-2 text-lg font-semibold">
                          {valor}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>

            <p className="mt-6 text-xs leading-6 text-gray-500">
              Datos de una simulación histórica de 50 vehículos.
              El calendario muestra las decisiones calculadas
              en la Fase 3, no recargas realizadas por una flota
              comercial real. Las horas se presentan como están
              guardadas en el archivo original.
            </p>
          </>
        )}
      </div>
    </main>
  );
}
export default function RecargasPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#FAFAFC] p-10 text-gray-500">
          Cargando calendario de recargas...
        </div>
      }
    >
      <RecargasContenido />
    </Suspense>
  );
}