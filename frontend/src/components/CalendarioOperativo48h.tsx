
'use client';

import { useEffect, useState } from 'react';

type Estado = 'cargando' | 'trabajando' | 'disponible';

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
  fecha_consulta: string;
  dias: string[];
  vehiculos: string[];
  cargadores: string[];
  registros: Registro[];
  advertencia: string;
};

type Tramo = {
  estado: 'cargando' | 'trabajando';
  cargador_id: string | null;
  inicio: string;
  ultimaHora: string;
  fin: string;
  energia: number;
};

function mostrarHora(fecha: string) {
  return new Date(fecha).toLocaleTimeString('es-ES', {
    timeZone: 'Europe/Madrid',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  });
}

function sumarHora(fecha: string) {
  return new Date(
    new Date(fecha).getTime() + 3600000
  ).toISOString();
}

function agruparTramos(registros: Registro[]): Tramo[] {
  const tramos: Tramo[] = [];

  const ordenados = [...registros].sort(
    (a, b) =>
      new Date(a.fecha_local).getTime() -
      new Date(b.fecha_local).getTime()
  );

  for (const registro of ordenados) {
    if (registro.estado === 'disponible') continue;

    const anterior = tramos[tramos.length - 1];

    const consecutivo =
      anterior &&
      anterior.estado === registro.estado &&
      anterior.cargador_id === registro.cargador_id &&
      new Date(registro.fecha_local).getTime() -
        new Date(anterior.ultimaHora).getTime() === 3600000;

    if (consecutivo) {
      anterior.ultimaHora = registro.fecha_local;
      anterior.fin = sumarHora(registro.fecha_local);
      anterior.energia += registro.energia_red_kwh;
    } else {
      tramos.push({
        estado: registro.estado,
        cargador_id: registro.cargador_id,
        inicio: registro.fecha_local,
        ultimaHora: registro.fecha_local,
        fin: sumarHora(registro.fecha_local),
        energia: registro.energia_red_kwh,
      });
    }
  }

  return tramos;
}

export default function CalendarioOperativo48h({
  fechaConsulta,
}: {
  fechaConsulta: string;
}) {
  const [datos, setDatos] = useState<Calendario | null>(null);
  const [dia, setDia] = useState('');
  const [vehiculo, setVehiculo] = useState('V001');
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const control = new AbortController();

    setCargando(true);
    setError('');
    setDatos(null);

    fetch(
      `/api/48h/${fechaConsulta}/calendario`,
      { signal: control.signal }
    )
      .then(async (respuesta) => {
        if (!respuesta.ok) {
          throw new Error(`Error HTTP ${respuesta.status}`);
        }

        return (await respuesta.json()) as Calendario;
      })
      .then((resultado) => {
        if (control.signal.aborted) return;

        setDatos(resultado);
        setDia(resultado.dias[0] || '');
        setVehiculo(resultado.vehiculos[0] || 'V001');
      })
      .catch((fallo: unknown) => {
        if (control.signal.aborted) return;

        setError(
          fallo instanceof Error
            ? fallo.message
            : 'No se pudo cargar el calendario.'
        );
      })
      .finally(() => {
        if (!control.signal.aborted) {
          setCargando(false);
        }
      });

    return () => control.abort();
  }, [fechaConsulta]);

  if (cargando) {
    return (
      <section className="rounded-3xl bg-white p-6 text-gray-500">
        Cargando calendario operativo...
      </section>
    );
  }

  if (error || !datos) {
    return (
      <section className="rounded-3xl bg-red-50 p-6 text-red-700">
        No se pudo cargar el calendario: {error}
      </section>
    );
  }

  const registrosDia = datos.registros.filter(
    (registro) => registro.fecha_local.slice(0, 10) === dia
  );

  const horas = Array.from(
    new Set(registrosDia.map((registro) => registro.fecha_local))
  ).sort(
    (a, b) => new Date(a).getTime() - new Date(b).getTime()
  );

  const porVehiculo = new Map(
    registrosDia.map((registro) => [
      `${registro.vehicle_id}|${registro.fecha_local}`,
      registro,
    ])
  );

  const porCargador = new Map(
    registrosDia
      .filter((registro) => registro.cargador_id !== null)
      .map((registro) => [
        `${registro.cargador_id}|${registro.fecha_local}`,
        registro,
      ])
  );

  const agenda = agruparTramos(
    registrosDia.filter(
      (registro) => registro.vehicle_id === vehiculo
    )
  );

  return (
    <section className="space-y-6 rounded-3xl border border-gray-200 bg-white p-6 shadow-sm">
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-[#8047F8]">
          Operativa de la flota
        </p>

        <h2 className="mt-2 text-2xl font-semibold">
          Turnos y asignación de cargadores
        </h2>

        <p className="mt-2 text-sm text-gray-500">
          Consulta qué vehículo trabaja, cuándo debe recargar
          y qué cargador tiene asignado.
        </p>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-wrap gap-2">
          {datos.dias.map((fecha) => (
            <button
              key={fecha}
              type="button"
              onClick={() => setDia(fecha)}
              className={
                dia === fecha
                  ? 'rounded-xl bg-[#8047F8] px-5 py-3 text-sm font-semibold text-white'
                  : 'rounded-xl border border-gray-200 px-5 py-3 text-sm text-gray-600'
              }
            >
              {fecha}
            </button>
          ))}
        </div>

        <label className="text-sm font-medium">
          Seleccionar vehículo

          <select
            value={vehiculo}
            onChange={(evento) => setVehiculo(evento.target.value)}
            className="mt-2 block rounded-xl border border-gray-200 bg-white px-4 py-3"
          >
            {datos.vehiculos.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex flex-wrap gap-5 text-sm">
        <span className="flex items-center gap-2">
          <span className="h-3 w-3 rounded bg-violet-600" />
          Recargando
        </span>

        <span className="flex items-center gap-2">
          <span className="h-3 w-3 rounded bg-amber-300" />
          Trabajando (estimado)
        </span>

        <span className="flex items-center gap-2">
          <span className="h-3 w-3 rounded bg-gray-200" />
          Disponible
        </span>
      </div>

      <div className="rounded-2xl border border-purple-100 bg-purple-50 p-5">
        <h3 className="font-semibold text-[#7541DC]">
          Agenda del vehículo {vehiculo}
        </h3>

        {agenda.length === 0 ? (
          <p className="mt-3 text-sm text-gray-600">
            Sin trabajo ni recargas previstas este día.
          </p>
        ) : (
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {agenda.map((tramo, indice) => (
              <div
                key={`${tramo.inicio}-${indice}`}
                className="rounded-xl border border-purple-100 bg-white p-4"
              >
                <p className="text-sm font-semibold">
                  {tramo.estado === 'cargando'
                    ? `Recarga · ${tramo.cargador_id}`
                    : 'Trabajando · turno estimado'}
                </p>

                <p className="mt-2 text-lg font-semibold">
                  {mostrarHora(tramo.inicio)}
                  {' – '}
                  {mostrarHora(tramo.fin)}
                </p>

                {tramo.estado === 'cargando' && (
                  <p className="mt-1 text-sm text-gray-500">
                    {tramo.energia.toFixed(2)} kWh de red
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-lg font-semibold">
          ¿Qué vehículo utiliza cada cargador?
        </h3>

        <p className="mb-4 text-sm text-gray-500">
          Cada casilla indica el vehículo asignado a ese cargador
          durante la hora correspondiente.
        </p>

        <div className="max-h-[540px] overflow-auto rounded-xl border border-gray-200">
          <table className="border-collapse text-center text-xs">
            <thead className="sticky top-0 z-10 bg-gray-100">
              <tr>
                <th className="sticky left-0 z-20 min-w-[100px] bg-gray-100 p-3">
                  Cargador
                </th>

                {horas.map((hora) => (
                  <th
                    key={hora}
                    className="min-w-[72px] border-l border-gray-200 p-2"
                  >
                    {mostrarHora(hora)}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {datos.cargadores.map((cargador) => (
                <tr key={cargador} className="border-t border-gray-100">
                  <th className="sticky left-0 bg-white p-3 font-semibold">
                    {cargador}
                  </th>

                  {horas.map((hora) => {
                    const registro = porCargador.get(
                      `${cargador}|${hora}`
                    );

                    return (
                      <td
                        key={hora}
                        className="border-l border-gray-100 p-1"
                        title={
                          registro
                            ? `${registro.vehicle_id} · ${mostrarHora(hora)} · ${registro.energia_red_kwh} kWh`
                            : 'Libre'
                        }
                      >
                        <span
                          className={
                            registro
                              ? 'block rounded-md bg-violet-100 px-2 py-3 font-semibold text-violet-800'
                              : 'block px-2 py-3 text-gray-300'
                          }
                        >
                          {registro?.vehicle_id || '·'}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-lg font-semibold">
          Horario de los 50 vehículos
        </h3>

        <p className="mb-4 text-sm text-gray-500">
          C01–C20 indica recarga, T significa trabajo estimado
          y el punto indica disponibilidad. Selecciona un vehículo
          para ver sus horas exactas arriba.
        </p>

        <div className="max-h-[600px] overflow-auto rounded-xl border border-gray-200">
          <table className="border-collapse text-center text-xs">
            <thead className="sticky top-0 z-10 bg-gray-100">
              <tr>
                <th className="sticky left-0 z-20 min-w-[100px] bg-gray-100 p-3">
                  Vehículo
                </th>

                {horas.map((hora) => (
                  <th
                    key={hora}
                    className="min-w-[72px] border-l border-gray-200 p-2"
                  >
                    {mostrarHora(hora)}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {datos.vehiculos.map((id) => (
                <tr
                  key={id}
                  className="border-t border-gray-100"
                >
                  <th className="sticky left-0 bg-white p-2">
                    <button
                      type="button"
                      onClick={() => setVehiculo(id)}
                      className={
                        id === vehiculo
                          ? 'font-bold text-violet-700'
                          : 'font-medium text-gray-700'
                      }
                    >
                      {id}
                    </button>
                  </th>

                  {horas.map((hora) => {
                    const registro = porVehiculo.get(`${id}|${hora}`);

                    const estilo =
                      registro?.estado === 'cargando'
                        ? 'bg-violet-600 text-white'
                        : registro?.estado === 'trabajando'
                          ? 'bg-amber-200 text-amber-900'
                          : 'bg-gray-100 text-gray-400';

                    const texto =
                      registro?.estado === 'cargando'
                        ? registro.cargador_id
                        : registro?.estado === 'trabajando'
                          ? 'T'
                          : '·';

                    return (
                      <td
                        key={hora}
                        className="border-l border-gray-100 p-1"
                        title={
                          `${id} · ${mostrarHora(hora)} · ` +
                          `${registro?.estado || 'Sin datos'} · ` +
                          `SOC ${registro?.soc_pct ?? '-'} %`
                        }
                      >
                        <span
                          className={`block rounded-md px-2 py-3 font-semibold ${estilo}`}
                        >
                          {texto}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-xs leading-5 text-gray-500">
        {datos.advertencia}
      </p>
    </section>
  );
}
