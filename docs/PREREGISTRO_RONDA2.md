# Pre-registro de la ronda 2 de hipótesis

**Fecha**: 2026-10-10. Escrito antes de ejecutar ningún backtest de las hipótesis de esta ronda.
Base: instrucciones de Juan (2026-10-10), [PREREGISTRO_PHASE_E.md](PREREGISTRO_PHASE_E.md) y
skill `aurum-methodology`. Las fichas completas están en [STRATEGY_RESEARCH.md](STRATEGY_RESEARCH.md)
(sección "Ronda 2").

## 1. Declaraciones previas

1. **La prueba final 2025-01-01 a 2026-10-09 está parcialmente gastada.** Ya vimos en la fase E
   cómo se comportó el oro en ese periodo (por ejemplo, la fuerte tendencia de 2026 que favoreció
   al cruce de medias), y esta ronda se diseña después de verlo. Cualquier resultado de 2025-2026
   puede estar contaminado por ese conocimiento, aunque ningún parámetro se haya ajustado con él.
2. **La evidencia principal será el paper trading con datos futuros, no el backtest.** El backtest
   de esta ronda funciona solo como **filtro**:
   - REJECTED en el backtest: la hipótesis se descarta y se registra.
   - CANDIDATE_FOR_PAPER o INCONCLUSIVE en el backtest: la hipótesis **solo** pasa a ser
     elegible para paper trading. Ningún resultado de backtest de esta ronda puede justificar por
     sí solo una decisión de capital ni de operativa real.
3. **No se usan métricas "típicas" de blogs ni de vendedores** como evidencia, punto de partida o
   umbral. Los rendimientos que publican páginas divulgativas o comerciales se citan, como mucho,
   como contexto, marcados como "sin valor de evidencia". Los parámetros salen de la fuente
   académica o del libro original cuando existen; si no, son convenciones nuestras declaradas como
   tales.

## 2. Hipótesis de esta ronda

| Id | Familia | Fuente principal | Estado |
|---|---|---|---|
| CAND-VOLX-NR7-v1 | volatilidad: compresión → expansión | Crabel (1990), NR7 | implementada, sin probar |
| CAND-REGIME-HMM-v1 | régimen de mercado (HMM de 2 estados) | Hamilton (1989); Daniel y Moskowitz (2016) | implementada, sin probar |
| CAND-VWAP-MR-v1 | reversión a VWAP (con tick_volume) | sin evidencia académica encontrada | implementada, sin probar |
| CAND-SESSION-LONDON | ruptura de la sesión de Londres | | **en espera** de la confirmación horaria del domingo |
| H-PAPER-SMACROSS-v1 | cruce de medias de la fase D | | **solo paper trading con datos futuros; sin backtest** |

- Una variante por hipótesis, con parámetros fijados en el código y en `configs/research.yaml`.
  No se prueban variantes alternativas en esta ronda.
- La ruptura de Londres se añadirá con un **anexo fechado a este pre-registro**, escrito antes de
  ejecutar nada con ella, cuando la zona horaria esté confirmada.

## 3. Protocolo del filtro de backtest (igual que la fase E)

Se aplica **sin cambios** el protocolo de [PREREGISTRO_PHASE_E.md](PREREGISTRO_PHASE_E.md):

- La misma división temporal, los mismos 4 folds anuales con purga, el mismo motor, los mismos
  costes y escenarios, y el 0,5 % de riesgo con los límites operativos desactivados.
- Las mismas definiciones de métricas, umbrales estrictos y flexibles, regla de decisión y regla
  de DSR (≥ 0,95 para CANDIDATE_FOR_PAPER).
- El mismo placebo: REF-RANDOM-v1 con las 1 000 semillas ya calculadas en la fase E (mismos
  segmentos y costes). Se reportan las mismas referencias: no operar, aleatoria y cruce de medias.
- La misma sensibilidad: escenarios de costes, año a año, por sesión y con y sin el 2020-03-26.

Particularidades de esta ronda:

- **HMM**: se ajusta una vez por año natural **solo con los días completos anteriores al 1 de
  enero** de ese año, y se aplica con el filtro hacia delante (nunca con el suavizado). En los
  folds es un walk-forward real: cada año de prueba usa un modelo ajustado con la historia previa.
  Hace falta un mínimo de 250 retornos diarios, así que la estrategia no opera en 2017 ni en 2018.
- **VWAP**: `tick_volume` cuenta ticks, no contratos. La hipótesis se evalúa tal cual, con esa
  limitación declarada.

## 4. Número de pruebas y DSR

- Variantes probadas antes de esta ronda: 6 (fase E).
- Esta ronda añade 3 (NR7, REGIME-HMM y VWAP-MR): **N = 9** para el DSR. Si se añade la de
  Londres, **N = 10**. Cualquier variante posterior suma.
- El DSR usa los Sharpe diarios de la prueba final de **todas** las variantes probadas (las 6 de
  la fase E y las nuevas). Las 1 000 semillas del placebo no cuentan como variantes.
- H-PAPER-SMACROSS-v1 es la misma variante que REF-SMACROSS-v1 (ya contada). Su evaluación en
  paper trading usará el N vigente en ese momento.

## 5. Paper trading (evidencia principal)

- Solo con datos posteriores a la fecha de registro de cada hipótesis (para H-PAPER-SMACROSS-v1,
  posteriores al 2026-10-10). Los datos anteriores no cuentan para su veredicto.
- Los criterios concretos (duración mínima, número mínimo de operaciones, métricas y umbrales,
  comparación con lo esperado del backtest) se pre-registrarán en la fase G, **antes de arrancar
  el paper trading**, siguiendo las reglas generales de Juan: al menos 6 meses en tamaño reducido
  si el veredicto previo es INCONCLUSIVE, y estado INCONCLUSIVE si no hay suficientes operaciones.
- La ejecución real sigue deshabilitada. Ningún resultado de paper la activa automáticamente.

## 6. Ambigüedades resueltas antes de ver resultados

1. **"Prueba final parcialmente gastada"**: se mantiene la misma división para poder comparar
   con la ronda 1, pero su resultado solo decide si una hipótesis pasa a paper (sección 1).
2. **Primera ruptura del día en NR7**: si el precio ya cerró fuera del rango del día NR7 antes de
   abrir la ventana de entradas (03:00 NY), ese día no se opera.
3. **Día de negociación**: el día del servidor (de 17:00 a 17:00 NY), que coincide con el cierre
   diario del oro bajo la convención horaria vigente.
4. **Salidas a las 15:45 NY**: las tres candidatas cierran antes de la hora de mayor spread
   (16:00-17:00 NY, COST_MODEL.md). Es una decisión de diseño tomada con la información de costes
   de la fase C, no con resultados de estrategias.
