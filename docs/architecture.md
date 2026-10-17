# FlotIQ - Arquitectura técnica

## Objetivo

Desarrollar una plataforma de análisis y planificación
energética para una flota eléctrica de VTC.

## Arquitectura prevista

Fuentes externas
    |
    v
Python - Ingesta y ETL
    |
    +--> CSV / Parquet (datos originales y procesados)
    |
    v
PostgreSQL
    |
    +--> Machine Learning (predicción de precios)
    |
    +--> Optimización (planificación de recargas)
    |
    +--> FastAPI --> Next.js / React
    |
    +--> Power BI

## Principios de desarrollo

1. Priorizar datos reales y fuentes verificables.
2. Documentar cualquier dato simulado.
3. Separar ingesta, transformación y modelado.
4. Mantener código reutilizable fuera de notebooks.
5. Evitar credenciales y datos sensibles en Git.
6. Validar modelos con separación temporal.
7. Evaluar restricciones operativas y energéticas.
8. Mantener documentación y pruebas actualizadas.


## Estado

Arquitectura propuesta durante la Fase 0.
Pendiente de validación técnica en las fases siguientes.