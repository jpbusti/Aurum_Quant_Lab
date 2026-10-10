# Investigación de estrategias de AURUM Quant Lab

Fase D, 2026-10-10; resultados de la fase E añadidos el mismo día ([PHASE_E_RESULTS.md](PHASE_E_RESULTS.md)).
Sin optimización. **Las tres candidatas fueron rechazadas en la fase E**: ninguna tiene ventaja en nuestros datos. Código en `src/aurum/strategies/`,
registro de variantes en `configs/research.yaml`.

## Cómo leer estas fichas

Cada estrategia distingue tres niveles de evidencia, que no son equivalentes:

1. **Publicada**: lo que dice la fuente, sobre su mercado, sus datos y sus costes.
2. **Probada en nuestros datos**: resultado en XAUUSD de IC Markets con el motor de la fase C.
   Desde la fase E existe para las seis: ver cada ficha y PHASE_E_RESULTS.md.
3. **Resultados reales verificables**: operativa real o paper trading auditable. No existe.

Todas las estrategias de este documento son **variantes propias** inspiradas en una fuente. Los
resultados de la fuente no se atribuyen a estas variantes, y si fallan no dicen nada sobre la
fuente original.

## Registro de variantes

| Id | Tipo | Variantes definidas | Variantes probadas | Estado |
|---|---|---|---|---|
| REF-NOTRADE-v1 | referencia | 1 | 1 | evaluada (fase E) |
| REF-RANDOM-v1 | referencia | 1 | 1 | evaluada; placebo de 1 000 semillas |
| REF-SMACROSS-v1 | referencia | 1 | 1 | evaluada; ver observación en PHASE_E_RESULTS.md |
| CAND-ORB-NY-v1 | candidata | 1 | 1 | **REJECTED** |
| CAND-IMOM-NY-v1 | candidata | 1 | 1 | **REJECTED** |
| CAND-TREND-ATR-v1 | candidata | 1 | 1 | **REJECTED** |
| **Total** | | **6** | **6** | |

Hipótesis consideradas y **no implementadas** (se registran para no ocultarlas):

- **Ruptura de la sesión de Londres**: la apertura de Londres en hora de Nueva York cambia
  cuando los horarios de verano de Reino Unido y EE. UU. no coinciden. Eso exige la conversión a
  UTC, todavía sin confirmar en vivo. Además, solo encontré material divulgativo sin metodología
  reproducible.
- **Reversión a la media sobre VWAP**: el CFD no tiene un volumen real verificado (fase B). Un
  VWAP con `tick_volume` sería una hipótesis distinta de la publicada.

Cualquier variante nueva, cambio de parámetro o prueba futura se añade a este registro y a
`configs/research.yaml`, también si falla. El número de pruebas alimenta el DSR de la fase E.

## Convenciones comunes

- **Horas**: en hora de Nueva York, que es la del servidor menos 7 h (docs/TIMEZONE.md, pendiente
  de confirmación en vivo). Con esa convención, las 09:30 de Nueva York son las 16:30 del
  servidor durante todo el año.
- **Decisión**: al cierre de cada vela M15, con un `DataView` que solo contiene velas cerradas
  (M15, H1 y M5). La ejecución la decide el motor: apertura de la siguiente barra M1, bid/ask,
  costes del escenario y tamaño por riesgo (docs/BACKTEST_ENGINE.md).
- **Indicadores**: ATR = media simple de los últimos n rangos verdaderos y SMA = media simple de
  cierres, calculados solo con velas cerradas (`features/indicators.py`).
- **Parámetros**: fijados antes de cualquier prueba. Donde la fuente da un valor, se usa ese.
  Donde no, se usa un valor convencional y se dice. No se ajustan en esta fase.
- **Común a todas**: una posición a la vez (el motor rechaza señales con posición abierta), sin
  stops dinámicos (el motor no los soporta) y sin operar si falta un dato necesario.

---

## CAND-ORB-NY-v1: ruptura del rango de apertura de Nueva York

1. **Nombre e identificador**: Opening Range Breakout, apertura de EE. UU., M15. `CAND-ORB-NY-v1`.
2. **Fuente, enlace y fecha de consulta (2026-10-10)**:
   - C. Zarattini y A. Aziz, "Can Day Trading Really Be Profitable? Evidence of Sustainable
     Long-term Profits from Opening Range Breakout (ORB) Day Trading Strategy", SSRN 4416622,
     2023. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416622 . **El texto original no
     se pudo leer** (la página devuelve 403). Las reglas se tomaron de la réplica siguiente.
   - T. Krueger, "The opening-range breakout paper, replicated on five indices: gross reproduced,
     net zero", blog de MQL5, 25-09-2026. https://www.mql5.com/en/blogs/post/776235 .
     Réplica independiente, sin revisión por pares.
   - C. Lundström, "On the Profitability of Momentum Strategies and Optimal Leverage Rules", Umeå
     Economic Studies 974, 2020. https://econpapers.repec.org/paper/hhsumnees/0974.htm .
     Estudios de ORB en futuros de crudo y del DAX.
3. **Evidencia y limitaciones**:
   - Publicada (según la réplica): ORB de 5 minutos en QQQ con un acierto del ~24 % y +0,13 R por
     operación, con comisión pero **sin spread ni slippage** y **sin periodo fuera de muestra**.
   - La réplica reproduce el resultado bruto en el NQ, pero, neto de costes, ninguno de cinco
     índices se distingue de cero y cuatro son negativos. Sí supera una referencia aleatoria por
     ~0,10-0,13 R en tres índices: hay una señal pequeña del tamaño de los costes.
   - **No encontré ningún estudio de ORB en oro.** La aplicación a XAUUSD es una hipótesis nuestra.
4. **Reglas exactas**:
   - Vela de rango: la vela M15 que abre a las 09:30 NY (16:30 del servidor). Si no existe (hueco),
     no se opera ese día.
   - Al cierre de esa vela (09:45 NY): si cierra por encima de su apertura, compra; si cierra por
     debajo, venta; si cierra igual, nada.
   - Stop: extremo opuesto de la vela de rango (su mínimo para compras y su máximo para ventas).
   - Objetivo: 10 veces el riesgo inicial medido desde el cierre de la vela de rango.
   - Salida por tiempo: a las 16:00 NY (6 h 15 min tras la decisión), si no saltó antes stop u objetivo.
   - Como máximo una señal al día.
5. **Marco temporal y condiciones**: señal en M15 y ejecución sobre M1. Solo días con la vela de
   las 09:30 NY. Sin filtro de régimen.
6. **Indicadores y parámetros**: ninguno. Inicio 09:30 NY, duración 15 min, cierre 16:00 NY,
   objetivo 10R.
7. **Stop, objetivo y gestión**: stop fijo en el extremo opuesto, objetivo 10R y cierre por tiempo.
   Sin stop dinámico.
8. **Supuestos de ejecución**: entrada a mercado en la apertura de la barra M1 de las 09:45 NY, al
   ask (compras) o al bid (ventas), con el spread y el slippage del escenario. Un stop muy cercano
   puede quedar dentro del spread, lo que es un riesgo real de esta regla en oro.
9. **Riesgos conocidos**: stops estrechos frente al spread y al slippage; dependencia de una sola
   vela; la apertura de acciones de EE. UU. puede no ser una referencia relevante para el oro, que
   cotiza casi 23 h; el cierre a las 16:00 NY cae a las 23:00 del servidor, la hora de mayor spread.
10. **Hipótesis a contrastar**: la dirección de la primera vela M15 tras las 09:30 NY anticipa el
    movimiento del resto de la sesión en XAUUSD lo bastante como para superar los costes reales.
11. **Variantes probadas**: 1 (fase E, 2026-10-10). Sin otras variantes.
12. **Resultados** (escenario base, 0,5 % de riesgo): in-sample 2017-2022 con PF 1,05 y +2 750 USD,
    pero negativo en el escenario adverso; validación 2023-2024 con PF 0,86; prueba final
    2025-2026 con 453 operaciones, PF 0,90 (IC90 0,68-1,14), DD 28,9 %, Sharpe −0,62 y expectancy
    −0,067 R. Placebo: p = 0,68. DSR 0,009.
13. **Decisión: REJECTED** (falla 6 de 7 estrictas y las 4 flexibles). Causa probable
    (inferida, sin análisis adicional): la dirección de la primera vela de la sesión de acciones no
    anticipa el oro de forma estable. Es coherente con la réplica de la fuente, que encontró un
    bruto pequeño y un neto nulo en índices.

**Diferencias con la fuente**: velas de 15 minutos en vez de 5, oro en vez de QQQ y cierre a las
16:00 NY por analogía con el cierre de acciones. Es una variante propia.

---

## CAND-IMOM-NY-v1: momentum intradía (primera media hora → última media hora)

1. **Nombre e identificador**: Market intraday momentum, sesión de EE. UU. `CAND-IMOM-NY-v1`.
2. **Fuente, enlace y fecha de consulta (2026-10-10)**: L. Gao, Y. Han, S. Z. Li y G. Zhou,
   "Market intraday momentum", *Journal of Financial Economics* 129(2), 394-414, 2018.
   DOI 10.1016/j.jfineco.2018.05.009. Ficha consultada:
   https://profiles.wustl.edu/en/publications/market-intraday-momentum/ (texto completo no leído).
3. **Evidencia y limitaciones**:
   - Publicada: en el ETF del S&P 500 (1993-2013), el retorno de la primera media hora, medido
     desde el cierre del día anterior, predice el de la última media hora. El efecto es más fuerte
     en días volátiles, de mucho volumen, de recesión y de datos macro. También aparece en otros
     diez ETF muy negociados.
   - Limitaciones: es evidencia en ETF de acciones, no en oro. La ficha consultada no detalla
     costes ni la regla operativa exacta. Las explicaciones propuestas (reequilibrios y operadores
     informados tarde) son de mercados de acciones con cierre diario; el oro cotiza casi 23 h.
4. **Reglas exactas**:
   - Referencia: cierre de la vela M15 que termina a las 16:00 NY del día de negociación anterior
     (como máximo 4 días antes; si no existe, no se opera).
   - Retorno de la mañana: log(cierre a las 10:00 NY de hoy / referencia).
   - A las 15:30 NY (22:30 del servidor): compra si el retorno es positivo y venta si es negativo.
   - Salida por tiempo a los 30 minutos (16:00 NY).
   - Stop de protección a 3 ATR(14, M15) del último cierre, sin objetivo.
5. **Marco temporal y condiciones**: velas M15; operación de 15:30 a 16:00 NY (22:30 a 23:00 del
   servidor). Una señal al día como máximo.
6. **Indicadores y parámetros**: ventana de 09:30-10:00 NY medida desde el cierre anterior de las
   16:00 NY (como en la fuente), última media hora 15:30-16:00, ATR 14 y stop de 3 ATR.
7. **Stop, objetivo y gestión**: el stop de 3 ATR es un **añadido nuestro** por control de riesgo,
   porque la fuente mantiene la posición sin stop. Sin objetivo; cierre por tiempo.
8. **Supuestos de ejecución**: entrada a mercado en la apertura de las 15:30 NY. La salida a las
   16:00 NY coincide con la hora 23 del servidor, donde el spread medio por tiempo es de 18 puntos
   (COST_MODEL.md). El coste puede anular cualquier efecto.
9. **Riesgos conocidos**: coste alto en la ventana de salida; el "cierre" de 16:00 NY es una
   convención de acciones (el oro cierra a las 17:00 NY); una operación al día da pocas
   observaciones independientes.
10. **Hipótesis a contrastar**: en XAUUSD, el signo del retorno desde las 16:00 NY del día anterior
    hasta las 10:00 NY de hoy predice el signo del retorno de 15:30 a 16:00 NY, y la ventaja supera
    los costes reales.
11. **Variantes probadas**: 1 (fase E, 2026-10-10).
12. **Resultados** (base): in-sample con PF 0,67; validación con PF 0,80; prueba final con 420
    operaciones, PF 0,99 (IC90 0,81-1,21), DD 2,0 %, Sharpe −0,07 y expectancy −0,000 R. En el
    escenario de estrés el PF cae a 0,55. Placebo: p = 0,39. DSR 0,041.
13. **Decisión: REJECTED** (falla 5 de 7 estrictas y 3 flexibles). Causa probable
    (inferida): el patrón documentado en ETF de acciones no aparece en el oro. Además, la salida a
    las 16:00 NY coincide con la hora de mayor spread, por eso el resultado empeora tanto con costes
    mayores.

---

## CAND-TREND-ATR-v1: ruptura de canal a favor de la tendencia, con ATR

1. **Nombre e identificador**: seguimiento de tendencia intradía con ATR. `CAND-TREND-ATR-v1`.
2. **Fuente, enlace y fecha de consulta (2026-10-10)**: B. K. Hurst, Y. H. Ooi y L. H. Pedersen,
   "A Century of Evidence on Trend-Following Investing", *Journal of Portfolio Management* 44(1),
   2017. https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing
3. **Evidencia y limitaciones**:
   - Publicada: el momentum de series temporales (ir largo en mercados con retornos recientes
     positivos y corto en los negativos) fue rentable de forma consistente en más de un siglo de
     datos y en muchos mercados.
   - Limitaciones: la evidencia es de horizontes de **meses** y carteras diversificadas, no de
     velas de 15 minutos en un solo instrumento. **Las reglas de esta variante (canal de 20 velas,
     filtro H1, ATR) son nuestras** y no proceden de la fuente. Que la tendencia funcione en meses
     no implica que funcione intradía.
4. **Reglas exactas**:
   - Solo entre las 03:00 y las 15:00 NY (10:00 a 22:00 del servidor).
   - Compra si el cierre de la vela M15 supera el máximo de las 20 velas M15 anteriores **y** el
     cierre de la última H1 cerrada está por encima de su SMA de 50.
   - Venta si el cierre queda por debajo del mínimo de las 20 velas anteriores **y** el cierre H1
     está por debajo de su SMA de 50.
   - Stop a 2 ATR(14, M15) y objetivo a 4 ATR del cierre de la vela de señal.
   - Cierre por tiempo a las 24 h.
5. **Marco temporal y condiciones**: señal M15 con contexto H1 (solo velas H1 cerradas) y
   ejecución sobre M1.
6. **Indicadores y parámetros**: canal de 20, SMA H1 de 50, ATR de 14, stop de 2 ATR, objetivo de
   4 ATR y 24 h. Valores convencionales, sin optimizar.
7. **Stop, objetivo y gestión**: stop y objetivo fijos (relación 1:2). El seguimiento de tendencia
   suele usar stops dinámicos, que el motor aún no soporta; esta es una limitación de la variante.
8. **Supuestos de ejecución**: entrada a mercado tras la ruptura, con riesgo de comprar en máximos
   locales; el slippage en rupturas puede ser mayor que el del escenario base.
9. **Riesgos conocidos**: falsas rupturas en rangos laterales, muchas operaciones (más costes) y
   posiciones que atraviesan la pausa diaria y pagan swap.
10. **Hipótesis a contrastar**: en XAUUSD, las rupturas de canal M15 en la dirección de la
    tendencia H1 continúan lo suficiente para que un objetivo de 4 ATR compense un stop de 2 ATR
    después de costes.
11. **Variantes probadas**: 1 (fase E, 2026-10-10).
12. **Resultados** (base): in-sample con PF 1,00; validación con PF 0,91; prueba final con 697
    operaciones, PF 1,00 (IC90 0,88-1,15), DD 13,0 %, Sharpe 0,08 y expectancy −0,008 R (+48 USD
    netos). Placebo: p = 0,33. DSR 0,061.
13. **Decisión: REJECTED** (falla 5 de 7 estrictas y 3 flexibles). Causa probable
    (inferida): las rupturas de canal de 15 minutos no continúan lo suficiente para compensar el
    stop después de costes. La evidencia de tendencia de la fuente es de horizontes mensuales y no
    se traslada al intradía.

---

## Referencias de comparación

No son estrategias candidatas ni se presentan como rentables. Sirven para que una candidata
tenga que superar algo más que cero.

### REF-NOTRADE-v1: no operar
Nunca genera señales. Resultado esperado: 0 operaciones, 0 costes y equity plana. Comprueba que
cualquier resultado distinto de cero viene de operar.

### REF-RANDOM-v1: entrada aleatoria con restricciones
- En cada cierre M15 entre las 03:00 y las 15:00 NY abre con probabilidad 0,0125 (unas 0,6
  entradas por día de negociación) y elige lado a cara o cruz.
- Stop y objetivo a 2 ATR(14, M15), es decir 1R, con cierre por tiempo a las 4 h.
- El azar depende solo de la semilla (20261010) y del instante de decisión, así que el resultado es
  reproducible y no depende de datos futuros.
- En la fase E se usarán muchas semillas para obtener una **distribución** de resultados al azar
  con los mismos costes, no un único número.
- Hipótesis nula que encarna: sin información, el resultado esperado es el coste.

### REF-SMACROSS-v1: cruce de medias simples
- Compra cuando la SMA(20) de cierres M15 cruza por encima de la SMA(50) en la última vela cerrada,
  y vende en el cruce contrario.
- Stop a 2 ATR(14), sin objetivo, con cierre por tiempo a las 24 h.
- Es una regla de tendencia trivial y muy conocida, con parámetros convencionales. Una candidata
  de tendencia que no la supere no aporta nada.

---

## Pruebas (`tests/unit/test_strategies.py`, datos sintéticos)

- **Interfaz** (cada estrategia): hereda de `Strategy`, decide en el cierre de velas M15, devuelve
  lado ±1, stop y objetivo al lado correcto del último cierre, cierre por tiempo positivo e
  `info_time <= decision_time`.
- **No fuga** (cada estrategia, 3 cortes): se sustituyen por otras velas coherentes todas las
  barras M1, M5, M15 y H1 sin cerrar en el corte (cambian nivel, dirección y rango), y las señales
  anteriores al corte deben ser idénticas.
- **Poder de la prueba**: una estrategia defectuosa a propósito, que mira la vela siguiente, hace
  fallar la comprobación.
- **Comportamiento**: ORB en una vela construida a mano (compra, stop, 10R y cierre a las 16:00
  NY; nada con vela sin cuerpo o fuera de hora), momentum con retornos fijados a mano,
  reproducibilidad y ventana de la aleatoria, cruce de medias y tendencia en series con dirección
  conocida.
- **Registro**: los parámetros del código coinciden con `configs/research.yaml` y el total de
  variantes probadas cuadra con el registro.
