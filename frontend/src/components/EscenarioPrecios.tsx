
"use client";

// FLOTIQ | ESCENARIOS ELECTRICOS PARA SEMANAS FUTURAS

import { useEffect, useState } from "react";

type PrecioHora = {
  fecha: string;
  precio_central_eur_mwh: number;
  precio_bajo_eur_mwh: number;
  precio_alto_eur_mwh: number;
  muestras_historicas: number;
};

type Escenario = {
  tipo_datos: string;
  metodo: string;
  semana_inicio: string;
  semana_fin: string;
  horas: number;
  precio_medio_escenario: number;
  aviso: string;
  registros: PrecioHora[];
};

type Props = {
  semana: string;
};

const numero = new Intl.NumberFormat("es-ES", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export default function EscenarioPrecios({ semana }: Props) {
  const [datos, setDatos] = useState<Escenario | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!semana) {
      return;
    }

    const controller = new AbortController();

    async function cargarEscenario() {
      setCargando(true);
      setError("");
      setDatos(null);

      try {
        const respuesta = await fetch(
          `/api/escenarios/precios?fecha=${semana}`,
          { signal: controller.signal }
        );

        if (!respuesta.ok) {
          throw new Error("No se pudo generar el escenario");
        }

        const resultado: Escenario = await respuesta.json();

        if (!Array.isArray(resultado.registros)) {
          throw new Error("Respuesta incorrecta de FastAPI");
        }

        setDatos(resultado);
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(
            err instanceof Error
              ? err.message
              : "Error de conexión"
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setCargando(false);
        }
      }
    }

    cargarEscenario();

    return () => controller.abort();
  }, [semana]);

  if (!semana) return null;

  if (cargando) {
    return (
      <div className="mt-8 rounded-3xl border border-gray-200 bg-white p-8">
        <p className="text-gray-500">
          Generando escenario eléctrico...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-8 rounded-3xl border border-red-200 bg-white p-8">
        <p className="text-red-600">{error}</p>
        <p className="mt-2 text-sm text-gray-500">
          Comprueba que FastAPI funciona en el puerto 8000.
        </p>
      </div>
    );
  }

  if (!datos) return null;

  const minimo = Math.min(
    ...datos.registros.map(
      (r) => r.precio_central_eur_mwh
    )
  );

  const maximo = Math.max(
    ...datos.registros.map(
      (r) => r.precio_central_eur_mwh
    )
  );

  const porDia = Array.from(
    Map.groupBy(
      datos.registros,
      (r) => r.fecha.slice(0, 10)
    )
  ).map(([fecha, horas]) => ({
    fecha,
    media:
      horas.reduce(
        (suma, h) => suma + h.precio_central_eur_mwh,
        0
      ) / horas.length,
  }));

  return (
    <section className="mt-8 rounded-3xl border border-gray-200 bg-white p-8 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8047F8]">
        Escenario energético
      </p>

      <h2 className="mt-3 text-2xl font-semibold">
        Precios estimados para la semana
      </h2>

      <p className="mt-3 text-sm text-gray-500">
        Perfil histórico por día y hora. No representa
        precios futuros conocidos.
      </p>

      <div className="mt-9 grid gap-4 sm:grid-cols-3">
        {[
          {
            titulo: "Precio central medio",
            valor: datos.precio_medio_escenario,
          },
          {
            titulo: "Mínimo del perfil central",
            valor: minimo,
          },
          {
            titulo: "Máximo del perfil central",
            valor: maximo,
          },
        ].map((indicador) => (
          <div
            key={indicador.titulo}
            className="rounded-2xl bg-[#FAFAFC] p-5"
          >
            <p className="text-xs text-gray-500">
              {indicador.titulo}
            </p>

            <p className="mt-3 text-2xl font-semibold">
              {numero.format(indicador.valor)}
              <span className="ml-2 text-xs font-normal text-gray-400">
                €/MWh
              </span>
            </p>
          </div>
        ))}
      </div>

      <div className="mt-10">
        <h3 className="font-semibold">
          Precio central medio por día
        </h3>

        <div className="mt-6 space-y-4">
          {porDia.map((dia) => (
            <div
              key={dia.fecha}
              className="flex items-center gap-4"
            >
              <span className="w-20 text-xs text-gray-500">
                {new Date(
                  `${dia.fecha}T12:00:00`
                ).toLocaleDateString("es-ES", {
                  weekday: "short",
                  day: "numeric",
                })}
              </span>

              <div className="h-4 flex-1 overflow-hidden rounded-full bg-[#F0F0F4]">
                <div
                  className="h-full rounded-full bg-[#8047F8]"
                  style={{
                    width: `${
                      maximo > 0
                        ? Math.max(
                            0,
                            (dia.media / maximo) * 100
                          )
                        : 0
                    }%`,
                  }}
                />
              </div>

              <span className="w-24 text-right text-xs font-medium">
                {numero.format(dia.media)} €
              </span>
            </div>
          ))}
        </div>
      </div>

      <p className="mt-8 text-xs leading-6 text-gray-500">
        {datos.aviso} El escenario contiene{" "}
        {datos.horas} intervalos horarios. Estos precios
        todavía no se han utilizado para optimizar recargas.
      </p>
    </section>
  );
}
