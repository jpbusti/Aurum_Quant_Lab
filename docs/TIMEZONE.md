# Zona horaria del servidor

**Convención adoptada: hora del servidor ICMarketsSC-Demo = hora de Nueva York + 7 h.**
Equivale a UTC+3 mientras rige el horario de verano de EE. UU. y a UTC+2 el resto del año.
Aprobada por Juan el 2026-10-10. Queda pendiente una confirmación en vivo (ver abajo).

## Qué guarda el laboratorio

- Los datos crudos (`data/raw/`) conservan las marcas originales de la API: `time_raw`
  (barras, segundos) y `time_msc` (ticks, milisegundos), en hora del servidor.
- La API de MetaTrader 5 documenta UTC, pero entrega la hora del servidor. Nunca se debe
  interpretar `time_raw` como UTC.
- Toda conversión a UTC se hace en una capa posterior (fase C), sin modificar los datos crudos.

## Evidencia

1. **Calendario de sesiones** (M1, 2017-04 a 2026-10, ver DATA_DICTIONARY.md): apertura
   diaria a las 01:00 del servidor, pausa de 00:00 a 01:00 y apertura semanal el lunes a las
   01:00, igual en verano que en invierno. En Nueva York eso es la apertura de las 18:00 y la
   pausa de 17:00 a 18:00 del oro, que tampoco cambian con el horario de verano.
2. **Publicaciones macro de EE. UU.** (08:30 de Nueva York) caen siempre a las 15:30 del
   servidor:
   - IPC 2022-11-10 (horario de invierno de EE. UU.): salto en la barra M1 de las 15:30.
   - Empleo 2018-04-06 y 2024-05-03 (horario de verano): saltos a las 15:30.
   - Empleo 2019-12-06 (invierno): salto a las 15:30.
   Si el servidor fuese un UTC fijo, esas horas se moverían una hora entre estaciones.
3. **Último tick del viernes 2026-10-09** a las 23:56:58 del servidor, coherente con el cierre
   de las 17:00 de Nueva York (21:00 UTC en horario de verano) más 7 h.

## Conversión

```text
hora_NY  = hora_servidor - 7 h                (aritmética simple, sin zona)
hora_UTC = hora_NY localizada en America/New_York y convertida a UTC
```

Los cambios de hora de Nueva York ocurren el domingo a las 02:00 de NY, es decir el domingo
a las 09:00 del servidor, con el mercado cerrado. Por eso la conversión no tiene horas ambiguas
ni inexistentes dentro de las sesiones. Si apareciera algún dato en domingo por la mañana, la
conversión debe fallar en lugar de adivinar.

## Pendiente

- **Confirmación en vivo**: ejecutar `python -m aurum.cli check-environment` con el mercado
  abierto (desde el domingo a las ~22:00 UTC). El desfase medido debe ser +3 h hasta el
  2026-11-01 y +2 h a partir de ese día, cuando acaba el horario de verano de EE. UU. Si no
  coincide, esta convención se revisa antes de usarla.
- Implementar la conversión y su prueba en la fase C (mismo ejemplo de los datos macro).
