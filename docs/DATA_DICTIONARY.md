# Diccionario de datos de AURUM Quant Lab

Fase B. Fuente única: terminal MT5, servidor **ICMarketsSC-Demo**, símbolo **XAUUSD**.
Las cifras de este documento salen de `validate-data` del 2026-10-10 (informe completo en
`data/reports/quality/latest.json`, no versionado).

## Almacén

```text
data/raw/ICMarketsSC-Demo/XAUUSD/
├── bars/<TF>/<año>.parquet      TF = M1, M5, M15, M30, H1 (nativos del servidor)
├── bars/<TF>/manifest.json      fuente + una entrada por descarga
├── ticks/<AAAA-MM-DD>.parquet   un archivo por día del servidor
├── ticks/manifest.json          fuente, descargas y estado (completo o no) de cada día
└── specs/<hash>.json            especificaciones del símbolo en cada descarga
```

Cada Parquet lleva en sus metadatos (`aurum`) la fuente, el símbolo, el timeframe y la
convención horaria. El manifiesto registra en cada descarga: hora UTC de descarga, servidor,
empresa, modo de cuenta, build del terminal, versión del paquete, rango pedido y recibido,
filas nuevas, barras re-descargadas idénticas, conflictos (con ejemplos), barras sin cerrar
descartadas y hash de especificaciones.

### Barras (`bars/<TF>/<año>.parquet`)

| Columna | Tipo | Significado |
|---|---|---|
| `time_raw` | int64 | apertura de la barra, epoch en **hora del servidor** tal como lo da la API |
| `open`, `high`, `low`, `close` | float64 | precios **bid** (verificado contra ticks: 100 % de coincidencia en máximo y mínimo) |
| `tick_volume` | int64 | número de ticks en la barra |
| `spread` | int32 | **spread mínimo** de la barra en puntos (0.01 USD), no el medio; ver abajo |
| `real_volume` | int64 | volumen real informado por el bróker; significado para el CFD sin verificar, no se usa |

### Ticks (`ticks/<día>.parquet`)

| Columna | Tipo | Significado |
|---|---|---|
| `time_msc` | int64 | epoch en milisegundos, hora del servidor |
| `bid`, `ask` | float64 | precios cotizados |
| `last`, `volume`, `volume_real` | | vacíos en este CFD (0) |
| `flags` | int64 | banderas de la API (qué cambió en el tick) |

Ticks disponibles en el terminal solo desde 2026-04-01. Descargados: los 138 días laborables
del 2026-04-01 al 2026-10-09, 87,1 M ticks y 686 MB. Integridad correcta: ordenados, bid y ask
positivos, sin ask por debajo del bid. Hay 7 513 ticks repetidos exactamente; se conservan. El día del último tick se marca como posiblemente
incompleto y se vuelve a pedir en la siguiente descarga.

## Reglas de ingesta

1. **Solo barras cerradas**: se guarda una barra si `time_raw + duración <= hora del último tick`.
   Con el mercado cerrado, la última barra del viernes queda pendiente hasta el lunes.
2. **Incremental**: cada descarga empieza en la última barra guardada. Esa barra se vuelve a
   pedir y se compara con la guardada.
3. **Sin sobrescritura**: si el servidor devuelve otra versión de una barra ya guardada, se
   conserva la original y se registra el conflicto en el manifiesto. Hasta hoy: 0 conflictos.
4. **Una sola fuente**: si el servidor, el símbolo o el modo de cuenta no coinciden con
   `configs/data.yaml` o con el manifiesto, la descarga se niega (`SourceMismatchError`).
5. **Errores**: cada llamada a MT5 se reintenta 3 veces con reconexión; si persiste, falla sin
   escribir datos parciales del bloque.

## Convención horaria

Todo se guarda en **hora del servidor**, sin convertir. Evidencia sobre el desfase:

- Calendario observado (M1, 2017-2026): apertura diaria a las 01:00, cierre a las 23:57-23:59,
  fin de semana del viernes 23:57 al lunes 01:00, en verano y en invierno.
- Datos macro de EE. UU. publicados a las 08:30 de Nueva York aparecen siempre a las
  **15:30 del servidor**: IPC del 10-11-2022 (invierno en EE. UU.) y empleo del 03-05-2024 y
  06-04-2018 (verano). El servidor sigue el horario de verano de EE. UU.
- Convención adoptada: hora del servidor = hora de Nueva York + 7 h. El detalle, la regla de
  conversión y la confirmación pendiente están en [TIMEZONE.md](TIMEZONE.md).

## Calendario y huecos

`configs/data.yaml > sessions` (derivado de los datos, hora del servidor). Clasificación:

| Clase | Regla | M1 |
|---|---|---|
| `daily_break` | termina en la apertura (01:00-01:05) y dura hasta 75 min | 1 895 |
| `weekend` | contiene el sábado a mediodía | 496 |
| `early_close` | termina en la apertura y dura hasta 6 h (festivos de EE. UU., cierre 20:00-21:30) | 58 |
| `holiday` | termina en la apertura y dura más de 6 h (Navidad y Año Nuevo entre semana) | 8 |
| `unexplained` | todo lo demás | 444 |

Los huecos no se rellenan. Huecos sin explicar en M1: 435 cortos (1-29 min, 2 054 min en
total, sobre todo en 2017 y 2021) y 9 largos:

| Desde (servidor) | Hasta | Minutos |
|---|---|---|
| 2021-12-02 10:22 | 2021-12-02 16:38 | 376 |
| 2018-09-14 19:32 | 2018-09-14 21:37 | 125 |
| 2026-06-29 08:05 | 2026-06-29 10:07 | 122 |
| 2026-03-31 23:59 | 2026-04-01 01:49 | 110 |
| 2026-03-25 16:16 | 2026-03-25 17:38 | 82 |
| 2023-08-24 20:15 | 2023-08-24 21:01 | 46 |
| 2023-08-15 08:05 | 2023-08-15 08:41 | 36 |
| 2017-05-29 20:06 | 2017-05-29 20:41 | 35 |
| 2018-07-09 01:01 | 2018-07-09 01:36 | 35 |

Dos semanas abrieron tarde (2017-04-17 01:47 y 2023-04-03 01:19). El motor de backtesting
(fase C) no debe ejecutar órdenes dentro de un hueco: la siguiente cotización válida es la
primera barra posterior.

## Resultados de la validación (2026-10-10)

| TF | Barras | Desde | Hasta | Estado |
|---|---|---|---|---|
| M1 | 3 365 568 | 2017-04-06 01:00 | 2026-10-09 23:55 | WARN (huecos, saltos) |
| M5 | 674 341 | 2017-04-06 01:00 | 2026-10-09 23:50 | WARN |
| M15 | 224 817 | 2017-04-06 01:00 | 2026-10-09 23:30 | WARN |
| M30 | 112 432 | 2017-04-06 01:00 | 2026-10-09 23:00 | WARN |
| H1 | 56 241 | 2017-04-06 01:00 | 2026-10-09 22:00 | WARN |

- Sin errores críticos: ordenadas, sin duplicados, en la rejilla, OHLC coherentes, precios
  positivos y finitos, archivos sin solapamientos, una sola fuente y una versión de especificaciones.
- **M5, M15, M30 y H1 nativos coinciden al 100 % con los reconstruidos desde M1.** Se pueden
  usar los nativos o reconstruirlos; el resultado es el mismo.
- Barras M1 frente a ticks (187 800 minutos, abril-octubre de 2026): los mínimos coinciden al
  100 % y los máximos en el 99,9995 % (1 minuto distinto: 2026-06-29 15:41, por un hueco de
  ticks de 15:37 a 15:41; análisis y efecto en el motor en [COST_MODEL.md](COST_MODEL.md)).

### Exclusión aplicada

2017-04-01 a 2017-04-06 01:00: el 3 y 4 de abril el servidor devuelve una barra por hora con
etiqueta M1, y el 5 de abril el minuto a minuto empieza a las 10:21. Se excluye en todos los
timeframes; el historial utilizable empieza en la sesión del **6 de abril de 2017**.

### Saltos de precio (avisos, no se eliminan)

281 retornos M1 superan 25 escalas robustas del año, la mayoría en publicaciones macro de
las 15:30 del servidor (reales). Un caso parece una cotización errónea:

- **2020-03-26 10:23**: barra M1 a 1 500.59 entre barras a ~1 600-1 602, con 3 ticks y spread
  de 261 puntos. Arrastra el mínimo de las barras M5, M15, M30 y H1 que la contienen.
  **Se mantiene** (decisión de Juan del 2026-10-10): el bróker la cotizó y pudo ejecutar stops.
  Su impacto se medirá en la fase C.

### Spread

El campo `spread` de las barras es el **mínimo** del periodo: coincide con el spread mínimo de
los ticks en el 99,92 % de los minutos (abril-octubre de 2026). En ese periodo la mediana del
spread medio de los ticks fue 8,6 puntos, frente a 5 en el campo de las barras. Hay un 9 % de barras M1 con spread 0.
**Usarlo como coste infravaloraría el spread.** El modelo de costes de la fase C se calibrará
con ticks.
