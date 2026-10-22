
"use client";

// FLOTIQ | PLANIFICACIÓN ENERGÉTICA SEMANAL

import { useState } from "react";
import Link from "next/link";
import EstadoFlota from "../../components/EstadoFlota";
import EscenarioPrecios from "@/components/EscenarioPrecios";

function fechaLocal(fecha: Date) {
  return (
    fecha.getFullYear() +
    "-" +
    String(fecha.getMonth() + 1).padStart(2, "0") +
    "-" +
    String(fecha.getDate()).padStart(2, "0")
  );
}

function inicioSemana(fecha: Date) {
  const lunes = new Date(fecha);
  const dia = (lunes.getDay() + 6) % 7;
  lunes.setDate(lunes.getDate() - dia);
  return lunes;
}

function sumarDias(fecha: Date, dias: number) {
  const resultado = new Date(fecha);
  resultado.setDate(resultado.getDate() + dias);
  return resultado;
}

function mostrarFecha(fecha: Date) {
  return fecha.toLocaleDateString("es-ES", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export default function PlanificacionPage() {
  const [fecha, setFecha] = useState("2026-11-23");

  const [planPreparado, setPlanPreparado] = useState(false);
  const [semanaEscenario, setSemanaEscenario] = useState("");

  const fechaSeleccionada = new Date(`${fecha}T12:00:00`);

  const lunes = inicioSemana(fechaSeleccionada);
  const domingo = sumarDias(lunes, 6);

  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);

  const semanaFutura = lunes.getTime() >=
    inicioSemana(hoy).getTime();

  return (
    <main className="min-h-screen bg-[#FAFAFC] text-[#111827]">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <Link href="/" className="text-2xl font-bold tracking-tight">
            Flot<span className="text-[#8047F8]">IQ</span>
          </Link>

          <Link
            href="/"
            className="text-sm text-gray-500 transition hover:text-[#8047F8]"
          >
            ← Volver al inicio
          </Link>
        </div>
      </header>

      <section className="mx-auto max-w-6xl px-6 py-14">
        <span className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8047F8]">
          Planificación energética
        </span>

        <h1 className="mt-4 text-4xl font-semibold tracking-tight md:text-5xl">
          Planifica las recargas
          <br />
          de tu flota.
        </h1>

        <p className="mt-5 max-w-2xl leading-7 text-gray-500">
          Selecciona una semana futura para preparar una
          planificación de recargas basada en previsiones del
          precio eléctrico y disponibilidad de vehículos.
        </p>

        <div className="mt-12 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <div className="rounded-3xl border border-gray-200 bg-white p-8 shadow-sm">
            <div className="flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#F2EBFF] text-xl">
                📅
              </span>

              <div>
                <h2 className="text-xl font-semibold">
                  Seleccionar semana
                </h2>
                <p className="text-sm text-gray-500">
                  Elige cualquier fecha de la semana.
                </p>
              </div>
            </div>

            <label
              htmlFor="fecha"
              className="mt-9 block text-sm font-medium text-gray-700"
            >
              Fecha de referencia
            </label>

            <input
              id="fecha"
              type="date"
              value={fecha}
              min={fechaLocal(hoy)}
              onChange={(e) => {
                setFecha(e.target.value);
                setPlanPreparado(false);
              }}
              className="mt-3 w-full rounded-xl border border-gray-200 bg-white px-4 py-4 text-base outline-none transition focus:border-[#8047F8]"
            />

            <div className="mt-7 rounded-2xl bg-[#F7F5FC] p-6">
              <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
                Semana seleccionada
              </p>

              <p className="mt-3 text-lg font-semibold">
                {mostrarFecha(lunes)}
              </p>

              <p className="mt-1 text-gray-500">
                al {mostrarFecha(domingo)}
              </p>

              <p className="mt-4 text-xs text-gray-500">
                Horizonte de planificación: 7 días
              </p>
            </div>

            <button
              type="button"
              disabled={!fecha || !semanaFutura}
              onClick={() => {
                setPlanPreparado(true);
                setSemanaEscenario(fechaLocal(lunes));
                }}
              className="mt-7 w-full rounded-xl bg-[#8047F8] px-6 py-4 font-semibold text-white transition hover:bg-[#6B2DFF] disabled:cursor-not-allowed disabled:opacity-40"
            >
              Preparar planificación →
            </button>

            {!semanaFutura && (
              <p className="mt-3 text-sm text-red-600">
                Selecciona una semana actual o futura.
              </p>
            )}
          </div>

          <div className="rounded-3xl border border-gray-200 bg-white p-8 shadow-sm">
            <div className="mt-8">
                <EstadoFlota />
            </div>

            <p className="mt-2 text-sm text-gray-500">
              Configuración utilizada en nuestros
              experimentos de FlotIQ.
            </p>

            <div className="mt-8 space-y-6">
              {[
                ["Vehículos eléctricos", "50"],
                ["Conductores", "80"],
                ["Cargadores disponibles", "20"],
                ["Potencia de instalación", "150 kW"],
                ["Capacidad de batería", "60 kWh"],
              ].map(([nombre, valor]) => (
                <div
                  key={nombre}
                  className="flex items-center justify-between border-b border-gray-100 pb-4"
                >
                  <span className="text-sm text-gray-500">
                    {nombre}
                  </span>

                  <span className="font-semibold">
                    {valor}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {planPreparado && semanaFutura && (
          <section className="mt-8 rounded-3xl border border-[#DACBFF] bg-white p-8">
            <p className="text-sm font-semibold text-[#8047F8]">
              Semana configurada
            </p>

            <h2 className="mt-2 text-2xl font-semibold">
              Planificación preparada
            </h2>

                {planPreparado && semanaFutura && (
                <EscenarioPrecios semana={semanaEscenario} />
                )}

            <p className="mt-3 leading-7 text-gray-500">
              Hemos seleccionado la semana del{" "}
              {mostrarFecha(lunes)} al{" "}
              {mostrarFecha(domingo)}.
              El siguiente paso será conectar esta selección
              con el motor Python para generar previsiones
              eléctricas y optimizar las recargas.
            </p>

            <p className="mt-4 text-sm text-gray-500">
              Todavía no se han calculado predicciones,
              costes ni horarios de carga.
            </p>
          </section>
        )}
      </section>
    </main>
  );
}
