# Viabilidad de capital (fase H, versión preliminar)

**Fecha**: 2026-10-11. Fuente: auditoría post-fase E ([AUDIT_POST_E.md](AUDIT_POST_E.md), código
`experiments/audit_risk/run.py`). Especificaciones verificadas en MT5 (cuenta DEMO ICMarketsSC-Demo,
XAUUSD, apalancamiento 1:200). **Ninguna variante está validada**, así que este documento describe
lo que exige el instrumento y cada regla. No es una recomendación de capital para operar.

## Datos del instrumento

- 0,01 lotes = 1 onza: **1 USD por cada 1,00 USD de movimiento del oro**.
- Margen de 0,01 lotes = 0,01 × 100 × precio / 200. A 4 195,36 son **20,98 USD** (MT5). En
  2025-2026 el máximo entre las señales fue de 27,72 USD.
- Comisión de 0,01 lotes ida y vuelta: 0,07 USD. Spread medio de unos 9 puntos (0,09 USD) por
  operación de 0,01 lotes. Slippage base supuesto: 2 puntos por lado.
- El volumen se redondea siempre hacia abajo. Si 0,01 lotes arriesgan más de lo permitido, no se
  opera.

## 1. Capital mínimo técnico (para abrir 0,01 lotes)

Hace falta el **margen: unos 21 a 28 USD** a los precios de 2025-2026. Pero con eso la cuenta no
soporta ninguna pérdida: el nivel de stop-out del bróker no está documentado en la API y no se ha
medido. Para mantener abierta una posición hasta el stop hace falta, como mínimo, margen + riesgo
hasta el stop (siguiente tabla).

## 2 y 3. Capital mínimo compatible con el riesgo (0,5 % y 2 %)

Capital necesario para que el riesgo de 0,01 lotes (stop, slippage y comisión) quepa en el límite:
riesgo de 0,01 lotes / límite. Señales de 2025-2026.

| Variante | Riesgo de 0,01 lotes: mediana / p90 / máximo (USD) | Capital al 0,5 %, p50 / p90 | Capital al 2 %, p50 / p90 |
|---|---|---|---|
| CAND-ORB-NY-v1 | 9,33 / 22,76 / 74,82 | 1 866 / 4 552 | 467 / 1 138 |
| CAND-IMOM-NY-v1 | 18,65 / 38,90 / 218,31 | 3 730 / 7 780 | 933 / 1 945 |
| CAND-TREND-ATR-v1 | 14,43 / 28,75 / 126,67 | 2 886 / 5 750 | 722 / 1 438 |
| CAND-VOLX-NR7-v1 | 61,13 / 88,44 / 112,49 | 12 226 / 17 688 | 3 057 / 4 422 |
| CAND-REGIME-HMM-v1 | 89,87 / 194,51 / 373,16 | 17 974 / 38 902 | 4 494 / 9 726 |
| CAND-VWAP-MR-v1 | 12,85 / 26,09 / 119,90 | 2 570 / 5 218 | 643 / 1 305 |
| REF-SMACROSS-v1 | 13,47 / 26,74 / 117,98 | 2 694 / 5 348 | 674 / 1 337 |
| REF-RANDOM-v1 | 14,87 / 27,79 / 158,68 | 2 974 / 5 558 | 744 / 1 390 |

Para ejecutar el 100 % de las señales de 2025-2026, REGIME-HMM necesitaría **74 632 USD al
0,5 %** o **18 658 USD al 2 %**.

## 4. Capital recomendado

**No se calcula.** Exige una estrategia que haya pasado la validación (pre-registro de la fase E y
skill de riesgo). Ninguna lo ha hecho. Dar una cifra sería presentar como viable algo que no
tiene ventaja demostrada.

## 5. Viabilidad por balance: señales de 2025-2026 ejecutables (capa 2)

Formato: ejecutables / señales.

| Variante | 200 USD, 0,5 % | 200 USD, 2 % | 1 000 USD, 0,5 % | 1 000 USD, 2 % | 10 000 USD, 0,5 % | 10 000 USD, 2 % | 50 000 USD, 0,5 % | 50 000 USD, 2 % |
|---|---|---|---|---|---|---|---|---|
| ORB-NY (457) | 2 | 57 | 98 | 394 | 453 | 456 | 456 | 456 |
| IMOM-NY (441) | 0 | 0 | 0 | 242 | 420 | 440 | 441 | 441 |
| TREND-ATR (1 654) | 0 | 0 | 15 | 1 210 | 1 620 | 1 654 | 1 654 | 1 654 |
| NR7 (23) | 0 | 0 | 0 | 0 | 7 | 23 | 23 | 23 |
| REGIME-HMM (188) | 0 | 0 | 0 | 0 | 0 | 173 | 182 | 188 |
| VWAP-MR (4 814) | 0 | 33 | 141 | 3 808 | 4 716 | 4 813 | 4 813 | 4 813 |
| SMACROSS (918) | 0 | 13 | 42 | 706 | 897 | 909 | 909 | 909 |
| RANDOM (301) | 0 | 0 | 4 | 205 | 295 | 301 | 301 | 301 |

Lectura:

- **200 USD**: **no viable**. Al 0,5 % el riesgo permitido es de 1 USD y casi nada cabe. Al 2 %
  (4 USD) solo cabe una minoría de señales con stop muy corto. Además, el margen de 0,01 lotes ya
  es el 10-14 % de la cuenta.
- **1 000 USD**: no viable al 0,5 % (5 USD). Al 2 % (20 USD) cabe entre el 55 % y el 86 %
  de las señales intradía, pero ninguna de NR7 ni de REGIME-HMM. Con 0,01 lotes y ese
  capital, el tamaño no se puede ajustar: casi todo opera al mínimo.
- **10 000 USD**: viable al 0,5 % para las reglas intradía. NR7 y REGIME-HMM, con stops diarios,
  quedan bloqueadas casi por completo. Al 2 % cabe casi todo.
- **50 000 USD**: viable con ambos límites para todas las variantes.

Ser viable significa poder ejecutar la señal, **no** que la estrategia sea rentable: ninguna
lo es en las pruebas.

## Riesgo del 2 % frente al 0,5 %

- El 2 % es **4 veces** el riesgo por operación del 0,5 %.
- Drawdowns medidos en 2025-2026: de 2,7 a 4,6 veces mayores. En todo el historial, de 1,2 a 4,8
  veces, con VWAP-MR al 100 % y TREND-ATR al 97 %.
- 10 pérdidas seguidas dejan el balance en el 81,7 % al 2 % y en el 95,1 % al 0,5 %.
- El stop-out del bróker no está modelado. El 2 % es más agresivo y está más cerca de la ruina.

## Pendiente para la fase H definitiva

- Medir el nivel de stop-out y el margen de mantenimiento de la cuenta.
- Una estrategia validada sobre la que calcular el capital recomendado con su drawdown y sus
  escenarios de estrés.
- Costes y slippage reales del paper trading.
