# Modelo de costes de AURUM Quant Lab

Fase C. Calibrado el 2026-10-10 con `python -m aurum.cli calibrate-costs`. Los parámetros
quedan en `configs/cost_model.yaml` (versionado) y los escenarios en `configs/backtest.yaml`.
Todo se fijó **antes** de probar estrategias y no se ajusta según sus resultados.

## Datos y convenciones

| Elemento | Valor |
|---|---|
| Fuente | ticks bid/ask de ICMarketsSC-Demo, XAUUSD (`data/raw/.../ticks/`, sin modificar) |
| Muestra | 87 094 528 ticks en 137 días con cotización (2026-04-01 01:49 a 2026-10-09 23:56); el 2026-04-03 (Viernes Santo) no tiene ticks |
| Cobertura | 187 801 minutos con ticks; se usan 187 799 (ver "Minutos excluidos") |
| Unidad | **puntos**: 1 punto = 0.01 USD de precio = 1 USD por lote = 0.01 USD con 0.01 lotes |
| Horas | **del servidor** (Nueva York + 7 h, docs/TIMEZONE.md). La hora 0 no existe: es la pausa diaria |
| Procesamiento | archivo diario por archivo diario, leyendo solo `time_msc`, `bid` y `ask` (unos 20 s en total). El resumen por minuto se guarda en `data/processed/.../tick_minutes.parquet` |

### Tres formas de medir el spread

- **Ponderado por ticks**: cada tick pesa igual. Sobrerrepresenta los momentos de mucha
  actividad. La mediana por minuto de esta media es la cifra de 8,57 puntos de la fase B.
- **Ponderado por tiempo**: cada cotización pesa el tiempo que estuvo vigente hasta el
  siguiente tick, con un tope de 60 s para que las pausas no cuenten. Es el coste esperado de
  una orden que llega en un instante cualquiera. **Es la medida que usa el modelo.**
- **Mínimo de la barra** (campo `spread` de M1): el menor spread del minuto. Infravalora el coste.

### Distribución global (abril-octubre de 2026)

| Medida | Media | Mediana | p75 | p90 | p95 | p99 | Máx. |
|---|---|---|---|---|---|---|---|
| Spread instantáneo ponderado por tiempo | 8,86 | 9 | 11 | 12 | 12 | 40 | 700 |
| Spread instantáneo ponderado por ticks | 8,87 | 9 | 11 | 12 | 12 | 16 | 700 |
| Media por tiempo de cada minuto | 8,84 | 8,46 | 10,0 | 11,0 | 11,9 | 40,0 | 199,8 |
| Exceso sobre el mínimo de la barra | 2,12 | 1,83 | 3,11 | 4,26 | 4,97 | 7,23 | |

### Perfil por hora del servidor (puntos)

Spread instantáneo ponderado por tiempo (media y percentiles exactos a partir de un histograma
por hora) y exceso de la media por minuto sobre el mínimo de la barra. n = minutos.

| Hora | n | Media | Mediana | p90 | p99 | Mínimo barra (media) | Exceso medio | Exceso p90 | Exceso p99 |
|---|---|---|---|---|---|---|---|---|---|
| 01 | 8 119 | 9,34 | 9 | 12 | 21 | 6,99 | 2,35 | 4,75 | 11,09 |
| 02 | 8 220 | 8,89 | 9 | 12 | 14 | 6,32 | 2,58 | 4,78 | 6,86 |
| 03 | 8 220 | 9,09 | 10 | 12 | 12 | 6,35 | 2,74 | 4,94 | 7,61 |
| 04 | 8 220 | 9,19 | 10 | 12 | 14 | 6,27 | 2,93 | 5,11 | 9,66 |
| 05 | 8 220 | 8,86 | 9 | 12 | 12 | 6,09 | 2,77 | 4,97 | 6,61 |
| 06 | 8 217 | 8,58 | 9 | 12 | 12 | 5,90 | 2,68 | 4,83 | 6,28 |
| 07 | 8 220 | 8,66 | 9 | 12 | 12 | 6,07 | 2,60 | 4,77 | 6,33 |
| 08 | 8 151 | 9,24 | 10 | 12 | 12 | 6,47 | 2,77 | 4,94 | 7,30 |
| 09 | 8 151 | 8,34 | 8 | 11 | 12 | 6,38 | 1,95 | 3,76 | 6,40 |
| 10 | 8 208 | 8,31 | 8 | 11 | 11 | 6,35 | 1,96 | 3,84 | 5,94 |
| 11 | 8 220 | 8,15 | 8 | 11 | 12 | 6,23 | 1,92 | 3,81 | 6,15 |
| 12 | 8 197 | 8,11 | 8 | 11 | 11 | 6,32 | 1,79 | 3,62 | 5,66 |
| 13 | 8 220 | 8,06 | 8 | 11 | 11 | 6,26 | 1,80 | 3,62 | 5,41 |
| 14 | 8 220 | 7,91 | 8 | 10 | 10 | 6,29 | 1,62 | 3,33 | 4,95 |
| 15 | 8 212 | 8,48 | 9 | 10 | 17 | 6,43 | 2,06 | 3,84 | 9,30 |
| 16 | 8 218 | 8,47 | 9 | 10 | 15 | 6,43 | 2,04 | 3,93 | 9,22 |
| 17 | 8 220 | 7,95 | 8 | 10 | 14 | 5,87 | 2,08 | 3,81 | 8,87 |
| 18 | 8 219 | 7,73 | 8 | 10 | 12 | 5,83 | 1,90 | 3,60 | 7,61 |
| 19 | 8 211 | 8,29 | 8 | 11 | 12 | 6,53 | 1,76 | 3,71 | 6,73 |
| 20 | 8 100 | 8,06 | 8 | 11 | 12 | 6,41 | 1,65 | 3,66 | 5,80 |
| 21 | 8 040 | 8,08 | 8 | 11 | 11 | 6,50 | 1,58 | 3,44 | 5,90 |
| 22 | 7 980 | 8,27 | 8 | 11 | 11 | 6,63 | 1,65 | 3,64 | 5,66 |
| 23 | 7 796 | 18,11 | 9 | 40 | 40 | 16,27 | 1,47 | 3,07 | 29,02 |

Lectura: el spread es bastante plano entre las 02:00 y las 22:00 (8-9 puntos de media). La
hora 23 (las 16:00 de Nueva York, antes del cierre diario) tiene una media de 18 puntos: el
spread salta a 40 puntos durante parte de esa hora. La sesión europea temprana (02:00-08:00)
es algo más cara que la americana.

### Régimen de volatilidad

Se probó clasificar cada hora por el ATR H1 de las 24 horas anteriores, en percentil respecto
a los ~120 días previos y dividido en tercios (cálculo causal; análisis exploratorio que no
quedó en el código). Medias por minuto en abril-julio: bajo 8,89, medio 9,02 y alto 9,19 puntos,
con p90 de 11 en los tres. Fuera de muestra, media por hora y régimen dio un error de 2,30
puntos frente a 2,29 sin régimen, así que **el modelo no usa el régimen**. El mínimo de la barra ya
recoge el cambio de nivel en momentos de tensión.

## Modelo elegido

```text
spread_estimado(minuto) = spread_mínimo_de_la_barra_M1(minuto) + exceso(hora del servidor)
```

Comparación fuera de muestra: calibración con abril-julio (119 072 minutos) y predicción de la
media por tiempo de cada minuto de agosto a octubre (68 672 minutos).

| Modelo | Error absoluto medio | Sesgo |
|---|---|---|
| Spread fijo (media global de calibración) | 2,29 | +0,42 |
| Media por hora | 2,30 | +0,42 |
| **Mínimo de la barra + exceso medio por hora** | **1,39** | **+0,79** |

El modelo elegido reduce el error casi un 40 %. Su sesgo positivo significa que sobreestima el coste
unos 0,8 puntos en el periodo de prueba, lo que es conservador. Un spread fijo de 8,6 puntos
no se usa: ignora la hora 23 y los cambios de nivel del historial.

**Por qué funciona en todo el historial**: el mínimo de la barra existe desde 2017 y cambia con
el tiempo (mediana de 4 puntos en 2018-2019, media de 14,6 en 2020 y de 6,7 en 2026). El
exceso por hora solo se ha medido en 2026; aplicarlo a 2017-2025 supone que la diferencia entre
el spread medio y el mínimo dentro de cada minuto se ha mantenido parecida. **Ese supuesto no
se puede verificar** porque no hay ticks anteriores a abril de 2026.

### Minutos excluidos de la calibración

Se excluyen los minutos cuyos ticks no reproducen el máximo y el mínimo de la barra M1:

- **2026-06-29 15:41**: la barra abre en 4 044,01, pero el primer tick guardado es de 4 042,73.
  Además, las barras de 15:37 a 15:40 no tienen ningún tick. Es un **hueco en el historial de
  ticks del terminal**, no un error de la barra: las barras de 15:37-15:41 existen con 115-559
  ticks de volumen. Es la "única discrepancia" de la fase B.
- **2026-10-09 23:56**: hay ticks, pero la barra no está guardada porque no había cerrado al
  descargar (regla de solo barras cerradas).

**Efecto en el motor**: los ticks solo se usan para decidir el orden de stop y objetivo dentro
de un minuto, y solo si reproducen exactamente su máximo y mínimo. En 2026-06-29 15:37-15:41
no se cumple y el motor aplica el supuesto conservador. Hay una prueba que lo verifica
(`tests/integration/test_real_data_engine.py`). No hace falta ninguna excepción adicional.

## Escenarios (`configs/backtest.yaml`)

| Escenario | Exceso de spread | Multiplicador de spread | Slippage por lado | Comisión | Swap |
|---|---|---|---|---|---|
| base | media por hora | 1,0 | 2 puntos | 3,50 USD/lado/lote | x1,0 |
| adverso | p90 por hora | 1,0 | 10 puntos | x1,0 | x1,5 |
| estrés | p99 por hora | 1,5 (sobre todo el spread) | 30 puntos | x1,5 | x2,0 |

- **Comisión**: 3,50 USD por lado y lote estándar de la cuenta Raw Spread, **verificada por Juan
  en el portal oficial de IC Markets el 2026-10-10** (`verified_on` en `configs/backtest.yaml`).
  Se cobra una vez al abrir y otra al cerrar: 7,00 USD por lote ida y vuelta y 0,07 USD con
  0,01 lotes. Hay pruebas que lo comprueban.
- **Slippage**: **no medido**. Los valores son supuestos a contrastar en paper trading (fase G).
  Se aplica a órdenes a mercado, stops y cierres por tiempo; no a objetivos, que son órdenes límite.
- **Swap**: valores de la instantánea de especificaciones del 2026-10-10 (largo −57,03 y corto
  +39,767 puntos por lote y noche). El triple del miércoles para metales lo confirma el portal de
  IC Markets y coincide con `swap_rollover3days = 3` del terminal; el motor lo aplica y lo prueba
  `test_swap_charged_per_night_with_triple_wednesday`. No hay histórico de swaps en la API:
  aplicarlos a 2017-2025 es una aproximación.

## Limitaciones y supuestos pendientes

1. El exceso por hora se calibró con 6 meses de 2026 y se aplica a todo el historial.
2. El slippage es un supuesto, no una medición.
3. El ask de las barras se estima. Fuera del periodo con ticks, un stop de un corto puede
   dispararse antes o después que en la realidad si el spread real de ese minuto fue distinto.
4. El swap histórico es desconocido.
5. No hay datos de profundidad ni de rechazos del bróker, así que no se modelan rechazos por
   liquidez.
