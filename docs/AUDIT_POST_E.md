# Auditoría post-fase E y límite de riesgo del 2 %

**Fecha**: 2026-10-11. Pre-registro: [PREREGISTRO_AUDIT_RISK.md](PREREGISTRO_AUDIT_RISK.md)
(commit e7bf24b, anterior a cualquier cálculo con el 2 %). Código: `experiments/audit_risk/run.py`
(los resultados en `experiments/audit_risk/` no se versionan). Sin desviaciones del pre-registro.
Viabilidad de capital: [PHASE_H_VIABILITY.md](PHASE_H_VIABILITY.md).

> Nada de este informe convierte una variante en estrategia validada. Los resultados con el 2 %
> son una sensibilidad sobre datos ya gastados.

## 1. Errores y limitaciones detectados

1. **Inferencia errónea corregida (ronda 2)**: atribuí primero las 0 operaciones de REGIME-HMM en
   2025-2026 al propio HMM. Lo comprobé antes de enviar el informe: el HMM sí daba días
   tranquilos y el bloqueo era el control de volumen mínimo. Esta auditoría lo confirma con el
   motor: 188 de 188 rechazos en 2025-2026 son por volumen mínimo.
2. **Los rechazos por capital también tocaron a otras variantes**, aunque poco. Con el 0,5 %,
   esto es lo que se perdió por volumen mínimo en la prueba final:

   | Variante | Rechazos | Operaciones ejecutadas |
   |---|---|---|
   | IMOM | 21 | 420 |
   | TREND | 24 (todo el historial) | 697 |
   | ORB | 3 | 453 |
   | VWAP | 94 | 1 007 |
   | NR7 | 16 | 7 |
   | REGIME | 188 | 0 |

   En ORB, IMOM, TREND y VWAP el efecto es pequeño, y con el 2 % sus resultados apenas cambian
   (sección 5). En NR7 y REGIME es decisivo.
3. **Riesgo de ruina con el 2 %**: VWAP-MR pierde el 99,97 % del balance virtual en todo el
   historial y TREND-ATR el 97 %. El motor **no simula el stop-out del bróker**, porque no está
   documentado. En la realidad la cuenta se habría cerrado antes.
4. **La capa 2 es una aproximación**: evalúa cada señal por separado, sin posiciones abiertas, con
   la entrada estimada (apertura de la barra M1 siguiente, spread y slippage base) y con el balance
   inicial. El motor dimensiona con el balance del momento, así que en drawdown el riesgo permitido
   baja y se bloquean más señales.
5. **No hay capital recomendado posible**: ninguna variante está validada. Por la regla de Juan
   no se fuerza una cifra (PHASE_H_VIABILITY.md).
6. **No se detectaron errores de cálculo** en contrato, valor monetario, margen ni comisión
   (sección 3). La prueba del motor sigue verde: 183 unitarias y 9 con terminal y datos.

## 2. Bloqueos de REGIME-HMM: causa

| Causa posible | ¿Es la causa? | Evidencia |
|---|---|---|
| Volumen mínimo de 0,01 lotes | **sí, en combinación** | el motor no redondea hacia arriba, y 0,01 ya supera el riesgo permitido |
| Distancia del stop de 2 ATR diarios | **sí, en combinación** | en 2025-2026, 0,01 lotes arriesgan de 56 a 373 USD (p10 65, mediana 90 y p90 195): stops de unos 56 a 373 USD de precio |
| Límite de riesgo del 0,5 % | **sí, en combinación** | 50 USD sobre 10 000; con el 2 % (200 USD) se desbloquean 173 de 188 |
| Margen insuficiente | no | el margen de 0,01 lotes es de 25 USD como mucho; ningún rechazo por margen |
| Otro error | no | 0 rechazos por otros motivos en 2025-2026 |

El bloqueo lo produce el **cociente**: riesgo de 0,01 lotes con un stop de 2 ATR diarios, dividido
entre el riesgo permitido. El volumen mínimo es el suelo y el stop amplio sube el numerador. Ninguno
de los tres bloquea por separado.

### Cálculo a mano: señal del 2025-01-02 a las 10:00 del servidor (03:00 NY), venta

1. ATR diario (14 días completos, media de rangos verdaderos del 10 al 31 de diciembre de 2024):
   45,48, 51,00, 46,53, 20,89, 25,53, 68,07, 43,48, 42,44, 25,25, 11,33, 24,35, 26,48, 31,79 y
   24,86. Media: **34,82 USD**.
2. Precio de referencia (último cierre M15): 2 636,03. Stop de la venta = 2 636,03 + 2 × 34,82 =
   **2 705,67**.
3. Entrada estimada (venta al bid de apertura de la barra M1 menos 2 puntos de slippage):
   2 636,02 − 0,02 = **2 636,00**. Stop ejecutado con slippage: 2 705,67 + 0,02 = **2 705,69**.
4. Distancia efectiva: 2 705,69 − 2 636,00 = **69,69 USD** de precio.
5. Valor de 0,01 lotes: 100 onzas × 0,01 = 1 onza, así que **1 USD por cada 1,00 de precio**
   (verificado con `order_calc_profit` de MT5). Riesgo del precio: 69,69 USD.
6. Comisión de ida y vuelta: 3,50 × 0,01 × 2 = **0,07 USD**. Riesgo total de 0,01 lotes:
   **69,76 USD**, la misma cifra que el rechazo registrado por el motor.
7. **Con el 0,5 %**: permitido 0,005 × 10 000 = **50 USD**. Como 69,76 > 50, el volumen calculado
   sería 50 / (69,69 × 100 + 7) = 0,0072 lotes, que se redondea hacia abajo a 0,00 < 0,01.
   **Bloqueada.**
8. **Con el 2 %**: permitido 0,02 × 10 000 = **200 USD**. Volumen = 200 / 6 976 = 0,0287, que se
   redondea hacia abajo a **0,02 lotes**, con un riesgo de 0,02 × 6 976 = **139,52 USD** ≤ 200.
   Margen de 0,02 lotes: 0,02 × 100 × 2 636,02 / 200 = 26,36 USD. **Ejecutable.**

## 3. Verificación de especificaciones (MT5, 2026-10-11, cuenta DEMO ICMarketsSC-Demo)

| Elemento | Valor en MT5 | Comprobación |
|---|---|---|
| Contrato | 100 onzas por lote | `trade_contract_size` = 100 |
| Valor por movimiento | 1 USD por 0,01 de precio y lote (`tick_value` 1,0, `tick_size` 0,01) | `order_calc_profit`: +1,00 de precio da +1,00 USD con 0,01 lotes, +10 con 0,1 y +100 con 1 lote |
| Volumen | mínimo 0,01, paso 0,01 | igual que el motor |
| Margen | apalancamiento 1:200, modo FOREX | `order_calc_margin` a 4 195,36: 20,98 USD (0,01), 209,77 (0,1) y 2 097,68 (1); el motor da lo mismo con volumen × 100 × precio / 200 |
| Comisión | 3,50 USD por lado y lote | verificada por Juan en el portal; no la expone la API |
| Spread | flotante; el modelo usa mínimo de la barra + exceso por hora | COST_MODEL.md; en la señal anterior, 18,96 puntos (0,19 USD), irrelevante frente a 69 USD |
| Slippage | 2 puntos base (supuesto, no medido) | backtest.yaml |
| Swap | largo −57,03 y corto +39,767 puntos por lote y noche, triple el miércoles | `swap_rollover3days` = 3 |

## 4. Capa 1 y capa 2 por variante

Capa 1: señales generadas (independientes del capital). Capa 2: señales cuyo riesgo con 0,01
lotes cabe en el límite sobre 10 000 USD y cuyo margen cabe en el balance, sin el efecto de
posiciones abiertas.

| Variante | Capa 1, total | Capa 2 con 0,5 % | Capa 2 con 2 % | Desbloqueadas | Capa 1, 2025-26 | Capa 2 con 0,5 %, 2025-26 | Capa 2 con 2 %, 2025-26 | Desbloqueadas, 2025-26 |
|---|---|---|---|---|---|---|---|---|
| REF-NOTRADE-v1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| REF-RANDOM-v1 | 1 445 | 1 437 | 1 443 | 6 | 301 | 295 | 301 | 6 |
| REF-SMACROSS-v1 | 5 187 | 5 141 | 5 153 | 12 | 918 | 897 | 909 | 12 |
| CAND-ORB-NY-v1 | 2 449 | 2 442 | 2 445 | 3 | 457 | 453 | 456 | 3 |
| CAND-IMOM-NY-v1 | 2 362 | 2 341 | 2 361 | 20 | 441 | 420 | 440 | 20 |
| CAND-TREND-ATR-v1 | 9 072 | 9 036 | 9 070 | 34 | 1 654 | 1 620 | 1 654 | 34 |
| CAND-VOLX-NR7-v1 | 135 | 119 | 135 | 16 | 23 | 7 | 23 | 16 |
| CAND-REGIME-HMM-v1 | 1 268 | 731 | 1 253 | **522** | 188 | **0** | 173 | **173** |
| CAND-VWAP-MR-v1 | 22 845 | 22 729 | 22 826 | 97 | 4 814 | 4 716 | 4 813 | 97 |

Las diferencias entre capa 1 y capa 2 con el 2 % que no son de capital son: "sin precio" (2 en
RANDOM, 34 en SMACROSS, 2 en TREND y 15 en VWAP) y "stop inválido" (4 en ORB y 4 en VWAP). Las
operaciones reales del motor son menos que la capa 2, porque se rechazan señales con una posición
ya abierta (por ejemplo, 3 713 de VWAP en 2025-2026).

## 5. Motor con el 0,5 % y con el 2 % (balance de 10 000 USD, escenario base, prueba final 2025-2026)

| Variante | Riesgo | Operaciones | PF | IC90 inferior | DD máx. | Sharpe | Sortino | Calmar | Expectancy | Neto (USD) |
|---|---|---|---|---|---|---|---|---|---|---|
| ORB-NY | 0,5 % | 453 | 0,90 | 0,68 | 28,9 % | −0,62 | −1,41 | −0,32 | −0,067 R | −1 515 |
| ORB-NY | 2 % | 456 | 0,91 | 0,70 | 78,2 % | −0,61 | −1,40 | −0,54 | −0,073 R | −6 050 |
| IMOM-NY | 0,5 % | 420 | 0,99 | 0,81 | 2,0 % | −0,07 | −0,09 | −0,07 | −0,000 R | −23 |
| IMOM-NY | 2 % | 440 | 1,08 | 0,89 | 8,9 % | 0,44 | 0,62 | 0,38 | 0,009 R | +661 |
| TREND-ATR | 0,5 % | 697 | 1,00 | 0,88 | 13,0 % | 0,08 | 0,12 | 0,02 | −0,008 R | +48 |
| TREND-ATR | 2 % | 709 | 0,97 | 0,85 | 53,6 % | −0,07 | −0,11 | −0,29 | −0,008 R | −2 605 |
| NR7 | 0,5 % | 7 | 0,36 | 0,00 | 0,8 % | −0,74 | −0,87 | −0,44 | −0,189 R | −64 |
| NR7 | 2 % | 23 | 0,77 | 0,31 | 3,8 % | −0,38 | −0,52 | −0,38 | −0,075 R | −258 |
| REGIME-HMM | 0,5 % | 0 | – | – | 0 % | – | – | – | – | 0 |
| REGIME-HMM | 2 % | 173 | 1,26 | 0,90 | 5,0 % | 0,84 | 1,20 | 0,77 | 0,026 R | +690 |
| VWAP-MR | 0,5 % | 1 007 | 0,90 | 0,81 | 24,2 % | −0,97 | −1,26 | −0,53 | −0,053 R | −2 294 |
| VWAP-MR | 2 % | 1 023 | 0,88 | 0,78 | 76,4 % | −1,00 | −1,29 | −0,68 | −0,052 R | −9 379 |
| REF-SMACROSS | 0,5 % | 601 | 1,25 | 1,03 | 10,9 % | 1,53 | 2,79 | 2,67 | 0,201 R | +5 298 |
| REF-SMACROSS | 2 % | 605 | 1,21 | 0,99 | 39,6 % | 1,61 | 2,98 | 4,19 | 0,200 R | +34 545 |
| REF-RANDOM | 0,5 % | 265 | 0,78 | 0,63 | 12,5 % | −1,31 | −1,67 | −0,46 | −0,102 R | −1 010 |
| REF-RANDOM | 2 % | 271 | 0,77 | 0,62 | 46,0 % | −1,32 | −1,68 | −0,54 | −0,088 R | −4 372 |

**REGIME-HMM con el 2 %, según los umbrales pre-registrados de la fase E** (solo como
sensibilidad):

- Estrictas: falla 3 de 7 (IC90 inferior 0,90 ≤ 1,0; Sharpe 0,84 ≤ 1,0; 173 < 300 operaciones).
- Flexibles: falla la expectancy (0,026 R ≤ 0,10).
- Sería REJECTED.
- En los demás periodos con el 2 %: in-sample PF 1,07 y validación **0,92** (DD 12 %). No es una
  ventaja estable.

**Drawdown: el 2 % es 4 veces el riesgo del 0,5 %, no el doble.**

| Variante | DD con 0,5 % | DD con 2 % | Factor |
|---|---|---|---|
| NR7 (2025-2026) | 0,8 % | 3,8 % | 4,6 |
| IMOM (2025-2026) | 2,0 % | 8,9 % | 4,4 |
| TREND (2025-2026) | 13,0 % | 53,6 % | 4,1 |
| SMACROSS (2025-2026) | 10,9 % | 39,6 % | 3,6 |
| VWAP (2025-2026) | 24,2 % | 76,4 % | 3,2 |
| ORB (2025-2026) | 28,9 % | 78,2 % | 2,7 |
| Todo el historial | | | 1,2 a 4,8 (VWAP llega al 100 %) |

El factor ronda 4 cuando el drawdown es pequeño y baja cuando es grande, porque las pérdidas se
componen y el drawdown no puede pasar del 100 %. Con el 2 %, 6 de las 8 variantes que operan
superan el umbral del 20 % de drawdown en algún periodo, y la referencia de cruce de medias
llega al **92 % en validación**.

## 6. Clasificación de las 9 variantes

| Variante | Clasificación | Motivo |
|---|---|---|
| CAND-ORB-NY-v1 | **REJECTED por rendimiento** | 453 operaciones; PF 0,90; igual con el 2 % (0,91) |
| CAND-IMOM-NY-v1 | **REJECTED por rendimiento** | 420 operaciones; PF 0,99; con el 2 %, 1,08 e IC90 inferior 0,89 |
| CAND-TREND-ATR-v1 | **REJECTED por rendimiento** | 697 operaciones; PF 1,00; con el 2 %, 0,97 |
| CAND-VWAP-MR-v1 | **REJECTED por rendimiento** | 1 007 operaciones; PF < 1 todos los años, con ambos límites |
| CAND-VOLX-NR7-v1 | **Rechazada por evidencia insuficiente** | 23 señales en 2025-2026 (7 ejecutadas con el 0,5 %); ni con el 2 % hay muestra (PF 0,77 con 23 operaciones) |
| CAND-REGIME-HMM-v1 | **No evaluada por bloqueo operativo** (con el 0,5 % y 10 000 USD) | 0 de 188 señales ejecutables; con el 2 %, la sensibilidad tampoco pasa (sección 5) |
| REF-NOTRADE-v1 | referencia | sin operaciones por diseño |
| REF-RANDOM-v1 | referencia (placebo) | PF 0,78; base del placebo de 1 000 semillas |
| REF-SMACROSS-v1 | referencia; hipótesis solo para paper (H-PAPER-SMACROSS-v1) | cumple las estrictas en 2025-2026 con el 0,5 %, pero validación PF 0,83 y DD 42 %; con el 2 %, DD 92 % en validación |

## 7. Estado de la muestra (data snooping)

| Periodo | Visto en | Uso que se le ha dado | Estado |
|---|---|---|---|
| 2017-04 a 2022 | fase E, ronda 2 y auditoría | descriptivo; vimos resultados de 9 variantes y 2 tamaños | **gastado** |
| 2023-2024 | fase E, ronda 2 y auditoría | validación, vista para 9 variantes | **gastado** |
| 2025 a 2026-10-09 | fase E (veredicto), ronda 2 (filtro) y auditoría (2 tamaños) | decidió los veredictos de 6 candidatas; la ronda 2 y el 2 % se decidieron después de verlo | **gastado** |
| Ticks de 2026-04 a 2026-10 | fases C y D | calibrar costes (no estrategias) | usado para costes |
| Datos posteriores a 2026-10-09 | nadie | – | **única muestra limpia** |

Decisiones tomadas con conocimiento de los datos:

- Las prioridades de la ronda 2 se eligieron tras ver la fase E.
- El 2 % se propuso tras ver que REGIME-HMM estaba bloqueado.
- El cruce de medias se marcó como interesante tras ver 2025-2026.

Cualquier resultado nuevo sobre 2017-2026 queda contaminado por estas decisiones. **El
resultado de REGIME-HMM con el 2 % es post hoc.**

## 8. Recomendación

**No hay ninguna variante que justifique paper trading por sus resultados de backtest.** Las
opciones, en orden:

1. **Paper trading solo de lo ya pre-registrado** (H-PAPER-SMACROSS-v1, cruce de medias) con el
   **0,5 %**, sobre datos futuros. Su objetivo no es aprobar la estrategia, sino medir costes y
   slippage reales y comprobar si el patrón de 2026 se mantiene. Con el 2 % su drawdown histórico
   (92 % en validación) es inaceptable.
2. **Cerrar esta línea de investigación por backtest**: hemos probado 9 variantes intradía, sin
   ventaja, y el historial está gastado. Más hipótesis sobre los mismos datos solo aumentan el
   sesgo de selección.
3. REGIME-HMM con el 2 % **no** debería pasar a paper: falla 3 estrictas y la expectancy, tiene
   validación negativa y es un resultado post hoc. Si Juan quisiera probarla igualmente, tendría
   que pre-registrarla como hipótesis nueva solo con datos futuros, sabiendo esto.

El límite del 2 % queda documentado como más agresivo y más cercano a la ruina. No se recomienda
como configuración por defecto.
