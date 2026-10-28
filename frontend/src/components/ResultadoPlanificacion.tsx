
"use client";

// FLOTIQ | RESULTADOS DE PLANIFICACION SEMANAL

import { useEffect, useState } from "react";

type Dia = {
  dia: string;
  estado: string;
  optimalidad_certificada: boolean;
  coste_estimado_eur: number;
  energia_total_kwh: number;
};

type Planificacion = {
  tipo_datos: string;
  metodo_precios: string;
  semana_inicio: string;
  vehiculos: number;
  horas: number;
  energia_total_kwh: number;
  coste_estimado_eur: number;
  factibilidad_validada: boolean;
  optimalidad_semanal_certificada: boolean;
  dias: Dia[];
  advertencia: string;
};

type Props = {
  semana: string;
};

const numero = new Intl.NumberFormat("es-ES", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export default function ResultadoPlanificacion({
  semana,
}: Props) {
  const [datos, setDatos] = useState<Planificacion | null>(null);
  const [cargando, setCargando] = useState(false);
  const [mensaje, setMensaje] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!semana) return;

    const controller = new AbortController();

    async function consultar() {
      setCargando(true);
      setDatos(null);
      setMensaje("");
      setError("");

      try {
        const respuesta = await fetch(
          `/api/planificaciones/${semana}/resumen`,
          { signal: controller.signal }
        );

        if (respuesta.status === 404) {
          setMensaje(
            "Esta semana todavía no tiene una planificación de recargas generada."
          );
          return;
        }

        if (!respuesta.ok) {
          throw new Error("No se pudo consultar la planificación");
        }

        const resultado: Planificacion =
          await respuesta.json();

        if (
          !resultado.factibilidad_validada ||
          !Array.isArray(resultado.dias)
        ) {
          throw new Error(
            "La planificación no está validada."
          );
        }

        setDatos(resultado);
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(
            err instanceof Error
              ? err.message
              : "Error desconocido"
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setCargando(false);
        }
      }
    }

    consultar();

    return () => controller.abort();
  }, [semana]);

  if (!semana) return null;

  if (cargando) {
    return (
      <div className="mt-8 rounded-3xl border border-gray-200 bg-white p-8">
        <p className="text-gray-500">
          Consultando planificación de recargas...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-8 rounded-3xl border border-red-200 bg-white p-8">
        <p className="font-medium text-red-600">
          {error}
        </p>
      </div>
    );
  }

  if (mensaje) {
    return (
      <div className="mt-8 rounded-3xl border border-gray-200 bg-white p-8">
        <h2 className="text-xl font-semibold">
          Planificación de recargas
        </h2>
        <p className="mt-3 text-sm text-gray-500">
          {mensaje}
        </p>
        <p className="mt-2 text-xs text-gray-400">
          Actualmente puedes consultar los precios
          estimados de esta semana.
        </p>
      </div>
    );
  }

  if (!datos) return null;

  const costeMaximo = Math.max(
    ...datos.dias.map((d) => d.coste_estimado_eur),
    1
  );

  return (
    <section className="mt-8 rounded-3xl border border-gray-200 bg-white p-8 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8047F8]">
        Optimización energética
      </p>

      <h2 className="mt-3 text-2xl font-semibold">
        Planificación semanal de recargas
      </h2>

      <p className="mt-3 text-sm text-gray-500">
        Semana del {datos.semana_inicio}.
        Resultados de una simulación operativa futura.
      </p>

      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        <div className="rounded-2xl bg-[#FAFAFC] p-5">
          <p className="text-xs text-gray-500">
            Coste semanal estimado
          </p>
          <p className="mt-3 text-3xl font-semibold">
            {numero.format(datos.coste_estimado_eur)} €
          </p>
        </div>

        <div className="rounded-2xl bg-[#FAFAFC] p-5">
          <p className="text-xs text-gray-500">
            Energía adquirida
          </p>
          <p className="mt-3 text-3xl font-semibold">
            {numero.format(datos.energia_total_kwh)}
            <span className="ml-2 text-sm font-normal text-gray-400">
              kWh
            </span>
          </p>
        </div>

        <div className="rounded-2xl bg-[#FAFAFC] p-5">
          <p className="text-xs text-gray-500">
            Vehículos planificados
          </p>
          <p className="mt-3 text-3xl font-semibold">
            {datos.vehiculos}
          </p>
        </div>
      </div>

      <div className="mt-7 flex flex-wrap gap-3 text-xs">
        <span className="rounded-full bg-green-50 px-4 py-2 font-medium text-green-700">
          Factibilidad validada
        </span>

        <span className="rounded-full bg-gray-100 px-4 py-2 text-gray-600">
          {datos.optimalidad_semanal_certificada
            ? "Optimalidad certificada"
            : "Optimalidad no certificada"}
        </span>
      </div>

      <div className="mt-10">
        <h3 className="text-lg font-semibold">
          Coste diario de recargas
        </h3>

        <div className="mt-6 space-y-5">
          {datos.dias.map((dia) => {
            const porcentaje =
              (dia.coste_estimado_eur / costeMaximo) * 100;

            const etiqueta = new Date(
              `${dia.dia}T12:00:00`
            ).toLocaleDateString("es-ES", {
              weekday: "short",
              day: "numeric",
            });

            return (
              <div key={dia.dia}>
                <div className="mb-2 flex justify-between gap-3 text-sm">
                  <span className="text-gray-600">
                    {etiqueta}
                  </span>
                  <span className="font-semibold">
                    {numero.format(dia.coste_estimado_eur)} €
                  </span>
                </div>

                <div className="h-3 overflow-hidden rounded-full bg-[#F0F0F4]">
                  <div
                    className="h-full rounded-full bg-[#8047F8]"
                    style={{
                      width: `${porcentaje}%`,
                    }}
                  />
                </div>

                <p className="mt-1 text-xs text-gray-400">
                  {numero.format(dia.energia_total_kwh)} kWh
                  · CBC: {dia.estado}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-10 border-t border-gray-100 pt-6">
        <p className="text-xs leading-6 text-gray-500">
          {datos.advertencia}
        </p>
      </div>
    </section>
  );
}
