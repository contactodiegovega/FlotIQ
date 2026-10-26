
import Image from "next/image";
import Link from "next/link";

const modulos = [
  {
    numero: "01",
    titulo: "Predicción energética",
    descripcion:
      "Estimamos el precio de la electricidad durante las próximas 48 horas mediante modelos de machine learning.",
  },
  {
    numero: "02",
    titulo: "Recargas optimizadas",
    descripcion:
      "Calculamos cuándo cargar cada vehículo teniendo en cuenta los costes eléctricos y las restricciones operativas.",
  },
  {
    numero: "03",
    titulo: "Control de la flota",
    descripcion:
      "Consultamos la planificación, el estado de las baterías, los horarios de recarga y los costes estimados.",
  },
];

export default function Home() {
  return (
    <main className="min-h-screen bg-[#FAFAFC] text-[#111827]">

      {/* HEADER */}
      <header className="border-b border-[#ECECF1] bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5 lg:px-10">

          
          <Link
            href="/"
            className="text-2xl font-extrabold tracking-tight text-slate-900"
          >
            Flot<span className="text-violet-600">IQ</span>
          </Link>


          <nav className="flex items-center gap-4 sm:gap-7">
            <Link
              href="/"
              className="text-sm font-medium text-[#374151] transition hover:text-[#8047F8]"
            >
              Inicio
            </Link>

            <Link
              href="/dashboard"
              className="rounded-xl bg-[#8047F8] px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#6B2DFF]"
            >
              Dashboard ↗
            </Link>
          </nav>

        </div>
      </header>

      {/* HERO PRINCIPAL */}
      <section className="mx-auto grid max-w-7xl items-center gap-12 px-6 pb-24 pt-20 lg:min-h-[620px] lg:grid-cols-2 lg:px-10">

        {/* TEXTOS */}
        <div className="relative z-10">

          <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-[#E8E3F4] bg-white px-4 py-2 text-xs font-semibold tracking-wide text-[#5B556B]">
            <span className="h-2 w-2 rounded-full bg-[#8047F8]" />
            INTELIGENCIA ENERGÉTICA PARA FLOTAS VTC
          </div>

          <h1 className="max-w-2xl text-5xl font-semibold leading-[1.1] tracking-[-0.055em] text-[#111827] sm:text-6xl lg:text-[64px]">
            Optimiza la recarga de tu{" "}
            <span className="text-[#8047F8]">
              flota eléctrica.
            </span>
          </h1>

          <p className="mt-8 max-w-lg text-lg leading-8 text-[#6B7280]">
            FlotIQ combina inteligencia artificial y optimización
            matemática para anticipar los precios eléctricos
            y planificar las recargas de una flota de vehículos VTC.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-4">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-3 rounded-xl bg-[#8047F8] px-7 py-4 text-sm font-semibold text-white shadow-lg shadow-purple-500/15 transition hover:-translate-y-1 hover:bg-[#6B2DFF]"
            >
              Abrir Dashboard
              <span aria-hidden="true">→</span>
            </Link>

            <a
              href="#como-funciona"
              className="rounded-xl border border-[#DFDFE5] bg-white px-7 py-4 text-sm font-semibold text-[#374151] transition hover:border-[#8047F8]"
            >
              Cómo funciona
            </a>
          </div>

          <div className="mt-10 flex flex-wrap gap-x-7 gap-y-3 text-sm text-[#6B7280]">
            <span>✓ Predicción de precios</span>
            <span>✓ Recargas inteligentes</span>
            <span>✓ Gestión de flota</span>
          </div>
        </div>

        {/* FOTO ORIGINAL DEL COCHE VTC */}
        <div className="relative">
          <div className="absolute -inset-5 rounded-[40px] bg-gradient-to-br from-[#F0EBFF] via-white to-[#EBF0F7] blur-2xl" />

          <div className="relative overflow-hidden rounded-[30px] border border-[#E9EAF0] bg-white shadow-[0_30px_90px_rgba(30,40,75,0.12)]">
            <Image
              src="/flotiq-hero-vtc.png"
              alt="Vehículo VTC eléctrico junto a un punto de recarga"
              width={797}
              height={530}
              priority
              className="h-auto w-full object-cover"
            />
          </div>

          <div className="absolute -bottom-5 left-5 flex items-center gap-3 rounded-2xl border border-[#E9EAF0] bg-white px-5 py-4 shadow-xl shadow-gray-200/60 sm:left-8">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#F2EBFF] text-xl text-[#8047F8]">
              ⚡
            </div>

            <div>
              <p className="text-sm font-semibold text-[#111827]">
                Energía + planificación
              </p>

              <p className="text-xs text-[#6B7280]">
                Una flota preparada para cada jornada
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* DATOS DE LA FLOTA */}
      <section className="border-y border-[#ECECF1] bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-8 px-6 py-10 lg:px-10">
          <p className="max-w-xs text-sm leading-6 text-[#6B7280]">
            Entorno de demostración basado en una flota
            VTC eléctrica con operaciones simuladas.
          </p>

          <div className="flex flex-wrap gap-10">
            {[
              ["50", "Vehículos"],
              ["80", "Conductores"],
              ["20", "Cargadores"],
              ["48 h", "Planificación"],
            ].map(([valor, etiqueta]) => (
              <div key={etiqueta}>
                <p className="text-3xl font-semibold text-[#111827]">
                  {valor}
                </p>
                <p className="mt-1 text-xs text-[#6B7280]">
                  {etiqueta}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FUNCIONALIDADES */}
      <section
        id="funcionalidades"
        className="mx-auto max-w-7xl px-6 py-24 lg:px-10"
      >
        <div className="mb-12 max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8047F8]">
            La plataforma
          </p>

          <h2 className="mt-4 text-4xl font-semibold tracking-tight text-[#111827]">
            Cada recarga, una decisión inteligente.
          </h2>

          <p className="mt-5 leading-7 text-[#6B7280]">
            Transformamos previsiones energéticas en decisiones
            operativas para gestionar una flota de manera más eficiente.
          </p>
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          {modulos.map((modulo) => (
            <article
              key={modulo.numero}
              className="rounded-3xl border border-[#E8E8EE] bg-white p-8 transition hover:border-[#D8C8FF] hover:shadow-xl hover:shadow-purple-100/40"
            >
              <span className="text-sm font-semibold text-[#8047F8]">
                {modulo.numero}
              </span>

              <h3 className="mt-8 text-xl font-semibold text-[#111827]">
                {modulo.titulo}
              </h3>

              <p className="mt-4 leading-7 text-[#6B7280]">
                {modulo.descripcion}
              </p>
            </article>
          ))}
        </div>
      </section>

      {/* COMO FUNCIONA */}
      <section
        id="como-funciona"
        className="bg-[#F0F1F5] px-6 py-20"
      >
        <div className="mx-auto max-w-7xl lg:px-4">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8047F8]">
            Nuestro método
          </p>

          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-[#111827]">
            Primero predecimos. Después optimizamos.
          </h2>

          <p className="mt-5 max-w-3xl leading-8 text-[#4B5563]">
            FlotIQ estima los precios eléctricos para los próximos
            dos días, simula las necesidades operativas de los
            vehículos y utiliza optimización matemática para
            calcular un calendario de recargas que respeta las
            restricciones de la flota.
          </p>

          <p className="mt-5 max-w-3xl text-sm leading-6 text-[#6B7280]">
            Las predicciones son estimaciones sujetas a incertidumbre.
            Los resultados del entorno de demostración se basan
            en operaciones simuladas.
          </p>

          <Link
            href="/dashboard"
            className="mt-8 inline-flex items-center gap-2 rounded-xl bg-[#8047F8] px-7 py-4 text-sm font-semibold text-white transition hover:bg-[#6B2DFF]"
          >
            Explorar Dashboard →
          </Link>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="border-t border-[#ECECF1] bg-white px-6 py-8 text-center text-sm text-[#9CA3AF]">
        FlotIQ · Inteligencia energética para flotas eléctricas
      </footer>
    </main>
  );
}

