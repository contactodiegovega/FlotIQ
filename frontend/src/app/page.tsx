
import Image from "next/image";

const modulos = [
  {
    numero: "01",
    titulo: "Predicción energética",
    descripcion:
      "Anticipa los precios de la electricidad y descubre cuándo conviene recargar.",
  },
  {
    numero: "02",
    titulo: "Recargas optimizadas",
    descripcion:
      "Planifica las cargas de cada vehículo sin comprometer la operación de tu flota.",
  },
  {
    numero: "03",
    titulo: "Vehículos y turnos",
    descripcion:
      "Coordina los conductores y los vehículos con sus necesidades energéticas.",
  },
];

export default function Home() {
  return (
    <main className="min-h-screen bg-[#FAFAFC] text-[#111827]">
      {/* Navegación */}
      <header className="mx-auto flex max-w-7xl items-center justify-between px-6 py-6 lg:px-10">
        <a
          href="#inicio"
          className="flex items-center gap-2 text-2xl font-bold tracking-tight"
        >
          <span className="text-3xl text-[#8047F8]">ϟ</span>
          <span>
            Flot<span className="text-[#8047F8]">IQ</span>
          </span>
        </a>

        <nav className="hidden items-center gap-9 text-sm font-medium text-gray-600 md:flex">
          <a href="#inicio" className="transition hover:text-[#8047F8]">
            Inicio
          </a>
          <a href="#modulos" className="transition hover:text-[#8047F8]">
            Plataforma
          </a>
          <a href="#como-funciona" className="transition hover:text-[#8047F8]">
            Cómo funciona
          </a>
        </nav>

        <a
          href="#modulos"
          className="rounded-full border border-[#E5E0F4] px-5 py-2.5 text-sm font-semibold text-[#7541DC] transition hover:border-[#8047F8] hover:bg-[#F1EBFF]"
        >
          Explorar FlotIQ
        </a>
      </header>

      {/* Presentación principal */}
      <section
        id="inicio"
        className="mx-auto grid min-h-[650px] max-w-7xl items-center gap-12 px-6 pb-20 pt-12 lg:grid-cols-2 lg:px-10 lg:pt-16"
      >
        <div className="relative z-10">
          <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-[#E8E3F4] bg-white px-4 py-2 text-xs font-semibold tracking-wide text-gray-600">
            <span className="h-2 w-2 rounded-full bg-[#8047F8]" />
            INTELIGENCIA ENERGÉTICA PARA FLOTAS VTC
          </div>

          <h1 className="max-w-2xl text-5xl font-semibold leading-[1.08] tracking-[-0.055em] sm:text-6xl lg:text-[68px]">
            Optimiza la recarga de tu{" "}
            <span className="text-[#8047F8]">
              flota eléctrica.
            </span>
          </h1>

          <p className="mt-8 max-w-lg text-lg leading-relaxed text-[#6B7280]">
            Predice el coste de la energía y descubre cuándo
            cargar tus vehículos. Planifica recargas, coches y
            turnos desde una sola plataforma.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-4">
            <a
              href="/dashboard"
              className="inline-flex items-center gap-3 rounded-xl bg-[#8047F8] px-7 py-4 text-sm font-semibold text-white shadow-lg shadow-purple-500/15 transition duration-300 hover:-translate-y-1 hover:bg-[#6B2DFF]"
            >
              Acceder al panel de control
              <span aria-hidden="true">→</span>
            </a>

            <a
              href="#modulos"
              className="rounded-xl border border-[#DFDFE5] bg-white px-7 py-4 text-sm font-semibold text-gray-700 transition duration-300 hover:-translate-y-1 hover:border-[#8047F8]"
            >
              Explorar funcionalidades
            </a>
          </div>

          <div className="mt-12 flex flex-wrap gap-x-8 gap-y-3 text-sm text-gray-500">
            <span>✓ Previsión de precios</span>
            <span>✓ Recargas inteligentes</span>
            <span>✓ Gestión de flota</span>
          </div>
        </div>

        {/* Imagen principal */}
        <div className="relative">
          <div className="absolute -inset-5 rounded-[40px] bg-gradient-to-br from-[#F0EBFF] via-white to-[#EBF0F7] blur-2xl" />

          <div className="relative overflow-hidden rounded-[30px] border border-[#E9EAF0] bg-white shadow-[0_30px_90px_rgba(30,40,75,0.10)]">
            <Image
              src="/flotiq-hero-vtc.png"
              alt="Vehículo VTC eléctrico junto a un punto de recarga"
              width={797}
              height={530}
              priority
              className="h-auto w-full object-cover"
            />
          </div>

          <div className="absolute -bottom-5 left-5 flex items-center gap-3 rounded-2xl border border-[#E9EAF0] bg-white/95 px-5 py-4 shadow-xl shadow-gray-200/60 backdrop-blur-md sm:left-8">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#F2EBFF] text-xl text-[#8047F8]">
              ⚡
            </div>

            <div>
              <p className="text-sm font-semibold text-gray-900">
                Energía + planificación
              </p>
              <p className="text-xs text-gray-500">
                Una flota preparada para cada jornada
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Configuración de la flota de demostración */}
      <section className="border-y border-[#ECECF1] bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-7 px-6 py-9 lg:px-10">
          <p className="max-w-xs text-sm text-gray-500">
            Entorno de demostración basado en una flota VTC
            eléctrica simulada.
          </p>

          <div className="flex flex-wrap gap-10">
            <div>
              <p className="text-3xl font-semibold">50</p>
              <p className="mt-1 text-xs text-gray-500">
                Vehículos
              </p>
            </div>

            <div>
              <p className="text-3xl font-semibold">80</p>
              <p className="mt-1 text-xs text-gray-500">
                Conductores
              </p>
            </div>

            <div>
              <p className="text-3xl font-semibold">20</p>
              <p className="mt-1 text-xs text-gray-500">
                Cargadores
              </p>
            </div>

            <div>
              <p className="text-3xl font-semibold">150 kW</p>
              <p className="mt-1 text-xs text-gray-500">
                Potencia máxima
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Funcionalidades */}
      <section
        id="modulos"
        className="mx-auto max-w-7xl px-6 py-24 lg:px-10"
      >
        <div className="mb-12 max-w-2xl">
          <span className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8047F8]">
            La plataforma
          </span>

          <h2 className="mt-4 text-4xl font-semibold tracking-tight">
            Cada recarga, una decisión inteligente.
          </h2>

          <p className="mt-4 text-gray-500">
            FlotIQ combina previsiones energéticas con las
            necesidades operativas de una flota eléctrica.
          </p>
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          {modulos.map((modulo) => (
            <article
              key={modulo.numero}
              className="group rounded-3xl border border-[#E8E8EE] bg-white p-8 transition duration-300 hover:-translate-y-1 hover:border-[#D8C8FF] hover:shadow-xl hover:shadow-purple-100/50"
            >
              <span className="text-sm font-semibold text-[#8047F8]">
                {modulo.numero}
              </span>

              <h3 className="mt-8 text-xl font-semibold tracking-tight">
                {modulo.titulo}
              </h3>

              <p className="mt-4 text-sm leading-7 text-gray-500">
                {modulo.descripcion}
              </p>
            </article>
          ))}
        </div>
      </section>

      {/* Funcionamiento */}
      <section
        id="como-funciona"
        className="bg-[#F0F1F5] px-6 py-20"
      >
        <div className="mx-auto max-w-7xl lg:px-4">
          <h2 className="text-3xl font-semibold tracking-tight">
            Primero predecimos. Después optimizamos.
          </h2>

          <p className="mt-4 max-w-2xl leading-7 text-gray-600">
            Estimamos los precios eléctricos, tenemos en cuenta
            la disponibilidad de cada vehículo y calculamos un
            plan de recargas que respeta las restricciones de
            la flota.
          </p>

          <p className="mt-6 text-xs text-gray-500">
            Las previsiones futuras son estimaciones sujetas
            a incertidumbre. Los resultados de demostración
            utilizan datos operativos simulados.
          </p>
        </div>
      </section>

      <footer className="border-t border-gray-200 bg-white px-6 py-8 text-center text-sm text-gray-400">
        FlotIQ · Inteligencia energética para flotas eléctricas
      </footer>
    </main>
  );
}
