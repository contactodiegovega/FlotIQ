
'use client';

import { useEffect, useMemo, useState } from 'react';

type Turno = {
  dia: string;
  conductor_id: string;
  nombre: string;
  vehiculo_id: string;
  tipo_turno: string;
  inicio_local: string;
  fin_local: string;
  horas: number;
};

type Respuesta = {
  total_turnos: number;
  total_conductores: number;
  turnos: Turno[];
  advertencia: string;
};

function hora(fecha: string) {
  return new Date(fecha).toLocaleTimeString('es-ES', {
    timeZone: 'Europe/Madrid',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  });
}

export default function TurnosConductores48h({
  fechaConsulta,
  dia,
}: {
  fechaConsulta: string;
  dia: string;
}) {
  const [datos, setDatos] = useState<Respuesta | null>(null);
  const [error, setError] = useState('');
  const [cargando, setCargando] = useState(true);
  const [busqueda, setBusqueda] = useState('');

  useEffect(() => {
    const control = new AbortController();

    setCargando(true);
    setDatos(null);
    setError('');

    fetch(
      `http://127.0.0.1:8000/api/48h/${fechaConsulta}/conductores`,
      {
        signal: control.signal,
        cache: 'no-store',
      }
    )
      .then(async (respuesta) => {
        if (!respuesta.ok) {
          const detalle = await respuesta.json().catch(() => null);
          throw new Error(
            detalle?.detail ||
            `Error HTTP ${respuesta.status}`
          );
        }

        return (await respuesta.json()) as Respuesta;
      })
      .then((resultado) => {
        if (!control.signal.aborted) {
          setDatos(resultado);
        }
      })
      .catch((fallo: unknown) => {
        if (!control.signal.aborted) {
          setError(
            fallo instanceof Error
              ? fallo.message
              : 'No se pudieron cargar los conductores.'
          );
        }
      })
      .finally(() => {
        if (!control.signal.aborted) {
          setCargando(false);
        }
      });

    return () => control.abort();
  }, [fechaConsulta]);

  const turnos = useMemo(() => {
    if (!datos) return [];

    const texto = busqueda.trim().toLowerCase();

    return datos.turnos.filter((turno) => {
      if (turno.dia !== dia) return false;

      return (
        turno.nombre.toLowerCase().includes(texto) ||
        turno.conductor_id.toLowerCase().includes(texto) ||
        turno.vehiculo_id.toLowerCase().includes(texto)
      );
    });
  }, [datos, dia, busqueda]);

  const turnosDia = datos?.turnos.filter(
    (t) => t.dia === dia
  ) || [];

  const conductoresDia = new Set(
    turnosDia.map((t) => t.conductor_id)
  ).size;

  const vehiculosDia = new Set(
    turnosDia.map((t) => t.vehiculo_id)
  ).size;

  return (
    <section className="mt-6 space-y-5">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-violet-600">
          Gestión de personal
        </p>

        <h2 className="mt-2 text-2xl font-bold">
          Conductores y turnos
        </h2>

        <p className="mt-2 text-sm text-slate-500">
          Consulta qué conductores aparecen en el
          escenario proyectado, sus horarios y el
          vehículo asociado.
        </p>
      </div>

      {cargando && (
        <div className="rounded-2xl bg-white p-6 text-slate-500">
          Cargando turnos...
        </div>
      )}

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
          {error}
        </div>
      )}

      {datos && !cargando && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            {[
              ['Conductores previstos', String(conductoresDia)],
              ['Turnos del día', String(turnosDia.length)],
              ['Vehículos asignados', String(vehiculosDia)],
            ].map(([titulo, valor]) => (
              <div
                key={titulo}
                className="rounded-2xl border border-slate-200 bg-white p-5"
              >
                <p className="text-xs font-semibold uppercase text-slate-500">
                  {titulo}
                </p>

                <p className="mt-2 text-3xl font-bold">
                  {valor}
                </p>
              </div>
            ))}
          </div>

          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 p-5">
              <div>
                <h3 className="text-lg font-bold">
                  Cuadrante de conductores
                </h3>

                <p className="mt-1 text-xs text-slate-500">
                  {turnos.length} turnos visibles
                </p>
              </div>

              <input
                type="search"
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
                placeholder="Buscar conductor o vehículo..."
                className="w-full max-w-xs rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-violet-500"
              />
            </div>

            <div className="max-h-[600px] overflow-auto">
              <table className="w-full min-w-[680px] text-left text-sm">
                <thead className="sticky top-0 bg-slate-100 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="p-4">Conductor</th>
                    <th className="p-4">Vehículo</th>
                    <th className="p-4">Turno</th>
                    <th className="p-4">Horario</th>
                    <th className="p-4">Horas</th>
                  </tr>
                </thead>

                <tbody>
                  {turnos.map((t, i) => (
                    <tr
                      key={`${t.conductor_id}-${t.inicio_local}-${i}`}
                      className="border-t border-slate-100 hover:bg-violet-50"
                    >
                      <td className="p-4">
                        <p className="font-semibold text-slate-900">
                          {t.nombre}
                        </p>

                        <p className="text-xs text-slate-500">
                          {t.conductor_id}
                        </p>
                      </td>

                      <td className="p-4 font-semibold text-violet-700">
                        {t.vehiculo_id}
                      </td>

                      <td className="p-4 capitalize">
                        {t.tipo_turno}
                      </td>

                      <td className="whitespace-nowrap p-4 font-medium">
                        {hora(t.inicio_local)}
                        {' – '}
                        {hora(t.fin_local)}
                      </td>

                      <td className="p-4">
                        {t.horas.toLocaleString('es-ES')} h
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {turnos.length === 0 && (
                <p className="p-6 text-sm text-slate-500">
                  No hay turnos que coincidan con la búsqueda.
                </p>
              )}
            </div>
          </div>

          <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
            {datos.advertencia}
          </p>
        </>
      )}
    </section>
  );
}
