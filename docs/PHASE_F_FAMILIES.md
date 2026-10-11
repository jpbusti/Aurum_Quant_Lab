# Fase F: resultados por familias

**Fecha**: 2026-10-11. Pre-registro: [PREREGISTRO_PHASE_F.md](PREREGISTRO_PHASE_F.md) (huellas
SHA-256 en `experiments/phase_f/PREREGISTRO.sha256`, publicadas en el hilo antes de ejecutar).
Familias: [FAMILIES_RESEARCH.md](FAMILIES_RESEARCH.md). Código: `experiments/phase_f/run.py`
(`--screen` tardó 271 s con 4 procesos; `--analyze` calcula las correcciones). Periodo:
2017-04-06 a 2026-10-09, gastado: nada de esto es una validación.

## Veredicto

| Familia | Variantes | Pasan FDR (q < 0,10) | Pasan DSR (≥ 0,95) | PBO | Veredicto pre-registrado |
|---|---|---|---|---|---|
| TREND | 72 | 0 | 0 | 0,184 | **SIN_EDGE** |
| MEANREV | 64 | 0 | 0 | 0,147 | **SIN_EDGE** |
| CALENDAR | 88 | 2 | 0 | 0,004 | **INCONCLUSO** |

Capa de capital (0,5 %, 10 000 USD, escenario base), la que decide según el pre-registro.
**Ninguna familia es EDGE_CANDIDATO.** Ninguna variante sobrevive a FDR y DSR a la vez, así que
no hay sensibilidad que correr (sección 8 del pre-registro).

**Las 2 variantes de CALENDAR que pasan FDR son un artefacto del swap** (diagnóstico posterior,
abajo). Por eso el INCONCLUSO no apunta a una ventaja real. Siguiendo la sección 9 del
pre-registro, no se resuelve ampliando la rejilla sobre estos datos.

**Decisión**: cerrar la línea "XAUUSD M15 con reglas técnicas simples". No hay ninguna
candidata para paper trading de esta fase.

## Correcciones

| Capa | N pruebas (DSR) | Varianza de Sharpe diario entre pruebas | SR0 anual (máximo esperado sin habilidad) |
|---|---|---|---|
| Capital | 233 | 0,00317 | 2,52 |
| Señal | 233 | 0,00094 | 1,37 |

El SR0 de la capa de capital es alto porque los Sharpe de las 224 variantes están muy
dispersos (de −2 a +1,8 anual). El mejor Sharpe observado (1,82) queda por debajo, y el DSR
máximo es 0,017.

| Familia (capital) | q mínimo de la familia | q global mínimo | DSR máximo | PBO | Logit mediano | P(pérdida OOS de la mejor IS) | Pendiente de degradación |
|---|---|---|---|---|---|---|---|
| TREND | 0,875 | 1,0 | < 0,001 | 0,184 | 1,05 | 0,28 | −0,82 |
| MEANREV | 1,0 | 1,0 | < 0,001 | 0,147 | 1,20 | 1,00 | −0,92 |
| CALENDAR | < 0,001 | < 0,001 | 0,017 | 0,004 | 4,48 | 0,03 | −0,64 |

Un PBO bajo **no** indica ventaja por sí solo. En MEANREV es bajo porque todas las variantes
pierden de forma parecida: la mejor dentro de muestra perdió fuera de muestra en el 100 % de las
combinaciones. En CALENDAR es bajo porque las variantes vendedoras que cruzan el rollover
cobran swap todos los días, dentro y fuera de muestra (ver diagnóstico).

## Resultados brutos (capa de capital)

Número de variantes por intervalo.

| PF | CALENDAR | MEANREV | TREND |
|---|---|---|---|
| < 0,8 | 28 | 6 | 1 |
| 0,8-0,9 | 34 | 47 | 17 |
| 0,9-1,0 | 21 | 11 | 33 |
| 1,0-1,1 | 2 | 0 | 18 |
| 1,1-1,15 | 1 | 0 | 3 |
| 1,15-1,3 | 1 | 0 | 0 |
| ≥ 1,3 | 1 | 0 | 0 |

| Sharpe anual | CALENDAR | MEANREV | TREND |
|---|---|---|---|
| < −1 | 35 | 31 | 3 |
| −1 a −0,5 | 29 | 27 | 9 |
| −0,5 a 0 | 19 | 6 | 32 |
| 0 a 0,5 | 2 | 0 | 26 |
| 0,5 a 1 | 1 | 0 | 2 |
| ≥ 1 | 2 | 0 | 0 |

| p-valor | CALENDAR | MEANREV | TREND |
|---|---|---|---|
| < 0,001 | 2 | 0 | 0 |
| 0,001-0,01 | 1 | 0 | 0 |
| 0,01-0,05 | 0 | 0 | 2 |
| 0,05-0,1 | 0 | 0 | 4 |
| 0,1-0,5 | 2 | 0 | 22 |
| ≥ 0,5 | 83 | 64 | 44 |

- PF mediano: TREND 0,95, MEANREV 0,85, CALENDAR 0,86. Variantes con beneficio neto: TREND 21
  de 72, MEANREV 0 de 64, CALENDAR 5 de 88.
- Drawdown máximo mediano: TREND 51 %, MEANREV 57 %, CALENDAR 36 %.
- Señales rechazadas porque 0,01 lotes arriesgan más del 0,5 %: TREND 12 589, MEANREV 75 893 y
  CALENDAR 8 192. Señales rechazadas por tener ya una posición abierta: muchas más (una
  posición a la vez).

## Capa de señal (0,01 lotes fijos; informativa)

| Familia | Pasan FDR | Pasan DSR | PBO | q mínimo | PF > 1 |
|---|---|---|---|---|---|
| TREND | 0 | 0 | **0,547** (falla) | 0,175 | 51 de 72 |
| MEANREV | 0 | 0 | 0,191 | 1,0 | 0 de 64 |
| CALENDAR | 0 | 0 | 0,464 | 1,0 | 13 de 88 |

TREND muestra una inclinación positiva con volumen fijo: 13 variantes con p < 0,05 y PF
máximo de 1,15-1,3. Pero no supera FDR, y su PBO de 0,547 dice que elegir la mejor
dentro de muestra rinde menos que la mediana fuera de muestra en más de la mitad de las
combinaciones. Con volumen fijo pesan más los años recientes de subida fuerte del oro;
no se ha comprobado si esa inclinación es solo la tendencia del propio activo.

## Diagnóstico de CALENDAR (posterior a los resultados, no cambia el veredicto)

Las dos variantes que pasan FDR son ventas cerca del cierre diario:

| Variante | Operaciones | PF | Sharpe | q | DSR | Swap cobrado | Neto | Neto sin swap | PF sin swap |
|---|---|---|---|---|---|---|---|---|---|
| FAM-CALENDAR-h16-S-d1 | 2 372 | 1,36 | 1,82 | < 0,001 | 0,017 | +19 205 | +8 116 | **−11 089** | 0,64 |
| FAM-CALENDAR-h14-S-d4 | 2 396 | 1,18 | 1,01 | 0,018 | < 0,001 | +11 860 | +5 253 | **−6 608** | 0,81 |

- La venta de las 16:00 NY a 1 hora no sale a las 17:00: a esa hora el mercado está cerrado,
  así que el cierre por tiempo se ejecuta en la reapertura (01:00 del servidor). El 99 % de
  las operaciones cruza el rollover y cobra un día de swap (el triple los miércoles). Lo mismo
  ocurre con la de las 14:00 NY a 4 horas.
- El swap corto que usa el motor es **+39,77 puntos por noche**, la instantánea del
  2026-10-10, aplicada a todo 2017-2026. El swap histórico es desconocido
  ([COST_MODEL.md](COST_MODEL.md)): con los tipos de interés de 2017-2021 probablemente era
  distinto. **Sin el swap, las dos variantes pierden.** El precio se movió en contra de la venta
  en esa ventana (media de −0,42 USD por onza, t = −3,5).
- En la capa de señal ninguna de las dos es significativa (p de 0,23 y 0,20).
- Conclusión: la "ventaja" es cobrar el swap de 2026 sobre precios de 2017-2026, no un patrón
  horario. **Limitación nueva del laboratorio**: cualquier regla que mantenga posiciones a
  través del rollover depende de un swap histórico que no tenemos.

## Contraste con librerías externas

| Comprobación | Resultado |
|---|---|
| PBO propio frente a nullius (las mismas 12 870 combinaciones) | Idéntico en las 6 familias y capas (diferencia de 0) |
| DSR de la mejor variante frente a nullius | 0,0172852 en los dos |
| PSR propio frente a jsharpe | Diferencia máxima de 0,009 (capital) y 0,034 (señal). jsharpe evalúa la varianza en SR0 y divide por T; Bailey y López de Prado (2012) la evalúan en el SR observado y dividen por T − 1. La diferencia crece con Sharpe extremos y no cambia ninguna decisión |
| Sharpe crítico por el FDR bayesiano de jsharpe (q = 0,10; p_H1 = 0,05; SR1 = 1 anual; T = días) | 0,85 anual (potencia del 68 %). Lo superan las mismas 2 variantes de CALENDAR en la capa de capital y ninguna en la de señal |

## Desviaciones del pre-registro

Ninguna en el cálculo ni en los umbrales. El diagnóstico de CALENDAR es un análisis
posterior: se informa por separado y no cambia el veredicto.

## Qué no cubre esta fase

- Horizontes diarios o semanales. Solo se probaron reglas en M15.
- Otras familias (volatilidad, otras definiciones de tendencia).
- El swap histórico, que condiciona cualquier estrategia que cruce el rollover.
- Datos nuevos: todo se evaluó sobre la muestra ya gastada.
