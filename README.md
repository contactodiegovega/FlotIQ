# FlotIQ

**Predicción de precios eléctricos y optimización de recargas para flotas de vehículos eléctricos.**

Proyecto final del Bootcamp de Data Science de Upgrade Hub.

## Descripción

FlotIQ es una aplicación web que utiliza Machine Learning para predecir los precios de la electricidad y optimizar las recargas de una flota VTC en Madrid.

El proyecto trabaja con un escenario simulado de **50 vehículos eléctricos, 80 conductores y 20 cargadores**, con una potencia máxima conjunta de 150 kW.

## Tecnologías

- **Python, Pandas y PostgreSQL:** procesamiento y almacenamiento de datos.
- **Scikit-learn:** predicción de precios mediante HistGradientBoostingRegressor.
- **PuLP:** optimización de recargas.
- **FastAPI:** backend y API REST.
- **Next.js, React y TypeScript:** aplicación web.

## Datos y Machine Learning

Se utilizan precios históricos de **OMIE** y datos operativos para analizar patrones de consumo y disponibilidad.

El proceso incluye limpieza de datos, análisis exploratorio (EDA) y predicción horaria de precios para los próximos dos días.

El modelo utiliza variables temporales y precios históricos de 72 y 168 horas anteriores.

En la evaluación realizada, el modelo ML obtuvo un MAE aproximado de **38,68 €/MWh**, frente a **27,66 €/MWh** del baseline semanal. Esta limitación se tiene en cuenta al interpretar los resultados.

## Funcionalidades

- Predicción de precios eléctricos para 48 horas.
- Optimización de recargas según costes y restricciones operativas.
- Visualización de vehículos, turnos y conductores estimados.
- Consulta de disponibilidad y asignación propuesta de cargadores.
- Dashboard con indicadores económicos y energéticos.
- Actualización de datos y generación de planificaciones mediante un pipeline Python.

Los turnos, las baterías y las operaciones futuras son simulaciones. Los costes mostrados son estimaciones, no ahorros reales demostrados.

## Instalación

**Backend**, desde la raíz del proyecto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn backend.main:app --reload
```

**Frontend**, en otra terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Abrir la aplicación en `http://localhost:3000/dashboard`.

La ejecución completa requiere los datos procesados, el modelo entrenado y la configuración de PostgreSQL para las funciones que consultan conductores.

## Estructura

- `backend/`: API, predicción y optimización.
- `frontend/`: aplicación web.
- `data/`: datos históricos y procesados.
- `notebooks/`: EDA y experimentación.
- `models/`: modelo entrenado.
- `database/`: base de datos.

## Limitaciones

FlotIQ es un prototipo funcional basado en datos históricos y escenarios simulados. No dispone de telemetría ni turnos futuros confirmados, y el precio mayorista de OMIE no representa necesariamente el precio final facturado.

La aplicación se ejecuta en entorno local.