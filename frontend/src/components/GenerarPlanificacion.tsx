
"use client";

// FLOTIQ | GENERACION AUTOMATICA DE PLANIFICACIONES

import { useEffect, useState } from "react";
import ResultadoPlanificacion from "./ResultadoPlanificacion";

type Estado =
  | "pendiente"
  | "ejecutando"
  | "completada"
  | "error";

type RespuestaEstado = {
  semana: string;
  estado: Estado;
  error: string | null;
};

const API = "http://127.0.0.1:8000";

export default function GenerarPlanificacion({
  semana,
}: {
  semana: string;
}) {
  const [estado, setEstado] = useState<Estado>("pendiente");
  const [mensaje, setMensaje] = useState("");
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (!semana) return;

    let cancelado = false;

    async function consultarEstado() {
      try {
        const respuesta = await fetch(
          `${API}/api/planificaciones/${semana}/estado`,
          { cache: "no-store" }
        );

        if (!respuesta.ok) {
          throw new Error("No se pudo consultar el estado.");
        }

        const datos: RespuestaEstado = await respuesta.json();

        if (cancelado) return;

        setEstado((anterior) => {
          if (
            datos.estado === "completada" &&
            anterior !== "completada"
          ) {
            setRevision((actual) => actual + 1);
          }

          return datos.estado;
        });

        setError(datos.error ?? "");

      } catch (err) {
        if (!cancelado) {
          setError(
            err instanceof Error
              ? err.message
              : "Error al conectar con FastAPI."
          );
        }
      }
    }

    setEstado("pendiente");
    setMensaje("");
    setError("");
    setRevision(0);

    consultarEstado();

    const intervalo = setInterval(consultarEstado, 5000);

    return () => {
      cancelado = true;
      clearInterval(intervalo);
    };
  }, [semana]);

  async function generar() {
    setEstado("ejecutando");
    setMensaje("Iniciando optimización semanal...");
    setError("");

    try {
      const respuesta = await fetch(
        `${API}/api/planificaciones/generar`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ semana }),
        }
      );

      const datos = await respuesta.json();

      if (!respuesta.ok) {
        throw new Error(
          typeof datos.detail === "string"
            ? datos.detail
            : "No se pudo iniciar la planificación."
        );
      }

      setEstado(datos.estado);
      setMensaje(datos.mensaje ?? "");

      if (datos.estado === "completada") {
        setRevision((actual) => actual + 1);
      }

    } catch (err) {
      setEstado("error");
      setError(
        err instanceof Error
          ? err.message
          : "Error de conexión."
      );
    }
  }

  return (
    <div className="mt-8 space-y-6">
      {estado === "pendiente" && (
        <div className="rounded-3xl border border-gray-200 bg-white p-8">
          <h2 className="text-xl font-semibold">
            Planificación pendiente
          </h2>

          <p className="mt-3 text-sm text-gray-500">
            Todavía no existe un calendario de recargas
            calculado para la semana del {semana}.
          </p>

          <button
            onClick={generar}
            className="mt-6 rounded-xl bg-[#8047F8] px-6 py-3 font-medium text-white hover:bg-[#6B35DF]"
          >
            Generar planificación semanal
          </button>
        </div>
      )}

      {estado === "ejecutando" && (
        <div className="rounded-3xl border border-[#E2D5FF] bg-white p-8">
          <div className="flex items-center gap-3">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-[#8047F8] border-t-transparent" />

            <h2 className="text-xl font-semibold">
              Optimizando los 50 Tesla
            </h2>
          </div>

          <p className="mt-4 text-sm text-gray-500">
            FlotIQ está calculando las recargas,
            comprobando los límites energéticos y
            asignando los cargadores.
          </p>

          <p className="mt-2 text-xs text-gray-400">
            Consultando el estado automáticamente.
            No cierres el servidor FastAPI durante el cálculo.
          </p>

          {mensaje && (
            <p className="mt-4 text-sm text-[#8047F8]">
              {mensaje}
            </p>
          )}
        </div>
      )}

      {estado === "completada" && (
        <ResultadoPlanificacion
          key={`${semana}-${revision}`}
          semana={semana}
        />
      )}

      {estado === "error" && (
        <div className="rounded-3xl border border-red-200 bg-white p-8">
          <h2 className="text-xl font-semibold text-red-700">
            No se ha podido completar la planificación
          </h2>

          <p className="mt-3 text-sm text-gray-600">
            {error || "Se ha producido un error."}
          </p>

          <button
            onClick={generar}
            className="mt-6 rounded-xl bg-[#8047F8] px-6 py-3 font-medium text-white"
          >
            Reintentar
          </button>
        </div>
      )}
    </div>
  );
}
