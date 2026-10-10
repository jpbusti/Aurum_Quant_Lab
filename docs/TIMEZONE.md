# Zona horaria del servidor

**Convención: hora del servidor ICMarketsSC-Demo = hora de Nueva York + 7 h.**
Equivale a UTC+3 mientras rige el horario de verano de EE. UU. y a UTC+2 el resto del año.
Aprobada por Juan el 2026-10-10 y **confirmada con datos históricos el 2026-10-10** (sección
"Validación histórica"). La medición en vivo del domingo queda como comprobación adicional.

## Qué guarda el laboratorio

- Los datos crudos (`data/raw/`) conservan las marcas originales de la API: `time_raw`
  (barras, en segundos) y `time_msc` (ticks, en milisegundos), en hora del servidor.
- La API de MetaTrader 5 documenta UTC, pero entrega la hora del servidor. `time_raw` nunca debe
  interpretarse como UTC.
- La conversión a UTC (`aurum.timeutils.server_to_utc`) se hace aparte y no modifica los datos
  crudos.

## Evidencia previa

1. **Calendario de sesiones** (M1, 2017-04 a 2026-10, ver DATA_DICTIONARY.md): apertura
   diaria a las 01:00 del servidor, pausa de 00:00 a 01:00 y apertura semanal el lunes a las
   01:00, igual en verano que en invierno. En Nueva York eso corresponde a la apertura de las
   18:00 y a la pausa de 17:00 a 18:00 del oro, que tampoco cambian con el horario de verano.
2. **Publicaciones macro de EE. UU.** (08:30 de Nueva York): casos sueltos a las 15:30 del
   servidor en ambas estaciones (IPC 2022-11-10; empleo 2018-04-06, 2019-12-06 y 2024-05-03).
   La sección siguiente lo comprueba de forma sistemática.
3. **Último tick del viernes 2026-10-09** a las 23:56:58 del servidor, coherente con el cierre
   de las 17:00 de Nueva York más 7 h.

## Validación histórica (2026-10-10)

Prueba pedida por Juan. Reproducible con `experiments/timezone_check/run.py` sobre `data/raw/`.

### A. Apertura del lunes y cierre del viernes en 10 semanas aleatorias (2018-2026)

Muestra: 10 lunes elegidos al azar entre 2018-01-01 y 2026-10-05 (semilla 20261010). Para
semanas anteriores a abril de 2026 no hay ticks, así que se usa la **primera barra M1** del lunes
y el **final de la última barra M1** del viernes (apertura + 59 s). La última semana se midió con
**ticks**. Criterios de Juan: lunes entre las 00:55 y las 01:10, y viernes entre las 23:50 y las 00:00.

| Lunes | Primer precio | Fuente | Viernes | Último precio | Fuente | Desfase con UTC según la regla |
|---|---|---|---|---|---|---|
| 2018-04-02 | 01:00:00 | barra M1 | 2018-04-06 | 23:58:59 | barra M1 | +3 |
| 2018-12-24 | 01:00:00 | barra M1 | 2018-12-28 | 23:56:59 | barra M1 | +2 |
| 2019-11-04 | 01:00:00 | barra M1 | 2019-11-08 | 23:56:59 | barra M1 | +2 |
| 2020-06-29 | 01:00:00 | barra M1 | 2020-07-03 | **20:00:59** | barra M1 | +3 |
| 2020-07-13 | 01:00:00 | barra M1 | 2020-07-17 | 23:56:59 | barra M1 | +3 |
| 2020-12-14 | 01:02:00 | barra M1 | 2020-12-18 | 23:56:59 | barra M1 | +2 |
| 2022-03-28 | 01:02:00 | barra M1 | 2022-04-01 | 23:56:59 | barra M1 | +3 |
| 2024-06-17 | 01:00:00 | barra M1 | 2024-06-21 | 23:56:59 | barra M1 | +3 |
| 2025-07-07 | 01:00:00 | barra M1 | 2025-07-11 | 23:56:59 | barra M1 | +3 |
| 2026-09-07 | 01:02:04 | tick | 2026-09-11 | 23:56:57 | tick | +3 |

- **Lunes: 10 de 10** dentro de 00:55-01:10, tanto en semanas de verano (+3) como de invierno (+2).
- **Viernes: 9 de 10** dentro de 23:50-00:00. La excepción es el **2020-07-03**, festivo en
  EE. UU. (se trasladó el 4 de julio): cierre anticipado a las 20:00 del servidor, las 13:00 de
  Nueva York. Es un cierre por festivo, no un desfase horario.
- Qué demuestra: el horario del oro en hora del servidor no cambia entre estaciones, así que el
  servidor sigue el horario de verano de EE. UU. Por sí solo no fija el desfase absoluto; para eso
  está la prueba B.

### B. Ancla externa: primer viernes de cada mes (2018-2026)

El informe de empleo de EE. UU. se publica a las 08:30 de Nueva York, normalmente el primer
viernes del mes. En cada primer viernes con datos (102), busqué el minuto de mayor rango entre las
13:00 y las 18:00 del servidor.

| Estación (según la regla) | Primeros viernes | Mayor rango a las 15:30 del servidor | Entre 15:29 y 15:33 |
|---|---|---|---|
| Verano de EE. UU. (UTC+3) | 66 | 50 | 53 |
| Invierno de EE. UU. (UTC+2) | 36 | 20 | 23 |
| Total | 102 | **70** | **76** |

- Las 15:30 del servidor son las 08:30 de Nueva York solo si el servidor va 7 h por delante de
  Nueva York. Con un UTC+2 o UTC+3 fijo, el pico se movería a las 14:30 o a las 16:30 en una de
  las dos estaciones, y no ocurre.
- Los otros 26 casos no se revisaron uno a uno. Son días en que el primer viernes no hubo
  informe de empleo (festivos o calendario distinto) o en que otro dato movió más el precio (por
  ejemplo, a las 17:00 del servidor, las 10:00 de Nueva York). **Es una inferencia.**

### Conclusión

Con A y B, la convención Nueva York + 7 h queda **confirmada para el historial 2018-2026**: el
servidor sigue el horario de verano de EE. UU. y está anclado a la hora de Nueva York. Límite:
estas pruebas usan las marcas del propio servidor más horarios externos conocidos, no un reloj
independiente. La medición en vivo del domingo (primer tick frente al reloj UTC del PC) queda
como comprobación adicional ya programada. Si no diera +3 h hasta el 2026-11-01 (y +2 h desde
ese día), se reabriría la cuestión.

## Conversión

```text
hora_NY  = hora_servidor - 7 h                (aritmética simple, sin zona)
hora_UTC = hora_NY localizada en America/New_York y convertida a UTC
```

Los cambios de hora de Nueva York ocurren el domingo a las 02:00 de NY, es decir, el domingo a
las 09:00 del servidor, con el mercado cerrado. Por eso la conversión no tiene horas ambiguas ni
inexistentes dentro de las sesiones. Si apareciera algún dato en domingo por la mañana, la
conversión falla en lugar de adivinar. Implementada y probada en `aurum.timeutils` (fase C).

## Comprobación adicional programada

- Domingo 2026-10-11, ~22:20 UTC: `python -m aurum.cli check-environment` con el mercado abierto.
  Desfase esperado: +3 h hasta el 2026-11-01 y +2 h a partir de ese día.
