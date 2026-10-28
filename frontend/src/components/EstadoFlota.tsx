
"use client";

// FLOTIQ | CONEXIÓN DE REACT CON FASTAPI

import { useEffect, useState } from "react";

type ConfiguracionFlota = {
  vehiculos: number;
  conductores: number;
  cargadores: number;
  potencia_maxima_kw: number;
  capacidad_bateria_kwh: number;
  tipo_datos: string;
};

export default function EstadoFlota() {
  const [flota, setFlota] = useState<ConfiguracionFlota | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function cargarFlota() {
      try {
        const respuesta = await fetch(
          "/api/flota"
        );

        if (!respuesta.ok) {
          throw new Error("La API no ha respondido correctamente");
        }

        const datos: ConfiguracionFlota = await respuesta.json();
        setFlota(datos);
      } catch {
        setError(
          "No se puede conectar con FastAPI. Comprueba que está funcionando en el puerto 8000."
        );
      } finally {
        setCargando(false);
      }
    }

    cargarFlota();
  }, []);

  if (cargando) {
    return (
      <p className="text-sm text-gray-500">
        Conectando con FlotIQ API...
      </p>
    );
  }

  if (error || !flota) {
    return (
      <p className="text-sm text-red-600">
        {error || "No hay datos disponibles."}
      </p>
    );
  }

  const indicadores = [
    ["Vehículos eléctricos", flota.vehiculos],
    ["Conductores", flota.conductores],
    ["Cargadores disponibles", flota.cargadores],
    ["Potencia de instalación", `${flota.potencia_maxima_kw} kW`],
    ["Capacidad de batería", `${flota.capacidad_bateria_kwh} kWh`],
  ];

  return (
    <div>
      <div className="mb-6 flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-green-500" />
        <span className="text-xs font-medium text-green-700">
          Conectado a FlotIQ API
        </span>
      </div>

      <div className="space-y-5">
        {indicadores.map(([nombre, valor]) => (
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

      <p className="mt-5 text-xs text-gray-400">
        Configuración de la flota simulada.
      </p>
    </div>
  );
}
