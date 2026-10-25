
'use client';

import { useMemo, useState } from 'react';

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

type Punto = {
  fecha: string;
  valor: number;
};

function numero(valor: number, decimales = 2) {
  return valor.toLocaleString('es-ES', {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  });
}

function fechaHora(fecha: string) {
  return new Date(fecha).toLocaleString('es-ES', {
    timeZone: 'Europe/Madrid',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  });
}

function soloHora(fecha: string) {
  return new Date(fecha).toLocaleTimeString('es-ES', {
    timeZone: 'Europe/Madrid',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  });
}

function GraficoDetallado({
  titulo,
  descripcion,
  puntos,
  unidad,
  color,
  limite,
}: {
  titulo: string;
  descripcion: string;
  puntos: Punto[];
  unidad: string;
  color: string;
  limite?: number;
}) {
  const [seleccionado, setSeleccionado] = useState<number | null>(null);

  if (!puntos.length) return null;

  const valores = puntos.map((p) => p.valor);

  const minimoDatos = Math.min(...valores);
  const maximoDatos = Math.max(...valores);
  const media =
    valores.reduce((s, v) => s + v, 0) / valores.length;

  const minEscala = Math.min(0, minimoDatos);
  const maxEscala = limite || Math.max(1, maximoDatos * 1.1);
  const rango = Math.max(1, maxEscala - minEscala);

  const x = (i: number) =>
    65 + (i * 770) / Math.max(1, puntos.length - 1);

  const y = (valor: number) =>
    210 - ((valor - minEscala) / rango) * 180;

  const camino = puntos.map((p, i) =>
    `${i === 0 ? 'M' : 'L'}${x(i)},${y(p.valor)}`
  ).join(' ');

  const paso = puntos.length > 30 ? 6 : 4;

  const indice = seleccionado !== null &&
    seleccionado < puntos.length
      ? seleccionado
      : null;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="text-lg font-bold">{titulo}</h3>

      <p className="mt-1 min-h-10 text-sm leading-6 text-slate-500">
        {descripcion}
      </p>

      <div className="mt-4 grid grid-cols-3 gap-2">
        {[
          ['Mínimo', minimoDatos],
          ['Media', media],
          ['Máximo', maximoDatos],
        ].map(([etiqueta, valor]) => (
          <div
            key={String(etiqueta)}
            className="rounded-xl bg-slate-50 p-3"
          >
            <p className="text-xs text-slate-500">
              {etiqueta}
            </p>

            <p className="mt-1 text-sm font-bold">
              {numero(Number(valor))} {unidad}
            </p>
          </div>
        ))}
      </div>

      <div className="mt-5">
        <svg
          viewBox="0 0 880 270"
          className="w-full"
          role="img"
          aria-label={titulo}
        >
          {[0, 0.25, 0.5, 0.75, 1].map((f) => {
            const valor =
              minEscala + (maxEscala - minEscala) * f;

            return (
              <g key={f}>
                <line
                  x1="65"
                  x2="835"
                  y1={y(valor)}
                  y2={y(valor)}
                  stroke="#E2E8F0"
                  strokeDasharray="5 5"
                />

                <text
                  x="55"
                  y={y(valor) + 4}
                  textAnchor="end"
                  fill="#64748B"
                  fontSize="12"
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
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {puntos.map((p, i) => (
            <g key={`${p.fecha}-${i}`}>
              <circle
                cx={x(i)}
                cy={y(p.valor)}
                r={i === indice ? 6 : 3.5}
                fill={color}
                stroke="white"
                strokeWidth="1"
                onMouseEnter={() => setSeleccionado(i)}
                onMouseLeave={() => setSeleccionado(null)}
                onFocus={() => setSeleccionado(i)}
                onBlur={() => setSeleccionado(null)}
                tabIndex={0}
                role="graphics-symbol"
                aria-label={
                  `${fechaHora(p.fecha)}: ` +
                  `${numero(p.valor)} ${unidad}`
                }
              >
                <title>
                  {fechaHora(p.fecha)}: {numero(p.valor)} {unidad}
                </title>
              </circle>

              {i % paso === 0 && (
                <text
                  x={x(i)}
                  y="241"
                  textAnchor="middle"
                  fill="#64748B"
                  fontSize="11"
                >
                  {soloHora(p.fecha)}
                </text>
              )}
            </g>
          ))}
        </svg>
      </div>

      <div className="mt-2 rounded-xl bg-slate-50 p-3 text-sm text-slate-600">
        {indice === null ? (
          'Pasa el ratón por los puntos para consultar el valor de cada hora.'
        ) : (
          <span>
            <strong>{fechaHora(puntos[indice].fecha)}</strong>
            {' · '}
            {numero(puntos[indice].valor)} {unidad}
          </span>
        )}
      </div>
    </section>
  );
}

export default function GraficosEnergia48h({
  precios,
  flota,
}: {
  precios: Precio[];
  flota: HoraFlota[];
}) {
  const [dia, setDia] = useState('todos');

  const dias = useMemo(
    () => [
      ...new Set(
        precios.map((p) => p.fecha_local.slice(0, 10))
      ),
    ],
    [precios]
  );

  const preciosVisibles = precios.filter(
    (p) => dia === 'todos' ||
      p.fecha_local.slice(0, 10) === dia
  );

  const flotaVisible = flota.filter(
    (p) => dia === 'todos' ||
      p.fecha_local.slice(0, 10) === dia
  );

  const baratas = [...preciosVisibles]
    .sort(
      (a, b) =>
        a.precio_predicho_eur_mwh -
        b.precio_predicho_eur_mwh
    )
    .slice(0, 5);

  const energiaTotal = flotaVisible.reduce(
    (s, p) => s + p.energia_red_kwh,
    0
  );

  const costeTotal = flotaVisible.reduce(
    (s, p) => s + p.coste_estimado_eur,
    0
  );

  return (
    <div className="mt-6 space-y-6">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-violet-600">
          Inteligencia energética
        </p>

        <h2 className="mt-2 text-2xl font-bold">
          Precios y energía
        </h2>

        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
          Analiza cómo cambian los precios previstos, cuándo
          se programan las recargas y cómo evolucionan las
          baterías de la flota.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setDia('todos')}
          className={
            dia === 'todos'
              ? 'rounded-xl bg-violet-600 px-4 py-2 text-sm font-semibold text-white'
              : 'rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm'
          }
        >
          Ver las 48 horas
        </button>

        {dias.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setDia(d)}
            className={
              dia === d
                ? 'rounded-xl bg-violet-600 px-4 py-2 text-sm font-semibold text-white'
                : 'rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm'
            }
          >
            {d}
          </button>
        ))}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <p className="text-xs uppercase text-slate-500">
            Energía planificada
          </p>

          <p className="mt-2 text-2xl font-bold">
            {numero(energiaTotal)} kWh
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <p className="text-xs uppercase text-slate-500">
            Coste estimado de las recargas
          </p>

          <p className="mt-2 text-2xl font-bold">
            {numero(costeTotal)} €
          </p>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <GraficoDetallado
          titulo="1. Precio eléctrico previsto"
          descripcion="Precio estimado por el modelo ML para cada hora. Cuanto más bajo sea, más barata podría resultar la recarga."
          unidad="€/MWh"
          color="#7C3AED"
          puntos={preciosVisibles.map((p) => ({
            fecha: p.fecha_local,
            valor: p.precio_predicho_eur_mwh,
          }))}
        />

        <GraficoDetallado
          titulo="2. Electricidad utilizada en las recargas"
          descripcion="Energía de red que el optimizador propone utilizar cada hora. Los picos muestran cuándo concentra las recargas."
          unidad="kWh"
          color="#059669"
          puntos={flotaVisible.map((p) => ({
            fecha: p.fecha_local,
            valor: p.energia_red_kwh,
          }))}
        />

        <GraficoDetallado
          titulo="3. Batería media de la flota"
          descripcion="Porcentaje medio de batería estimada. Desciende durante el trabajo y aumenta cuando se recarga."
          unidad="%"
          color="#D97706"
          limite={100}
          puntos={flotaVisible.map((p) => ({
            fecha: p.fecha_local,
            valor: p.soc_medio_pct,
          }))}
        />

        <GraficoDetallado
          titulo="4. Cargadores con recarga activa"
          descripcion="Número de vehículos cargando simultáneamente. El máximo disponible en FLOTIQ es de 20 puestos."
          unidad="vehículos"
          color="#2563EB"
          limite={20}
          puntos={flotaVisible.map((p) => ({
            fecha: p.fecha_local,
            valor: p.cargadores_ocupados,
          }))}
        />
      </div>

      <section className="rounded-2xl border border-emerald-200 bg-white p-6">
        <h3 className="text-lg font-bold">
          ¿Cuáles son las horas con electricidad prevista más barata?
        </h3>

        <p className="mt-2 text-sm text-slate-500">
          Estas son las cinco horas con menor precio previsto
          del periodo seleccionado. No siempre se puede cargar
          en ellas: también influyen los turnos, la batería
          disponible y la capacidad de los cargadores.
        </p>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {baratas.map((p) => (
            <div
              key={p.fecha_local}
              className="rounded-xl bg-emerald-50 p-4"
            >
              <p className="text-xs text-emerald-800">
                {fechaHora(p.fecha_local)}
              </p>

              <p className="mt-2 text-lg font-bold text-emerald-900">
                {numero(p.precio_predicho_eur_mwh)}
              </p>

              <p className="text-xs text-emerald-800">
                €/MWh
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-violet-200 bg-violet-50 p-6">
        <p className="text-xs font-bold uppercase tracking-widest text-violet-700">
          Así funciona nuestro Machine Learning
        </p>

        <h3 className="mt-2 text-xl font-bold text-violet-950">
          ¿Cómo predice FLOTIQ los precios eléctricos?
        </h3>

        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <div className="rounded-xl bg-white p-5">
            <span className="text-xs font-bold text-violet-700">
              PASO 1
            </span>

            <h4 className="mt-2 font-bold">
              Aprendemos del histórico de OMIE
            </h4>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Utilizamos precios históricos del mercado
              eléctrico español. Los datos de 15 minutos
              se agregan a frecuencia horaria para que
              coincidan con el modelo.
            </p>
          </div>

          <div className="rounded-xl bg-white p-5">
            <span className="text-xs font-bold text-violet-700">
              PASO 2
            </span>

            <h4 className="mt-2 font-bold">
              Identificamos patrones
            </h4>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Un HistGradientBoostingRegressor aprende
              relaciones entre el precio y la hora,
              el día de la semana, el mes y precios
              anteriores.
            </p>
          </div>

          <div className="rounded-xl bg-white p-5">
            <span className="text-xs font-bold text-violet-700">
              PASO 3
            </span>

            <h4 className="mt-2 font-bold">
              Predecimos y optimizamos
            </h4>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Generamos un precio estimado para cada hora
              de los próximos dos días. PuLP utiliza
              esos precios y las restricciones de la
              flota para proponer las recargas.
            </p>
          </div>
        </div>

        <details className="mt-5 rounded-xl border border-violet-200 bg-white p-5">
          <summary className="cursor-pointer font-semibold text-violet-900">
            Ver qué variables utiliza exactamente el modelo
          </summary>

          <div className="mt-4 text-sm leading-7 text-slate-600">
            <p>
              Nuestro modelo utiliza ocho variables:
            </p>

            <ul className="mt-2 list-disc pl-5">
              <li>Hora del día: componentes seno y coseno.</li>
              <li>Mes del año: componentes seno y coseno.</li>
              <li>Día de la semana.</li>
              <li>Indicador de fin de semana.</li>
              <li>Precio registrado 72 horas antes.</li>
              <li>Precio registrado 168 horas antes.</li>
            </ul>

            <p className="mt-3">
              Las transformaciones seno y coseno permiten
              representar ciclos: por ejemplo, que las 23:00
              y las 00:00 son horas próximas.
            </p>
          </div>
        </details>

        <p className="mt-5 text-sm leading-6 text-violet-900">
          <strong>Importante:</strong> el ML genera estimaciones,
          no precios garantizados. En las pruebas históricas,
          el modelo todavía no demostró superar al método
          base de repetir el precio de la semana anterior.
          Por eso FLOTIQ no presenta estos resultados como
          ahorros reales demostrados.
        </p>
      </section>
    </div>
  );
}
