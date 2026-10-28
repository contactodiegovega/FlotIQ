
"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

const API =
  "";

type Modelo = {
  id: string;
  nombre: string;
  disponible: boolean;
};

type Hora = {
  fecha_local: string;
  precio_eur_mwh: number;
  energia_red_kwh: number;
  recargando: number;
  soc_medio_pct: number;
};

type Sesion = {
  vehiculo: string;
  inicio_local: string;
  fin_local: string;
  energia_kwh: number;
};

type Resultado = {
  modelo: string;
  nombre_modelo: string;
  cambio_demanda_pct: number;
  factibilidad_validada: boolean;
  optimalidad_certificada: boolean;
  estado_solver: string;
  energia_total_kwh: number;
  coste_estimado_eur: number;
  coste_bajo_baseline_comun_eur: number;
  horas: Hora[];
  sesiones_recarga: Sesion[];
  nota: string;
};

function numero(valor: number, decimales = 2) {
  return valor.toLocaleString("es-ES", {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  });
}

function fechaHora(fecha: string) {
  return new Date(fecha).toLocaleString("es-ES", {
    timeZone: "Europe/Madrid",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
}

function diasPlan(fecha: string, dias: number) {
  const [anio, mes, dia] = fecha.split("-").map(Number);

  return new Date(
    Date.UTC(anio, mes - 1, dia + dias)
  ).toLocaleDateString("es-ES", {
    timeZone: "UTC",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function Grafico({
  titulo,
  descripcion,
  unidad,
  color,
  puntos,
}: {
  titulo: string;
  descripcion: string;
  unidad: string;
  color: string;
  puntos: { fecha: string; valor: number }[];
}) {
  const [indice, setIndice] = useState<number | null>(null);

  if (!puntos.length) return null;

  const minimo = Math.min(
    0,
    ...puntos.map((p) => p.valor)
  );

  const maximo = Math.max(
    1,
    ...puntos.map((p) => p.valor)
  );

  const rango = Math.max(1, maximo - minimo);

  const x = (i: number) =>
    56 + (i * 680) / Math.max(1, puntos.length - 1);

  const y = (v: number) =>
    190 - ((v - minimo) / rango) * 155;

  const trazo = puntos
    .map(
      (p, i) =>
        `${i ? "L" : "M"}${x(i).toFixed(1)},${y(
          p.valor
        ).toFixed(1)}`
    )
    .join(" ");

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="font-bold text-slate-900">
        {titulo}
      </h3>

      <p className="mt-1 text-sm text-slate-500">
        {descripcion}
      </p>

      <svg
        role="img"
        aria-label={titulo}
        viewBox="0 0 790 235"
        className="mt-5 w-full"
      >
        {[0, 0.25, 0.5, 0.75, 1].map((f) => {
          const valor = minimo + f * rango;

          return (
            <g key={f}>
              <line
                x1="56"
                x2="736"
                y1={y(valor)}
                y2={y(valor)}
                stroke="#E2E8F0"
                strokeDasharray="4 4"
              />

              <text
                x="48"
                y={y(valor) + 4}
                fontSize="11"
                fill="#64748B"
                textAnchor="end"
              >
                {numero(valor, 0)}
              </text>
            </g>
          );
        })}

        <path
          d={trazo}
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinecap="round"
        />

        {puntos.map((p, i) => (
          <g key={`${p.fecha}-${i}`}>
            <circle
              cx={x(i)}
              cy={y(p.valor)}
              r={indice === i ? 6 : 4}
              fill={color}
              stroke="white"
              strokeWidth="1"
              onMouseEnter={() => setIndice(i)}
              onMouseLeave={() => setIndice(null)}
            >
              <title>
                {fechaHora(p.fecha)}: {numero(p.valor)}{" "}
                {unidad}
              </title>
            </circle>

            {i % 8 === 0 && (
              <text
                x={x(i)}
                y="220"
                fontSize="11"
                textAnchor="middle"
                fill="#64748B"
              >
                {new Date(p.fecha).toLocaleTimeString(
                  "es-ES",
                  {
                    timeZone: "Europe/Madrid",
                    hour: "2-digit",
                    minute: "2-digit",
                  }
                )}
              </text>
            )}
          </g>
        ))}
      </svg>

      <div className="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
        {indice === null
          ? "Pasa el ratón por la línea para consultar cada hora."
          : `${fechaHora(puntos[indice].fecha)} · ${numero(
              puntos[indice].valor
            )} ${unidad}`}
      </div>
    </section>
  );
}

export default function EscenariosPage() {
  const [fechas, setFechas] = useState<string[]>([]);
  const [fecha, setFecha] = useState("");
  const [modelos, setModelos] = useState<Modelo[]>([]);
  const [modelo, setModelo] = useState("hgb");
  const [demanda, setDemanda] = useState(0);

  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");
  const [resultado, setResultado] =
    useState<Resultado | null>(null);

  const [dia, setDia] = useState("todos");
  const [vehiculo, setVehiculo] = useState("todos");

  useEffect(() => {
    const control = new AbortController();

    Promise.all([
      fetch(`${API}/api/48h/disponibles`, {
        signal: control.signal,
      }).then((r) => {
        if (!r.ok) {
          throw new Error(
            "No se pudieron consultar las planificaciones"
          );
        }
        return r.json();
      }),

      fetch(`${API}/api/escenarios/modelos`, {
        signal: control.signal,
      }).then((r) => {
        if (!r.ok) {
          throw new Error(
            "No se pudo consultar el catálogo de modelos"
          );
        }
        return r.json();
      }),
    ])
      .then(([a, b]) => {
        if (control.signal.aborted) return;

        setFechas(a.fechas || []);
        setFecha(a.fechas?.[0] || "");
        setModelos(b.modelos || []);
      })
      .catch((e) => {
        if (!control.signal.aborted) {
          setError(
            e instanceof Error
              ? e.message
              : "Error de conexión"
          );
        }
      });

    return () => control.abort();
  }, []);

  const horasVisibles = useMemo(
    () =>
      resultado?.horas.filter(
        (h) =>
          dia === "todos" ||
          h.fecha_local.slice(0, 10) === dia
      ) || [],
    [resultado, dia]
  );

  const dias = useMemo(
    () => [
      ...new Set(
        resultado?.horas.map(
          (h) => h.fecha_local.slice(0, 10)
        ) || []
      ),
    ],
    [resultado]
  );

  async function simular() {
    if (!fecha) return;

    setCargando(true);
    setError("");
    setResultado(null);
    setDia("todos");
    setVehiculo("todos");

    try {
      const res = await fetch(
        `${API}/api/escenarios/simular`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            fecha_consulta: fecha,
            modelo,
            cambio_demanda_pct: demanda,
          }),
        }
      );

      const payload = await res.json();

      if (!res.ok) {
        throw new Error(
          typeof payload.detail === "string"
            ? payload.detail
            : "No se pudo optimizar el escenario"
        );
      }

      setResultado(payload as Resultado);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Error al ejecutar el escenario"
      );
    } finally {
      setCargando(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#F7F8FC] text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-5 sm:px-8">
          <Link
            href="/"
            className="text-2xl font-extrabold"
          >
            Flot
            <span className="text-violet-600">IQ</span>
          </Link>

          <div className="flex gap-4 text-sm">
            <Link
              href="/dashboard"
              className="text-slate-600 hover:text-violet-600"
            >
              Centro de operaciones
            </Link>

            <span className="font-bold text-violet-700">
              Simulador
            </span>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl space-y-6 px-5 py-8 sm:px-8">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-violet-600">
            FLOTIQ · LABORATORIO DE ESCENARIOS
          </p>

          <h1 className="mt-2 text-3xl font-bold">
            Modelos y demanda de viajes
          </h1>

          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
            Selecciona un método de predicción y simula
            cambios de demanda. El optimizador recalcula
            las recargas sin modificar el plan original.
          </p>
        </div>

        <section className="grid gap-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:grid-cols-3">
          <label className="text-sm font-bold">
            Jornadas a planificar

            <select
              value={fecha}
              onChange={(e) => {
                setFecha(e.target.value);
                setResultado(null);
              }}
              className="mt-2 block w-full rounded-xl border border-slate-200 bg-white p-3 font-normal"
            >
              {fechas.map((f) => (
                <option key={f} value={f}>
                  {diasPlan(f, 1)} y {diasPlan(f, 2)}
                </option>
              ))}
            </select>

            <span className="mt-1 block text-xs font-normal text-slate-500">
              Fecha de referencia: {fecha || "—"}
            </span>
          </label>

          <label className="text-sm font-bold">
            Modelo de precios

            <select
              value={modelo}
              onChange={(e) => {
                setModelo(e.target.value);
                setResultado(null);
              }}
              className="mt-2 block w-full rounded-xl border border-slate-200 bg-white p-3 font-normal"
            >
              {modelos.map((m) => (
                <option
                  key={m.id}
                  value={m.id}
                  disabled={!m.disponible}
                >
                  {m.nombre}
                  {m.disponible
                    ? ""
                    : " · sin modelo guardado"}
                </option>
              ))}
            </select>

            <span className="mt-1 block text-xs font-normal text-slate-500">
              Solo se pueden utilizar modelos disponibles.
            </span>
          </label>

          <div>
            <label
              htmlFor="demanda"
              className="flex justify-between text-sm font-bold"
            >
              <span>Cambio de demanda</span>

              <span className="text-violet-700">
                {demanda > 0 ? "+" : ""}
                {demanda}%
              </span>
            </label>

            <input
              id="demanda"
              type="range"
              min={-30}
              max={50}
              step={5}
              value={demanda}
              onChange={(e) => {
                setDemanda(Number(e.target.value));
                setResultado(null);
              }}
              className="mt-6 w-full accent-violet-600"
            />

            <div className="mt-2 flex justify-between text-xs text-slate-500">
              <span>−30%</span>
              <span>Normal</span>
              <span>+50%</span>
            </div>

            <p className="mt-2 text-xs text-slate-500">
              Modifica los kWh consumidos en los servicios.
              No cambia los turnos ni el número de viajes.
            </p>
          </div>

          <div className="lg:col-span-3">
            <button
              type="button"
              disabled={!fecha || cargando}
              onClick={simular}
              className="w-full rounded-xl bg-violet-600 px-6 py-3 font-bold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
            >
              {cargando
                ? "Optimizando escenario…"
                : "Calcular planificación alternativa"}
            </button>

            {cargando && (
              <p className="mt-2 text-sm text-slate-500">
                El solver CBC está recalculando las
                recargas. Mantén abierta esta pestaña
                mientras se completa la petición.
              </p>
            )}
          </div>
        </section>

        {error && (
          <div
            role="alert"
            className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800"
          >
            {error}
          </div>
        )}

        {resultado && (
          <>
            <section className="rounded-2xl border border-violet-200 bg-violet-50 p-5">
              <p className="text-sm font-bold text-violet-900">
                Escenario: {resultado.nombre_modelo}
                {" · "}
                {resultado.cambio_demanda_pct > 0
                  ? "+"
                  : ""}
                {resultado.cambio_demanda_pct}%
                de demanda
              </p>

              <p className="mt-1 text-xs text-violet-700">
                {resultado.estado_solver}
                {" · "}
                {resultado.factibilidad_validada
                  ? "Solución factible"
                  : "Sin validación"}
                {" · "}
                {resultado.optimalidad_certificada
                  ? "Óptimo certificado"
                  : "Optimalidad no certificada"}
              </p>
            </section>

            <div className="grid gap-4 sm:grid-cols-3">
              {[
                [
                  "Energía de red",
                  `${numero(
                    resultado.energia_total_kwh
                  )} kWh`,
                ],
                [
                  "Coste previsto con el modelo elegido",
                  `${numero(
                    resultado.coste_estimado_eur
                  )} €`,
                ],
                [
                  "Mismo plan valorado con precios baseline",
                  `${numero(
                    resultado.coste_bajo_baseline_comun_eur
                  )} €`,
                ],
              ].map(([etiqueta, valor]) => (
                <div
                  key={etiqueta}
                  className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
                >
                  <p className="text-xs font-semibold uppercase text-slate-500">
                    {etiqueta}
                  </p>

                  <p className="mt-2 text-2xl font-bold">
                    {valor}
                  </p>
                </div>
              ))}
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setDia("todos")}
                className={`rounded-xl px-4 py-2 text-sm font-semibold ${
                  dia === "todos"
                    ? "bg-slate-900 text-white"
                    : "bg-white text-slate-700"
                }`}
              >
                48 horas
              </button>

              {dias.map((d) => (
                <button
                  type="button"
                  key={d}
                  onClick={() => setDia(d)}
                  className={`rounded-xl px-4 py-2 text-sm font-semibold ${
                    dia === d
                      ? "bg-slate-900 text-white"
                      : "bg-white text-slate-700"
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              <Grafico
                titulo="Precio horario previsto"
                unidad="€/MWh"
                color="#7C3AED"
                descripcion="Predicción del método seleccionado. No son precios reales futuros."
                puntos={horasVisibles.map((h) => ({
                  fecha: h.fecha_local,
                  valor: h.precio_eur_mwh,
                }))}
              />

              <Grafico
                titulo="Recargas programadas"
                unidad="kWh"
                color="#059669"
                descripcion="Energía que el optimizador asigna a cada hora del nuevo escenario."
                puntos={horasVisibles.map((h) => ({
                  fecha: h.fecha_local,
                  valor: h.energia_red_kwh,
                }))}
              />
            </div>

            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h2 className="text-lg font-bold">
                    Recargas por vehículo
                  </h2>

                  <p className="mt-1 text-sm text-slate-500">
                    Tramos de recarga recalculados.
                  </p>
                </div>

                <label className="text-sm font-semibold">
                  Vehículo

                  <select
                    aria-label="Filtrar sesiones por vehículo"
                    value={vehiculo}
                    onChange={(e) =>
                      setVehiculo(e.target.value)
                    }
                    className="ml-3 rounded-xl border border-slate-200 bg-white p-2 text-sm font-normal"
                  >
                    <option value="todos">Todos</option>

                    {Array.from(
                      new Set(
                        resultado.sesiones_recarga.map(
                          (s) => s.vehiculo
                        )
                      )
                    )
                      .sort()
                      .map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                  </select>
                </label>
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {resultado.sesiones_recarga
                  .filter(
                    (s) =>
                      (vehiculo === "todos" ||
                        s.vehiculo === vehiculo) &&
                      (dia === "todos" ||
                        s.inicio_local.slice(0, 10) === dia)
                  )
                  .slice(
                    0,
                    vehiculo === "todos" ? 12 : 60
                  )
                  .map((s, i) => (
                    <div
                      key={`${s.vehiculo}-${s.inicio_local}-${i}`}
                      className="rounded-xl border border-violet-100 bg-violet-50 p-4"
                    >
                      <p className="font-bold text-violet-900">
                        {s.vehiculo}
                      </p>

                      <p className="mt-1 text-sm text-violet-800">
                        {fechaHora(s.inicio_local)}
                        {" – "}
                        {fechaHora(s.fin_local)}
                      </p>

                      <p className="mt-1 text-xs text-violet-700">
                        {numero(s.energia_kwh)} kWh
                        programados
                      </p>
                    </div>
                  ))}
              </div>

              {resultado.sesiones_recarga.length === 0 && (
                <p className="mt-4 text-sm text-slate-500">
                  No hay recargas programadas.
                </p>
              )}

              <p className="mt-3 text-xs text-slate-500">
                Se muestran las primeras sesiones;
                selecciona un vehículo para consultar
                su agenda.
              </p>
            </section>

            <p className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-900">
              {resultado.nota}
              {" "}
              Valorar el mismo plan con precios
              del baseline permite una referencia
              común, pero no demuestra ahorros reales
              ni mayor precisión predictiva.
            </p>
          </>
        )}
      </div>
    </main>
  );
}
