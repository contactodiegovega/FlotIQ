# FlotIQ

**Intelligent Electric Fleet Management**

FlotIQ es un proyecto de ciencia de datos orientado a la gestión energética y operativa de una flota de vehículos eléctricos destinada a servicios de transporte VTC.

El objetivo es desarrollar una plataforma capaz de anticipar los costes energéticos, planificar recargas y facilitar la asignación de vehículos y conductores, manteniendo la disponibilidad operativa de la flota.

## 1. Caso de uso

El proyecto plantea un escenario empresarial de demostración con:

- 50 vehículos eléctricos.
- 80 conductores registrados.
- 20 puntos de carga AC de 11 kW.
- Una potencia máxima simultánea de 150 kW.
- Un horizonte de planificación de 24 horas.

Estos parámetros constituyen hipótesis iniciales de diseño y podrán ajustarse tras el análisis de los datos.

## 2. Objetivos

- Obtener y analizar datos reales de precios eléctricos, movilidad y recarga.
- Construir un pipeline ETL reproducible.
- Diseñar una base de datos relacional en PostgreSQL.
- Desarrollar un modelo predictivo de precios eléctricos.
- Optimizar la planificación de recargas respetando restricciones operativas.
- Gestionar vehículos, conductores, turnos y servicios.
- Desarrollar una aplicación web con Next.js y React.
- Crear un dashboard de análisis empresarial en Power BI.

## 3. Tecnologías previstas

**Datos:** Python, Pandas, NumPy, Requests y PyArrow.

**Base de datos:** PostgreSQL, SQLAlchemy y Psycopg.

**Machine Learning y optimización:** Scikit-learn y SciPy.

**Backend:** FastAPI.

**Frontend:** Next.js y React.

**Business Intelligence:** Power BI.

**Desarrollo:** VS Code, Git y GitHub.

## 4. Metodología

El proyecto se organiza en cinco fases:

1. **Adquisición de datos:** investigación de fuentes, descarga de datasets y APIs, y generación documentada de datos sintéticos cuando sea necesario.
2. **ETL y análisis:** limpieza, transformación, integración, almacenamiento SQL y análisis exploratorio.
3. **Machine Learning y optimización:** predicción de precios, estimación de necesidades energéticas y planificación de recargas.
4. **Desarrollo web:** aplicación operativa para gestionar flota, conductores y recargas.
5. **Power BI:** dashboard de seguimiento energético, económico y operativo.

## 5. Fuentes de datos previstas

Se evaluarán fuentes como:

- OMIE: precios del mercado eléctrico.
- Ayuntamiento de Madrid: datos públicos de taxi y movilidad.
- ACN-Data: registros históricos de sesiones de recarga.
- Open-Meteo: datos y previsiones meteorológicas.

La accesibilidad, cobertura, licencia y calidad de cada fuente se verificarán durante la primera fase.

Los datos simulados se identificarán expresamente y no se presentarán como observaciones reales.

## 6. Estructura del repositorio

- `data/`: datos originales, procesados y muestras.
- `notebooks/`: exploración y experimentación.
- `src/flotiq/`: código Python reutilizable.
- `database/`: esquemas y consultas SQL.
- `api/`: backend FastAPI.
- `web/`: aplicación Next.js.
- `powerbi/`: informes de Business Intelligence.
- `models/`: modelos y artefactos generados.
- `tests/`: pruebas automatizadas.
- `docs/`: documentación técnica.

## 7. Instalación del entorno Python

Requisitos: Python y Git. Las versiones compatibles se concretarán y documentarán durante la preparación del entorno.

Crear y activar el entorno virtual en Windows:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instalar dependencias:

```powershell
python -m pip install -r requirements.txt
```

## 8. Estado del proyecto

**Fase 0 — Preparación del repositorio.**

La obtención de datos, el desarrollo de modelos y la aplicación web todavía no han comenzado.

## 9. Limitaciones iniciales

- No se dispone de registros internos reales de una empresa VTC.
- La disponibilidad de datasets y APIs debe validarse.
- Los costes se estimarán utilizando un escenario contractual documentado; el precio mayorista no equivale directamente al coste final facturado.
- La optimización de rutas en tiempo real queda fuera del alcance inicial.

## 10. Próximos pasos

Finalizar la configuración del repositorio, validar las fuentes de datos y comenzar el pipeline de adquisición.
