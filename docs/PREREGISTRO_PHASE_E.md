# Pre-registro de la fase E

**Fecha**: 2026-10-10. Escrito y guardado en git **antes de ejecutar ningún backtest** de las
estrategias. Hasta este commit no se ha calculado ninguna métrica de ninguna estrategia sobre los
datos reales. Las únicas ejecuciones previas del motor con datos reales fueron las de la fase C:
señales mecánicas sin relación con estas estrategias y la medición de la cotización del
2020-03-26 (docs/BACKTEST_ENGINE.md).

Lo que figura aquí no se cambia después de ver resultados. Si hiciera falta un cambio, se
documentará como desviación, con su motivo, y los resultados se mostrarán con y sin él.

Base: especificación de Juan (2026-10-10) y skill `aurum-methodology`. Las ambigüedades encontradas
y cómo se resuelven están en la sección 9.

## 1. Estrategias evaluadas

Las 6 variantes de la fase D, con los parámetros de `configs/research.yaml` (commit 997d195),
sin ningún cambio:

- Candidatas: CAND-ORB-NY-v1, CAND-IMOM-NY-v1 y CAND-TREND-ATR-v1.
- Referencias: REF-NOTRADE-v1, REF-RANDOM-v1 (más el placebo de 1000 semillas, sección 7) y
  REF-SMACROSS-v1.

No hay selección previa: las tres candidatas pasan a todos los periodos, incluida la prueba final.

## 2. División temporal (hora del servidor)

| Periodo | Desde | Hasta (incluido) | Uso |
|---|---|---|---|
| In-sample (investigación) | 2017-04-06 | 2022-12-31 | descriptivo |
| Validación | 2023-01-01 | 2024-12-31 | descriptivo; no se descarta ninguna candidata aquí |
| Prueba final (OOS) | 2025-01-01 | 2026-10-09 | **veredicto** |

- El historial validado empieza el 2017-04-06 01:00 (exclusión de la fase B) y termina el
  2026-10-09 23:55. Cubre los tres periodos y no hace falta ajustar las fechas.
- Hay **datos de 2017 a 2022** que nunca se han usado para fijar parámetros: los parámetros salen
  de las fuentes y de convenciones (fase D).

## 3. Walk-forward

- Folds con ventana de entrenamiento expansiva y prueba anual, según la especificación:

| Fold | Entrenamiento | Prueba |
|---|---|---|
| 1 | 2017-04-06 a 2022-12-31 | 2023 |
| 2 | 2017-04-06 a 2023-12-31 | 2024 |
| 3 | 2017-04-06 a 2024-12-31 | 2025 |
| 4 | 2017-04-06 a 2025-12-31 | 2026-01-01 a 2026-10-09 |

- **No se ajusta nada en las ventanas de entrenamiento**: los parámetros están fijados desde la
  fase D. La ventana de entrenamiento solo aporta historia para los indicadores (warm-up), que se
  calculan con barras cerradas anteriores a cada decisión. Por eso el walk-forward equivale a
  evaluar cada año de prueba por separado.
- **Purga**: cada segmento evaluado (cada año) se simula con su propio balance inicial
  (10 000 USD virtuales) y solo admite señales cuyo cierre por tiempo máximo cae dentro del
  segmento (`decision_time + max_hold_s <= fin del segmento`). Ninguna operación cruza de un
  segmento al siguiente. ORB y la aleatoria pierden así como mucho la última sesión del año.
- **Embargo**: 0. Justificación: no hay ninguna estimación en el entrenamiento, así que no hay
  etiquetas de entrenamiento que puedan solaparse con la prueba. La purga ya impide que una misma
  operación cuente en dos segmentos.
- Se reportan las métricas **por fold** (PF incluido) y agregadas. Los folds 3 y 4 forman la prueba
  final; los folds 1 y 2, la validación.

## 4. Simulación

- Motor de la fase C (commit 01b9d40), ejecución sobre M1, `configs/backtest.yaml` y
  `configs/cost_model.yaml` sin cambios.
- Tamaño de posición: modo riesgo, **0,5 % del balance** por operación (`configs/risk.yaml`).
- **Límites de pérdida diaria y de drawdown desactivados** durante la evaluación. Son controles
  operativos: si cortaran la simulación, el drawdown medido sería artificialmente menor.
- Escenario del veredicto: **base**. Adverso y estrés se reportan como sensibilidad (sección 8).
- Las señales se generan una sola vez sobre todo el historial (causalmente) y cada segmento usa
  las que caen dentro de él.

## 5. Métricas (definiciones)

Se calculan sobre las operaciones y la curva de equity de cada segmento. Los agregados (validación,
prueba final y total de los folds) encadenan los retornos diarios de sus segmentos.

| Métrica | Definición |
|---|---|
| PF | suma de beneficios netos de las operaciones ganadoras / suma absoluta de las perdedoras |
| IC90 inferior del PF | percentil 5 del PF en un **bootstrap por bloques circular** de las operaciones en orden temporal: bloque = ceil(n^(1/3)), 5 000 réplicas, semilla 20261010 |
| DD | drawdown máximo de la equity diaria (cierre del día del servidor, con posiciones valoradas a mercado), en % desde el máximo |
| Sharpe | media / desviación de los retornos diarios de equity × √252; los días sin barras no cuentan; tasa libre de riesgo 0 |
| Sortino | media de los retornos diarios / desviación a la baja (raíz de la media de min(r, 0)² sobre todos los días) × √252 |
| Calmar | rentabilidad anual compuesta (CAGR) / DD máximo; años = días naturales del segmento / 365,25 |
| Operaciones | número de operaciones cerradas en el segmento |
| Expectancy | media del múltiplo R neto (resultado neto / riesgo inicial de la operación, con costes) |
| SQN | √min(N, 100) × media(R) / desviación(R) (convención de Van Tharp, con N limitado a 100) |
| Recovery factor | beneficio neto / DD máximo en USD |
| Ulcer Index | raíz de la media de los drawdowns diarios al cuadrado, en % |

## 6. Umbrales y criterio de decisión (sobre la prueba final, escenario base)

**Estrictas** (todas obligatorias para CANDIDATE_FOR_PAPER): PF ≥ 1,15; IC90 inferior del PF > 1,0;
DD < 20 %; Sharpe > 1,0; Sortino > 1,0; Calmar > 0,5; al menos 300 operaciones.

**Flexibles**: Expectancy > 0,10 R; SQN > 1,5; Recovery factor > 2,0; Ulcer Index < 10.

| Veredicto | Condición |
|---|---|
| CANDIDATE_FOR_PAPER | cumple las 7 estrictas (y la regla de la sección 7) |
| INCONCLUSIVE | falla 1 o 2 estrictas y cumple las 4 flexibles |
| REJECTED | falla más de 2 estrictas, o falla alguna estricta y alguna flexible |

- Las recomendaciones de paper trading de la especificación (tamaño y duración) son de Juan y se
  decidirán en las fases F y G. Esta evaluación no las modifica.
- Ningún veredicto es una garantía de rentabilidad futura.

## 7. Referencias, placebo y DSR

- **Superar las referencias** (prueba final, escenario base) significa:
  - frente a REF-NOTRADE-v1: beneficio neto > 0;
  - frente a REF-SMACROSS-v1: PF y expectancy mayores;
  - frente a REF-RANDOM-v1: PF por encima del **percentil 95** de los 1 000 placebos (p < 0,05,
    con p = fracción de placebos con PF mayor o igual).
- **Placebo**: la referencia aleatoria se ejecuta con **1 000 semillas** (1 a 1000, más la semilla
  oficial 20261010 como REF-RANDOM-v1), con las mismas restricciones, costes, tamaño y segmentos.
  Se reportan la distribución de PF, expectancy y beneficio neto, y el p-valor de cada candidata.
- **Implementación del azar**: para poder correr 1 000 semillas, el generador de REF-RANDOM-v1
  pasa a ser un hash determinista (splitmix64) de (semilla, instante de decisión), vectorizable. Las
  reglas de la referencia no cambian (probabilidad, ventana, stops y objetivos). Este cambio se
  hace **antes de ver ningún resultado** y queda en el mismo commit que este documento.
- **DSR** (Bailey y López de Prado, 2014): se calcula para cada candidata con el Sharpe diario de
  la prueba final, la asimetría y la curtosis de sus retornos y N = número total de variantes
  probadas en el registro (6). Es la probabilidad de que el Sharpe verdadero sea positivo
  descontando el número de pruebas.
- **Regla añadida por la metodología del proyecto** (skill `aurum-methodology`): una candidata que
  cumpla las 7 estrictas pero tenga DSR < 0,95 queda como **INCONCLUSIVE** y se señala para que
  decida Juan.
- **PBO**: no se calcula. Requiere una búsqueda entre muchas configuraciones (CSCV) y aquí no se
  ha buscado nada: 3 reglas fijas. Se declara "no aplicable" en lugar de inventar una cifra.

## 8. Sensibilidad (se reporta; no cambia el veredicto, salvo lo indicado)

- **Costes**: escenarios base, adverso y estrés para todas las estrategias y periodos.
- **Cotización del 2020-03-26 10:23**: el periodo in-sample se simula con los datos reales y con
  ese minuto excluido. Para cada estrategia se indica si tenía una posición abierta en ese minuto y
  cuánto cambia el resultado. No afecta a la prueba final.
- **Año a año**: métricas de 2017 a 2026 por separado.
- **Por sesión**, según la hora de entrada en Nueva York (servidor − 7 h): Asia de 18:00 a 03:00;
  Londres de 03:00 a 08:00; Nueva York de 08:00 a 15:00; cierre de 15:00 a 17:00. Es una división
  aproximada: no corrige los días en que los horarios de verano de Reino Unido y EE. UU. no
  coinciden, y depende de la convención horaria pendiente de confirmación en vivo.

## 9. Ambigüedades resueltas antes de ver resultados

1. **Folds que prueban sobre la prueba final**: los folds 3 y 4 (2025 y 2026) caen dentro del OOS.
   Como no se ajusta nada en ningún fold, eso no contamina la prueba final. Los folds 3 y 4 se
   reportan como parte de ella y el veredicto usa el agregado de ambos.
2. **"Selección limitada" en validación**: no hay nada que seleccionar. Las 3 candidatas siguen a la
   prueba final sea cual sea su validación, para no introducir un sesgo de selección.
3. **300+ operaciones**: se exigen en la prueba final, donde se decide el veredicto.
4. **IC90 del PF**: intervalo bilateral del 90 %; su límite inferior es el percentil 5 del bootstrap.
   Por bloques, porque las operaciones de días seguidos no son independientes.
5. **DD**: sobre la equity diaria valorada a mercado, no solo sobre operaciones cerradas.
6. **Sesiones**: definidas en hora de Nueva York para no depender de la conversión a UTC.
7. **2020-03-26**: no está en la prueba final. Su sensibilidad se mide en el in-sample y no cambia
   el veredicto.

## 10. Registro

- Al ejecutar la evaluación, `configs/research.yaml` pasará `variants_tested` a 1 para cada una de
  las 6 variantes evaluadas (`variants_tested_total: 6`). Las 1 000 semillas del placebo se
  registran como placebo, no como variantes candidatas.
- Resultados en `docs/PHASE_E_RESULTS.md` y veredictos en `docs/STRATEGY_RESEARCH.md`,
  aprobados o no.
