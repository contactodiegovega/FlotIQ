

'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import GraficosEnergia48h from '@/components/GraficosEnergia48h';
import TurnosConductores48h from '@/components/TurnosConductores48h';

const API =
  process.env.NEXT_PUBLIC_FLOTIQ_API_URL ||
  'http://127.0.0.1:8000';

type Vista =
  | 'resumen'
  | 'vehiculos'
  | 'cargadores'
  | 'conductores'
  | 'energia';
type Estado = 'cargando' | 'trabajando' | 'disponible';

type Resumen = {
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

type Precio = {
  fecha_local: string;
  precio_predicho_eur_mwh: number;
};

type HoraFlota = {
  fecha_local: string;
  energia_red_kwh: number;
  coste_estimado_eur: number;
  cargadores_ocupados: number;
  soc_medio_pct: number;
  soc_minimo_pct: number;
};

type Registro = {
  vehicle_id: string;
  fecha_local: string;
  estado: Estado;
  cargador_id: string | null;
  energia_red_kwh: number;
  energia_consumida_kwh: number;
  soc_pct: number;
};

type Calendario = {
  dias: string[];
  vehiculos: string[];
  cargadores: string[];
  registros: Registro[];
  advertencia: string;
};

type Datos = {
  resumen: Resumen;
  precios: Precio[];
  flota: HoraFlota[];
  calendario: Calendario;
};

type Tramo = {
  vehicle_id: string;
  estado: Estado;
  cargador_id: string | null;
  inicio: string;
  ultimaHora: string;
  fin: string;
  energia: number;
  consumo: number;
  socFinal: number;
};

const vistas: {
  id: Vista;
  titulo: string;
  descripcion: string;
}[] = [
  {
    id: 'resumen',
    titulo: 'Resumen',
    descripcion: 'Qué hay que hacer',
  },
  {
    id: 'vehiculos',
    titulo: 'Vehículos',
    descripcion: 'Turnos y recargas',
  },
  {
    id: 'cargadores',
    titulo: 'Cargadores',
    descripcion: 'Puestos y horarios',
  },
  {
  id: 'conductores',
  titulo: 'Conductores',
  descripcion: 'Personal y turnos',
},
  {
    id: 'energia',
    titulo: 'Precios y energía',
    descripcion: 'Análisis de 48 h',
  },
];

const estiloEstado: Record<Estado, string> = {
  cargando: 'border-violet-200 bg-violet-50 text-violet-800',
  trabajando: 'border-amber-200 bg-amber-50 text-amber-800',
  disponible: 'border-slate-200 bg-slate-50 text-slate-600',
};

const textoEstado: Record<Estado, string> = {
  cargando: 'Recargando',
  trabajando: 'En servicio (estimado)',
  disponible: 'Disponible',
};

function numero(valor: number, decimales = 2) {
  return valor.toLocaleString('es-ES', {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  });
}

function horaMadrid(fecha: string) {
  return new Date(fecha).toLocaleTimeString('es-ES', {
    timeZone: 'Europe/Madrid',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  });
}

function diaLegible(dia: string) {
  return new Date(`${dia}T12:00:00Z`).toLocaleDateString('es-ES', {
    timeZone: 'UTC',
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
}

function finDeHora(fecha: string) {
  return new Date(
    new Date(fecha).getTime() + 3600000
  ).toISOString();
}

function agrupar(registros: Registro[]): Tramo[] {
  const ordenados = [...registros].sort(
    (a, b) =>
      Date.parse(a.fecha_local) - Date.parse(b.fecha_local)
  );

  const salida: Tramo[] = [];

  for (const r of ordenados) {
    const anterior = salida[salida.length - 1];

    const continuo =
      anterior &&
      anterior.vehicle_id === r.vehicle_id &&
      anterior.estado === r.estado &&
      anterior.cargador_id === r.cargador_id &&
      Date.parse(r.fecha_local) -
        Date.parse(anterior.ultimaHora) ===
        3600000;

    if (continuo) {
      anterior.ultimaHora = r.fecha_local;
      anterior.fin = finDeHora(r.fecha_local);
      anterior.energia += r.energia_red_kwh;
      anterior.consumo += r.energia_consumida_kwh;
      anterior.socFinal = r.soc_pct;
    } else {
      salida.push({
        vehicle_id: r.vehicle_id,
        estado: r.estado,
        cargador_id: r.cargador_id,
        inicio: r.fecha_local,
        ultimaHora: r.fecha_local,
        fin: finDeHora(r.fecha_local),
        energia: r.energia_red_kwh,
        consumo: r.energia_consumida_kwh,
        socFinal: r.soc_pct,
      });
    }
  }

  return salida;
}

async function pedir<T>(
  ruta: string,
  signal: AbortSignal
): Promise<T> {
  const respuesta = await fetch(`${API}${ruta}`, {
    signal,
    cache: 'no-store',
  });

  if (!respuesta.ok) {
    throw new Error(
      `La API ha respondido con error ${respuesta.status}: ${ruta}`
    );
  }

  return (await respuesta.json()) as T;
}

function Tarjeta({
  etiqueta,
  valor,
  nota,
}: {
  etiqueta: string;
  valor: string;
  nota?: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {etiqueta}
      </p>

      <p className="mt-2 text-2xl font-bold tracking-tight text-slate-900">
        {valor}
      </p>

      {nota && (
        <p className="mt-1 text-xs text-slate-500">
          {nota}
        </p>
      )}
    </div>
  );
}

function Grafico({
  titulo,
  unidad,
  color,
  puntos,
}: {
  titulo: string;
  unidad: string;
  color: string;
  puntos: { fecha: string; valor: number }[];
}) {
  if (!puntos.length) return null;

  const valores = puntos.map((p) => p.valor);
  const minimo = Math.min(0, ...valores);
  const maximo = Math.max(1, ...valores);
  const rango = Math.max(1, maximo - minimo);

  const posX = (i: number) =>
    45 + (i * 620) / Math.max(1, puntos.length - 1);

  const posY = (v: number) =>
    175 - ((v - minimo) / rango) * 145;

  const camino = puntos
    .map(
      (p, i) =>
        `${i === 0 ? 'M' : 'L'}${posX(i).toFixed(2)},${posY(
          p.valor
        ).toFixed(2)}`
    )
    .join(' ');

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="font-semibold text-slate-900">
        {titulo}
      </h3>

      <p className="mt-1 text-xs text-slate-500">
        {unidad} · Horario de Madrid
      </p>

      <svg
        viewBox="0 0 690 215"
        className="mt-4 w-full"
        role="img"
        aria-label={titulo}
      >
        {[0, 0.5, 1].map((f) => {
          const valor = minimo + rango * f;

          return (
            <g key={f}>
              <line
                x1="45"
                x2="665"
                y1={posY(valor)}
                y2={posY(valor)}
                stroke="#E2E8F0"
                strokeDasharray="4 5"
              />

              <text
                x="37"
                y={posY(valor) + 4}
                textAnchor="end"
                fill="#64748B"
                fontSize="11"
              >
                {numero(valor, 0)}
              </text>
            </g>
          );
        })}

        <path
          d={camino}
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {puntos.map((p, i) => (
          <circle
            key={i}
            cx={posX(i)}
            cy={posY(p.valor)}
            r="3"
            fill={color}
          >
            <title>
              {horaMadrid(p.fecha)} · {numero(p.valor)} {unidad}
            </title>
          </circle>
        ))}

        {puntos.map((p, i) =>
          i % 12 === 0 ? (
            <text
              key={i}
              x={posX(i)}
              y="205"
              fill="#64748B"
              fontSize="11"
              textAnchor="middle"
            >
              {new Date(p.fecha).toLocaleDateString('es-ES', {
                timeZone: 'Europe/Madrid',
                day: 'numeric',
                month: 'short',
              })}{' '}
              {horaMadrid(p.fecha)}
            </text>
          ) : null
        )}
      </svg>
    </div>
  );
}
function fechaPlan(fecha: string, dias: number) {
  const [anio, mes, dia] = fecha.split('-').map(Number);

  const valor = new Date(
    Date.UTC(anio, mes - 1, dia + dias)
  );

  return valor.toLocaleDateString('es-ES', {
    timeZone: 'UTC',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}
export default function DashboardPage() {
  const [vista, setVista] = useState<Vista>('resumen');
  const [fechas, setFechas] = useState<string[]>([]);
  const [fechaConsulta, setFechaConsulta] = useState('');
  const [datos, setDatos] = useState<Datos | null>(null);
  const [dia, setDia] = useState('');
  const [vehiculo, setVehiculo] = useState('V001');
  const [busqueda, setBusqueda] = useState('');
  const [cargador, setCargador] = useState('C01');
  const [hora, setHora] = useState('');
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');

  // Cargar fechas disponibles

  useEffect(() => {
    const control = new AbortController();

    pedir<{ fechas: string[] }>(
      '/api/48h/disponibles',
      control.signal
    )
      .then((r) => {
        if (control.signal.aborted) return;

        setFechas(r.fechas);
        setFechaConsulta(r.fechas[0] || '');

        if (!r.fechas.length) {
          setCargando(false);
        }
      })
      .catch((e: Error) => {
        if (!control.signal.aborted) {
          setError(e.message);
          setCargando(false);
        }
      });

    return () => control.abort();
  }, []);

  // Obtener resultados del pipeline

  useEffect(() => {
    if (!fechaConsulta) return;

    const control = new AbortController();

    setCargando(true);
    setError('');

    Promise.all([
      pedir<Resumen>(
        `/api/48h/${fechaConsulta}/resumen`,
        control.signal
      ),
      pedir<{ registros: Precio[] }>(
        `/api/48h/${fechaConsulta}/precios`,
        control.signal
      ),
      pedir<{ registros: HoraFlota[] }>(
        `/api/48h/${fechaConsulta}/flota`,
        control.signal
      ),
      pedir<Calendario>(
        `/api/48h/${fechaConsulta}/calendario`,
        control.signal
      ),
    ])
      .then(([resumen, precios, flota, calendario]) => {
        if (control.signal.aborted) return;

        setDatos({
          resumen,
          precios: precios.registros,
          flota: flota.registros,
          calendario,
        });

        setDia(calendario.dias[0] || '');
        setVehiculo(calendario.vehiculos[0] || 'V001');
        setCargador(calendario.cargadores[0] || 'C01');
        setHora('');
      })
      .catch((e: Error) => {
        if (!control.signal.aborted) {
          setDatos(null);
          setError(e.message);
        }
      })
      .finally(() => {
        if (!control.signal.aborted) {
          setCargando(false);
        }
      });

    return () => control.abort();
  }, [fechaConsulta]);

  // Datos correspondientes al dia elegido

  const registrosDia = useMemo(
    () =>
      datos?.calendario.registros.filter(
        (r) => r.fecha_local.slice(0, 10) === dia
      ) || [],
    [datos, dia]
  );

  const horasDia = useMemo(
    () =>
      [
        ...new Set(
          registrosDia.map((r) => r.fecha_local)
        ),
      ].sort((a, b) => Date.parse(a) - Date.parse(b)),
    [registrosDia]
  );

  const horaSeleccionada = horasDia.includes(hora)
    ? hora
    : horasDia[0] || '';

  const registrosVehiculo = registrosDia.filter(
    (r) => r.vehicle_id === vehiculo
  );

  const tramosVehiculo = agrupar(registrosVehiculo);

  const finVehiculo =
    registrosVehiculo[registrosVehiculo.length - 1];

  const flotaDia =
    datos?.flota.filter(
      (r) => r.fecha_local.slice(0, 10) === dia
    ) || [];

  const energiaDia = flotaDia.reduce(
    (a, r) => a + r.energia_red_kwh,
    0
  );

  const costeDia = flotaDia.reduce(
    (a, r) => a + r.coste_estimado_eur,
    0
  );

  const ocupacionMax = Math.max(
    0,
    ...flotaDia.map((r) => r.cargadores_ocupados)
  );

  const trabajandoDia = new Set(
    registrosDia
      .filter((r) => r.estado === 'trabajando')
      .map((r) => r.vehicle_id)
  ).size;

  // Recargas organizadas por tramos consecutivos

  const sesiones = useMemo(() => {
    if (!datos) return [] as Tramo[];

    return datos.calendario.vehiculos
      .flatMap((v) =>
        agrupar(
          registrosDia.filter(
            (r) => r.vehicle_id === v
          )
        ).filter((t) => t.estado === 'cargando')
      )
      .sort(
        (a, b) =>
          Date.parse(a.inicio) - Date.parse(b.inicio)
      );
  }, [datos, registrosDia]);

  const vehiculosFiltrados =
    datos?.calendario.vehiculos.filter((v) =>
      v
        .toLowerCase()
        .includes(busqueda.trim().toLowerCase())
    ) || [];

  const registrosHora = registrosDia.filter(
    (r) => r.fecha_local === horaSeleccionada
  );

  const cargadoresEnHora = new Map<string, Registro>(
    registrosHora
      .filter((r) => r.cargador_id !== null)
      .map((r) => [r.cargador_id as string, r])
  );

  const registroCargador = cargadoresEnHora.get(cargador);

  const tramosCargador = sesiones.filter(
    (s) => s.cargador_id === cargador
  );

  function abrirVehiculo(id: string) {
    setVehiculo(id);
    setVista('vehiculos');
  }

  return (
    <main className="min-h-screen bg-[#F7F8FC] text-slate-900">
      {/* CABECERA */}

      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-5 py-5 sm:px-8">
          <Link
            href="/"
            className="text-2xl font-extrabold tracking-tight"
          >
            Flot
            <span className="text-violet-600">IQ</span>
          </Link>

          <div className="flex items-center gap-5 text-sm">
            <Link
              href="/"
              className="text-slate-500 hover:text-violet-700"
            >
              Inicio
            </Link>

            <Link
              href="/planificacion"
              className="text-slate-500 hover:text-violet-700"
            >
              Planificación semanal
            </Link>

            <span className="rounded-full bg-violet-50 px-3 py-1.5 font-medium text-violet-700">
              Centro de operaciones
            </span>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-5 py-8 sm:px-8">
        {/* TITULO Y SELECCION DE PLAN */}

        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-violet-600">
              FLOTIQ · PLANIFICACIÓN A 48 HORAS
            </p>

            <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
              Centro de operaciones
            </h1>

            <p className="mt-2 text-sm text-slate-500">
              Consulta qué vehículos trabajan, cuándo recargan
              y qué cargador deben utilizar.
            </p>
          </div>

          <label className="text-sm font-semibold text-slate-700">
            Plan disponible

            <select
              className="mt-2 block w-full min-w-[170px] rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm"
              value={fechaConsulta}
              onChange={(e) => {
                setFechaConsulta(e.target.value);
                setDatos(null);
                setCargando(true);
              }}
              
            >
              {fechas.map((f) => (
                <option key={f} value={f}>
                  {fechaPlan(f, 1)} y {fechaPlan(f, 2)}
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs font-normal text-slate-500">
                Fecha de referencia: {fechaConsulta || '—'}
                {' · '}Escenario simulado
                </p>
          </label>
        </div>

        {/* NAVEGACION PRINCIPAL */}

        <nav
          className="mt-7 grid grid-cols-2 gap-2 rounded-2xl border border-slate-200 bg-white p-2 md:grid-cols-5"
          aria-label="Secciones del centro de operaciones"
        >
          {vistas.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => setVista(v.id)}
              aria-current={
                vista === v.id ? 'page' : undefined
              }
              className={
                vista === v.id
                  ? 'rounded-xl bg-violet-600 px-4 py-3 text-left text-white shadow-sm'
                  : 'rounded-xl px-4 py-3 text-left text-slate-600 hover:bg-slate-50'
              }
            >
              <span className="block text-sm font-bold">
                {v.titulo}
              </span>

              <span
                className={`mt-0.5 block text-xs ${
                  vista === v.id
                    ? 'text-violet-100'
                    : 'text-slate-400'
                }`}
              >
                {v.descripcion}
              </span>
            </button>
          ))}
        </nav>

        {/* ESTADOS DE CARGA */}

        {error && (
          <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
            <p className="font-bold">
              No se han podido cargar los datos.
            </p>

            <p className="mt-1">{error}</p>

            <p className="mt-2">
              Comprueba que FastAPI esté ejecutándose
              en el puerto 8000.
            </p>
          </div>
        )}

        {cargando && !error && (
          <p className="mt-6 rounded-2xl border border-slate-200 bg-white p-8 text-slate-500">
            Cargando la planificación de FLOTIQ...
          </p>
        )}

        {!cargando && !error && fechas.length === 0 && (
          <p className="mt-6 rounded-2xl bg-white p-8 text-slate-600">
            Todavía no hay planificaciones completas
            para mostrar.
          </p>
        )}

        {datos && !cargando && !error && (
          <>
            {/* INFORMACION DEL PLAN */}

            <div className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-violet-100 bg-violet-50 px-5 py-4">
              <div>
                <p className="text-sm font-bold text-violet-900">
                  Plan de 48 horas ·{' '}
                  {datos.calendario.dias.join(' y ')}
                </p>

                <p className="mt-1 text-xs text-violet-700">
                  {datos.resumen.factibilidad_validada
                    ? 'Plan factible'
                    : 'Factibilidad no validada'}
                  {' · '}
                  {datos.resumen.estado_solver}
                  {' · '}
                  {datos.resumen.optimalidad_certificada
                    ? 'Óptimo certificado'
                    : 'Sin óptimo certificado'}
                </p>
              </div>

              <span className="rounded-full border border-violet-200 bg-white px-3 py-2 text-xs font-semibold text-violet-800">
                Escenario simulado · No son turnos confirmados
              </span>
            </div>

            {/* SELECCION DE DIA */}

            <div
              className="mt-6 flex flex-wrap gap-2"
              aria-label="Día que se desea consultar"
            >
              {datos.calendario.dias.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => {
                    setDia(d);
                    setHora('');
                  }}
                  className={
                    dia === d
                      ? 'rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white'
                      : 'rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-600 hover:border-violet-300'
                  }
                >
                  {diaLegible(d)}
                </button>
              ))}
            </div>

            {/* ====================================== */}
            {/* VISTA 1: RESUMEN */}
            {/* ====================================== */}

            {vista === 'resumen' && (
              <div className="mt-6 space-y-6">
                <div>
                  <h2 className="text-xl font-bold">
                    El plan de un vistazo
                  </h2>

                  <p className="mt-1 text-sm text-slate-500">
                    Totales previstos para las 48 horas.
                  </p>
                </div>

                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <Tarjeta
                    etiqueta="Coste estimado · 48 h"
                    valor={`${numero(
                      datos.resumen.coste_estimado_eur
                    )} €`}
                  />

                  <Tarjeta
                    etiqueta="Energía de red · 48 h"
                    valor={`${numero(
                      datos.resumen.energia_red_kwh
                    )} kWh`}
                  />

                  <Tarjeta
                    etiqueta="Vehículos de la flota"
                    valor={String(datos.resumen.vehiculos)}
                  />

                  <Tarjeta
                    etiqueta="SOC mínimo tras el primer día"
                    valor={
                      datos.resumen.continuidad
                        ? `${numero(
                            datos.resumen.continuidad.soc_minimo_pct
                          )} %`
                        : 'No disponible'
                    }
                  />
                </div>

                {/* ACTIVIDAD DEL DIA */}

                <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h2 className="text-xl font-bold">
                        Jornada del {diaLegible(dia)}
                      </h2>

                      <p className="mt-1 text-sm text-slate-500">
                        Actividad prevista para el día seleccionado.
                      </p>
                    </div>

                    <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600">
                      {sesiones.length} sesiones de recarga
                    </span>
                  </div>

                  <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <Tarjeta
                      etiqueta="Vehículos con servicio"
                      valor={String(trabajandoDia)}
                    />

                    <Tarjeta
                      etiqueta="Energía del día"
                      valor={`${numero(energiaDia)} kWh`}
                    />

                    <Tarjeta
                      etiqueta="Coste del día"
                      valor={`${numero(costeDia)} €`}
                    />

                    <Tarjeta
                      etiqueta="Máxima carga simultánea"
                      valor={`${ocupacionMax} / 20`}
                      nota="Vehículos cargando"
                    />
                  </div>
                </section>

                {/* PROXIMAS RECARGAS Y ACCESOS */}

                <section className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
                  <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h2 className="text-lg font-bold">
                        Primeras recargas programadas
                      </h2>

                      <button
                        type="button"
                        onClick={() => setVista('vehiculos')}
                        className="text-sm font-semibold text-violet-700 hover:underline"
                      >
                        Ver vehículos
                      </button>
                    </div>

                    {sesiones.length === 0 ? (
                      <p className="mt-5 text-sm text-slate-500">
                        No hay recargas previstas para este día.
                      </p>
                    ) : (
                      <div className="mt-4 divide-y divide-slate-100">
                        {sesiones.slice(0, 8).map((s, i) => (
                          <button
                            key={`${s.vehicle_id}-${s.inicio}-${i}`}
                            type="button"
                            onClick={() =>
                              abrirVehiculo(s.vehicle_id)
                            }
                            className="flex w-full items-center justify-between gap-3 py-3 text-left hover:bg-violet-50"
                          >
                            <div>
                              <p className="font-semibold">
                                {s.vehicle_id}{' '}
                                <span className="font-normal text-slate-500">
                                  · {s.cargador_id}
                                </span>
                              </p>

                              <p className="mt-1 text-xs text-slate-500">
                                {horaMadrid(s.inicio)}
                                {' – '}
                                {horaMadrid(s.fin)}
                              </p>
                            </div>

                            <span className="text-sm font-semibold text-violet-700">
                              {numero(s.energia)} kWh
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="flex flex-col justify-between rounded-2xl border border-violet-100 bg-violet-50 p-6">
                    <div>
                      <h2 className="text-lg font-bold text-violet-950">
                        ¿Qué necesitas consultar?
                      </h2>

                      <p className="mt-2 text-sm leading-6 text-violet-800">
                        Elige un vehículo para saber cuándo trabaja
                        y debe cargar, o consulta un cargador para
                        ver qué coche tiene asignado a cada hora.
                      </p>
                    </div>

                    <div className="mt-6 grid gap-3">
                      <button
                        type="button"
                        onClick={() => setVista('vehiculos')}
                        className="rounded-xl bg-violet-600 px-5 py-3 text-left text-sm font-bold text-white hover:bg-violet-700"
                      >
                        Consultar turnos y recargas →
                      </button>

                      <button
                        type="button"
                        onClick={() => setVista('cargadores')}
                        className="rounded-xl border border-violet-200 bg-white px-5 py-3 text-left text-sm font-bold text-violet-800 hover:bg-violet-100"
                      >
                        Consultar los 20 cargadores →
                      </button>
                    </div>
                  </div>
                </section>
              </div>
            )}

            {/* ====================================== */}
            {/* VISTA 2: VEHICULOS */}
            {/* ====================================== */}

            {vista === 'vehiculos' && (
              <section className="mt-6 grid gap-5 lg:grid-cols-[260px_1fr]">
                {/* SELECTOR DE VEHICULO */}

                <aside className="self-start rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <h2 className="font-bold">
                    Seleccionar vehículo
                  </h2>

                  <p className="mt-1 text-xs text-slate-500">
                    Busca entre los 50 vehículos.
                  </p>

                  <input
                    type="search"
                    value={busqueda}
                    onChange={(e) =>
                      setBusqueda(e.target.value)
                    }
                    placeholder="Buscar V001, V002..."
                    className="mt-4 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm outline-none focus:border-violet-500"
                  />

                  <div className="mt-3 grid max-h-80 grid-cols-2 gap-2 overflow-y-auto lg:grid-cols-1">
                    {vehiculosFiltrados.map((v) => (
                      <button
                        type="button"
                        key={v}
                        onClick={() => setVehiculo(v)}
                        className={
                          v === vehiculo
                            ? 'rounded-lg bg-violet-600 px-4 py-3 text-left text-sm font-bold text-white'
                            : 'rounded-lg bg-slate-50 px-4 py-3 text-left text-sm font-semibold text-slate-700 hover:bg-violet-50'
                        }
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                </aside>

                {/* AGENDA VEHICULO */}

                <div className="min-w-0 space-y-5">
                  <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-widest text-violet-600">
                          Agenda por vehículo
                        </p>

                        <h2 className="mt-1 text-2xl font-bold">
                          {vehiculo}
                        </h2>

                        <p className="mt-1 text-sm text-slate-500">
                          {diaLegible(dia)} · Actividad estimada
                        </p>
                      </div>

                      <select
                        value={vehiculo}
                        onChange={(e) =>
                          setVehiculo(e.target.value)
                        }
                        className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm"
                      >
                        {datos.calendario.vehiculos.map((v) => (
                          <option key={v} value={v}>
                            {v}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="mt-5 grid gap-3 sm:grid-cols-3">
                      <Tarjeta
                        etiqueta="Horas de servicio"
                        valor={`${
                          registrosVehiculo.filter(
                            (r) => r.estado === 'trabajando'
                          ).length
                        } h`}
                      />

                      <Tarjeta
                        etiqueta="Recarga del día"
                        valor={`${numero(
                          registrosVehiculo.reduce(
                            (s, r) => s + r.energia_red_kwh,
                            0
                          )
                        )} kWh`}
                      />

                      <Tarjeta
                        etiqueta="SOC al final del día"
                        valor={
                          finVehiculo
                            ? `${numero(finVehiculo.soc_pct)} %`
                            : '—'
                        }
                      />
                    </div>
                  </div>

                  {/* TRAMOS DE TRABAJO Y RECARGA */}

                  <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <h3 className="text-lg font-bold">
                      Horario completo
                    </h3>

                    <p className="mt-1 text-sm text-slate-500">
                      Tramos consecutivos de trabajo,
                      disponibilidad y recarga. Cada cargador
                      aparece identificado.
                    </p>

                    <div className="mt-5 space-y-3">
                      {tramosVehiculo.map((t, i) => (
                        <div
                          key={`${t.inicio}-${i}`}
                          className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4 ${
                            estiloEstado[t.estado]
                          }`}
                        >
                          <div>
                            <p className="text-base font-bold">
                              {horaMadrid(t.inicio)}
                              {' – '}
                              {horaMadrid(t.fin)}
                            </p>

                            <p className="mt-1 text-sm font-semibold">
                              {textoEstado[t.estado]}
                              {t.cargador_id
                                ? ` · ${t.cargador_id}`
                                : ''}
                            </p>

                            <p className="mt-1 text-xs opacity-80">
                              {t.estado === 'cargando'
                                ? `${numero(
                                    t.energia
                                  )} kWh de red programados`
                                : t.estado === 'trabajando'
                                  ? `${numero(
                                      t.consumo
                                    )} kWh de consumo estimado`
                                  : 'Sin actividad asignada'}
                              {' · '}
                              SOC al acabar:{' '}
                              {numero(t.socFinal)} %
                            </p>
                          </div>

                          {t.cargador_id && (
                            <button
                              type="button"
                              onClick={() => {
                                setCargador(
                                  t.cargador_id || 'C01'
                                );
                                setHora(t.inicio);
                                setVista('cargadores');
                              }}
                              className="rounded-lg border border-violet-300 bg-white px-3 py-2 text-xs font-bold text-violet-800 hover:bg-violet-100"
                            >
                              Ver {t.cargador_id}
                            </button>
                          )}
                        </div>
                      ))}
                    </div>

                    {/* DETALLE OPCIONAL HORA A HORA */}

                    <details className="mt-6 rounded-xl border border-slate-200">
                      <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-slate-700">
                        Ver detalle hora por hora
                      </summary>

                      <div className="max-h-96 overflow-auto">
                        <table className="w-full min-w-[520px] text-left text-sm">
                          <thead className="sticky top-0 bg-slate-100 text-xs text-slate-500">
                            <tr>
                              <th className="p-3">Hora</th>
                              <th className="p-3">Estado</th>
                              <th className="p-3">Cargador</th>
                              <th className="p-3">Recarga</th>
                              <th className="p-3">SOC</th>
                            </tr>
                          </thead>

                          <tbody>
                            {registrosVehiculo.map((r) => (
                              <tr
                                key={r.fecha_local}
                                className="border-t border-slate-100"
                              >
                                <td className="p-3">
                                  {horaMadrid(r.fecha_local)}
                                </td>

                                <td className="p-3">
                                  {textoEstado[r.estado]}
                                </td>

                                <td className="p-3">
                                  {r.cargador_id || '—'}
                                </td>

                                <td className="p-3">
                                  {numero(
                                    r.energia_red_kwh
                                  )}{' '}
                                  kWh
                                </td>

                                <td className="p-3">
                                  {numero(r.soc_pct)} %
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  </div>
                </div>
              </section>
            )}

            {/* ====================================== */}
            {/* VISTA 3: CARGADORES */}
            {/* ====================================== */}

            {vista === 'cargadores' && (
              <div className="mt-6 space-y-5">
                <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <h2 className="text-xl font-bold">
                        Ocupación de cargadores
                      </h2>

                      <p className="mt-1 text-sm text-slate-500">
                        Selecciona una hora para saber qué
                        vehículo va en cada puesto.
                      </p>
                    </div>

                    {/* NAVEGACION HORARIA */}

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        aria-label="Hora anterior"
                        onClick={() =>
                          setHora(
                            horasDia[
                              Math.max(
                                0,
                                horasDia.indexOf(
                                  horaSeleccionada
                                ) - 1
                              )
                            ]
                          )
                        }
                        disabled={
                          horasDia.indexOf(
                            horaSeleccionada
                          ) <= 0
                        }
                        className="rounded-lg border border-slate-200 px-3 py-2 disabled:opacity-30"
                      >
                        ←
                      </button>

                      <select
                        value={horaSeleccionada}
                        onChange={(e) =>
                          setHora(e.target.value)
                        }
                        aria-label="Hora de consulta"
                        className="rounded-lg border border-slate-200 px-4 py-2 font-semibold"
                      >
                        {horasDia.map((h) => (
                          <option key={h} value={h}>
                            {horaMadrid(h)}
                          </option>
                        ))}
                      </select>

                      <button
                        type="button"
                        aria-label="Hora siguiente"
                        onClick={() =>
                          setHora(
                            horasDia[
                              Math.min(
                                horasDia.length - 1,
                                horasDia.indexOf(
                                  horaSeleccionada
                                ) + 1
                              )
                            ]
                          )
                        }
                        disabled={
                          horasDia.indexOf(
                            horaSeleccionada
                          ) >=
                          horasDia.length - 1
                        }
                        className="rounded-lg border border-slate-200 px-3 py-2 disabled:opacity-30"
                      >
                        →
                      </button>
                    </div>
                  </div>

                  <p className="mt-4 text-sm font-semibold text-violet-700">
                    {cargadoresEnHora.size} de 20 cargadores
                    con recarga programada a las{' '}
                    {horaMadrid(horaSeleccionada)}.
                  </p>

                  {/* LOS 20 CARGADORES */}

                  <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">
                    {datos.calendario.cargadores.map((c) => {
                      const ocupado = cargadoresEnHora.get(c);

                      return (
                        <button
                          key={c}
                          type="button"
                          onClick={() => setCargador(c)}
                          className={
                            `rounded-xl border p-4 text-left transition hover:border-violet-400 ` +
                            (c === cargador
                              ? 'ring-2 ring-violet-500 '
                              : '') +
                            (ocupado
                              ? 'border-violet-200 bg-violet-50'
                              : 'border-slate-200 bg-slate-50')
                          }
                        >
                          <p className="text-xs font-semibold text-slate-500">
                            Cargador {c}
                          </p>

                          <p className="mt-2 text-lg font-bold">
                            {ocupado?.vehicle_id || 'Libre'}
                          </p>

                          <p className="mt-1 text-xs text-slate-600">
                            {ocupado
                              ? `${numero(
                                  ocupado.energia_red_kwh
                                )} kWh en esta hora`
                              : 'Sin recarga prevista'}
                          </p>
                        </button>
                      );
                    })}
                  </div>

                  {/* ACCESO AL VEHICULO DEL CARGADOR */}

                  {registroCargador && (
                    <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-violet-50 p-4 text-sm">
                      <span>
                        <strong>{cargador}</strong>
                        {' · '}
                        {registroCargador.vehicle_id}
                        {' · '}
                        {horaMadrid(horaSeleccionada)}
                      </span>

                      <button
                        type="button"
                        className="font-bold text-violet-700 hover:underline"
                        onClick={() =>
                          abrirVehiculo(
                            registroCargador.vehicle_id
                          )
                        }
                      >
                        Consultar jornada de{' '}
                        {registroCargador.vehicle_id} →
                      </button>
                    </div>
                  )}
                </section>

                {/* AGENDA DEL CARGADOR */}

                <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <h2 className="text-lg font-bold">
                        Agenda del cargador {cargador}
                      </h2>

                      <p className="mt-1 text-sm text-slate-500">
                        Todas las recargas previstas en
                        este puesto durante el día.
                      </p>
                    </div>

                    <select
                      value={cargador}
                      onChange={(e) =>
                        setCargador(e.target.value)
                      }
                      className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm"
                    >
                      {datos.calendario.cargadores.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>

                  {tramosCargador.length === 0 ? (
                    <p className="mt-5 text-sm text-slate-500">
                      Sin recargas asignadas a este
                      cargador en este día.
                    </p>
                  ) : (
                    <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {tramosCargador.map((t, i) => (
                        <button
                          key={`${t.inicio}-${t.vehicle_id}-${i}`}
                          type="button"
                          onClick={() =>
                            abrirVehiculo(t.vehicle_id)
                          }
                          className="rounded-xl border border-violet-200 bg-violet-50 p-4 text-left hover:bg-violet-100"
                        >
                          <p className="font-bold text-violet-900">
                            {t.vehicle_id}
                          </p>

                          <p className="mt-1 text-sm text-violet-800">
                            {horaMadrid(t.inicio)}
                            {' – '}
                            {horaMadrid(t.fin)}
                          </p>

                          <p className="mt-1 text-xs text-violet-700">
                            {numero(t.energia)} kWh
                            {' · '}
                            Ver vehículo →
                          </p>
                        </button>
                      ))}
                    </div>
                  )}
                </section>
              </div>
            )}

            {/* ====================================== */}
            {/* VISTA 4: PRECIOS Y ENERGIA */}
            {/* ====================================== */}

           {vista === 'energia' && (
            <GraficosEnergia48h
                precios={datos.precios}
                flota={datos.flota}
            />
            )}

            {vista === 'conductores' && (
                <TurnosConductores48h
                    fechaConsulta={fechaConsulta}
                    dia={dia}
                />
                )}

            {/* ADVERTENCIA SOBRE DATOS SIMULADOS */}

            <footer className="mt-10 border-t border-slate-200 py-6 text-xs leading-5 text-slate-500">
              {datos.calendario.advertencia}
              {' '}
              El coste mostrado es una estimación;
              los resultados no acreditan ahorros reales.
            </footer>
          </>
        )}
      </div>
    </main>
  );
}
