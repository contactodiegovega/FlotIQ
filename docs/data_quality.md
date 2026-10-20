# FlotIQ — Calidad y limitaciones de los datos

## 1. Objetivo

Documentar el origen, las validaciones y las limitaciones de los datos utilizados en FlotIQ, una plataforma de análisis y optimización de recargas para flotas de vehículos eléctricos VTC.

## 2. Fuentes de datos

| Fuente | Naturaleza | Registros |
|---|---|---:|
| Vehículos, conductores, turnos, asignaciones y trayectos | Datos sintéticos | 5.892 |
| Precios de electricidad OMIE | Datos históricos | 59.135 |
| Tráfico del Ayuntamiento de Madrid | Datos históricos | 2.160 |
| Meteorología Open-Meteo | Datos históricos | 32.856 |
| **Total** | | **100.043** |

## 3. Validaciones realizadas

- Integridad referencial entre las cinco tablas operativas: cuatro comprobaciones sin errores.
- Coherencia temporal de viajes, turnos y asignaciones: cinco comprobaciones sin errores.
- Validación de las columnas y ausencia de valores nulos en los archivos externos inspeccionados.
- Comprobación de la numeración consecutiva de los periodos eléctricos de OMIE.
- Verificación de los registros almacenados en las ocho tablas PostgreSQL.
- Confirmación de que RLS está activado en las ocho tablas.

## 4. Limitaciones conocidas

### Datos operativos sintéticos

La flota simulada contiene 50 Tesla Model 3 y 80 conductores, con una semana de operación y 4.962 trayectos.

Los viajes, los consumos y las asignaciones no representan operaciones reales de una empresa VTC.

El consumo energético utiliza inicialmente una hipótesis de 16 kWh/100 km y no contempla todos los factores reales, como climatización, desplazamientos sin pasajeros o degradación de las baterías.

### Precios eléctricos

Los datos de OMIE representan precios del mercado mayorista, no el precio final de suministro eléctrico de una empresa.

Las fechas se han convertido a UTC utilizando una interpretación de los periodos del mercado. Queda pendiente contrastar dicha interpretación con la especificación oficial de OMIE.

### Tráfico

Los datos de tráfico corresponden a septiembre de 2025, mientras que la operación simulada se desarrolla en septiembre de 2026.

Se utilizarán como referencia histórica de congestión, no como observaciones reales durante los trayectos simulados.

La zona horaria del archivo original está pendiente de confirmación.

Los valores de velocidad media iguales a cero deben interpretarse con cautela, especialmente para la categoría URB.

### Meteorología

Los datos se solicitaron a Open-Meteo con la zona horaria Europe/Madrid, pero el CSV contiene 24 registros para todos los días, incluidos los días de cambio horario.

Antes de utilizar estas observaciones en cruces temporales exactos será necesario revisar o reconstruir las marcas de tiempo.

### Viabilidad energética

La primera simulación de baterías no incorpora recargas y puede producir saldos energéticos negativos teóricos.

La disponibilidad de un vehículo fuera de turno no garantiza que esté físicamente situado en un cargador.

La viabilidad energética y la planificación de recargas se abordarán en la Fase 3.

## 5. Seguridad

Las ocho tablas de Supabase tienen Row Level Security activado.

Antes de exponer datos mediante la aplicación web será necesario revisar las políticas de acceso y los permisos de los roles utilizados.

## 6. Próximas mejoras

- Normalizar y verificar las zonas horarias de todas las fuentes.
- Crear perfiles históricos de congestión para la simulación.
- Mejorar el modelo de consumo energético.
- Incorporar la disponibilidad realista de puntos de recarga.
- Comparar estrategias de carga mediante indicadores de coste y viabilidad.