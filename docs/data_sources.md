# FlotIQ — Inventario de fuentes de datos

## Objetivo

Identificar, evaluar y documentar las fuentes de datos utilizadas en el proyecto FlotIQ.

## Fuentes candidatas

| ID | Fuente | Información | Estado |
|---|---|---|---|
| DS01 | OMIE | Precios históricos de electricidad | Identificada |
| DS02 | Ayuntamiento de Madrid — Taxi | Características de vehículos | Identificada |
| DS03 | ACN-Data | Sesiones de recarga | Identificada |
| DS04 | Ayuntamiento de Madrid — Tráfico | Intensidad del tráfico | Identificada |
| DS05 | Open-Meteo | Meteorología histórica | Identificada |

## Criterios de validación

Para cada fuente comprobaremos:

- Organismo responsable.
- URL oficial.
- Licencia y condiciones de reutilización.
- Cobertura temporal y geográfica.
- Frecuencia de actualización.
- Formato y variables disponibles.
- Calidad y valores ausentes.
- Método de descarga o autenticación.
- Limitaciones para su integración en FlotIQ.

## Política de datos

1. Priorizar fuentes reales, oficiales y verificables.
2. Conservar los archivos originales sin modificaciones.
3. Documentar fecha de descarga, versión y procedencia.
4. Identificar expresamente los datos sintéticos.
5. No publicar identificadores personales innecesarios.
6. No subir datasets voluminosos ni credenciales a GitHub.

## Próximo paso

Validar los ficheros históricos de OMIE y desarrollar el primer proceso de ingesta reproducible en Python.