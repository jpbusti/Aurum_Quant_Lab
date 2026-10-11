# Familias de estrategias de la fase F

**Fecha**: 2026-10-11, antes de ejecutar ninguna variante. Criterios de evaluación en
[PREREGISTRO_PHASE_F.md](PREREGISTRO_PHASE_F.md). Código: `src/aurum/strategies/families.py`.

El objetivo no es encontrar una estrategia ganadora. Es medir si **una familia** muestra una
ventaja que sobreviva a la corrección por pruebas múltiples, o cerrar la línea con datos. Cada
combinación de parámetros es una prueba independiente; no hay paso de optimización ni se
elige "la mejor" para seguir ajustándola.

## Por qué estas tres familias

Juan propuso cuatro familias: tendencia, reversión, volatilidad y calendario. Elijo tres:

- **Tendencia** y **reversión a la media**: son las dos hipótesis opuestas más básicas sobre
  precios. Si una tuviera ventaja en XAUUSD M15, la otra debería perder. Probarlas juntas
  ayuda a interpretar el resultado.
- **Calendario (hora del día)**: es la hipótesis con menos grados de libertad (una hora, un
  lado y una duración). No depende de indicadores. Si existiera un patrón horario persistente
  en el oro, esta rejilla lo cubre de forma exhaustiva.
- **Volatilidad (NR7, expansión de rango) queda fuera.** NR7 dio 23 señales en 2025-2026, y
  sus stops diarios quedan bloqueados casi siempre al 0,5 % con 10 000 USD
  ([AUDIT_POST_E.md](AUDIT_POST_E.md)). Una rejilla de 50 variantes mediría sobre todo el
  bloqueo por capital, no la regla.

No cito estudios externos como evidencia a favor de ninguna familia. La afirmación de que
en otro proyecto se probaron 517 estrategias y ninguna sobrevivió a la corrección FDR
(tickfloor) es de Juan; no he comprobado la fuente.

## Contaminación declarada

Las familias se eligen después de haber visto los resultados de las fases E y de la ronda 2
sobre los mismos datos. En concreto, ya se vio que REF-SMACROSS (tendencia), CAND-VWAP-MR
(reversión) y las estrategias de la sesión de Nueva York no pasaron. La muestra 2017-2026 está
gastada; ver la sección 1 del pre-registro.

## Familia 1: TREND (cruce de medias simples)

- **Lógica central**: al cierre de cada vela M15, compra si la media rápida cruza por encima de
  la lenta y vende si cruza por debajo. Es la regla de REF-SMACROSS.
- **Salida**: stop a k × ATR(14) M15 desde el cierre de la señal; sin objetivo; cierre por
  tiempo a las h horas. Una sola posición a la vez; las señales con posición abierta se
  rechazan y se cuentan.
- **Rejilla** (72 variantes):

  | Parámetro | Valores |
  |---|---|
  | Media rápida (velas M15) | 5, 10, 20, 40 |
  | Media lenta (velas M15) | 50, 100, 200 |
  | Stop k × ATR(14) | 1,5; 3,0 |
  | Cierre por tiempo h (horas) | 8, 24, 72 |

- La combinación de REF-SMACROSS (20/50, stop 2,0 ATR, 24 h) **no** está en la rejilla, porque
  el stop de 2,0 no es uno de sus valores. La rejilla se fijó por espaciado, no para incluirla.

## Familia 2: MEANREV (z-score del cierre)

- **Lógica central**: z = (cierre − media de L cierres) / desviación típica de L cierres
  (poblacional). Compra cuando z cruza hacia abajo −k (z anterior > −k y z actual ≤ −k) y
  vende cuando cruza hacia arriba +k.
- **Salida**: objetivo en la media de L velas en el momento de la señal; stop a s × ATR(14)
  M15; cierre por tiempo a las h horas.
- **Rejilla** (64 variantes):

  | Parámetro | Valores |
  |---|---|
  | L (velas M15) | 20, 50, 100, 200 |
  | Umbral k | 1,5; 2,0; 2,5; 3,0 |
  | Stop s × ATR(14) | 2,0; 4,0 |
  | Cierre por tiempo h (horas) | 4, 24 |

## Familia 3: CALENDAR (hora del día en Nueva York)

- **Lógica central**: al cierre de la vela M15 que termina a las HH:00 de Nueva York, abre una
  posición en un lado fijo y la cierra a las h horas. El precio no interviene en la decisión.
- **Stop de protección**: 3 × ATR(14) M15. Es necesario para dimensionar por riesgo y es lo
  bastante amplio para que la salida sea casi siempre por tiempo.
- **Rejilla** (88 variantes):

  | Parámetro | Valores |
  |---|---|
  | Hora de Nueva York HH | 0-23 salvo 17 y 18 (22 horas) |
  | Lado | compra, venta |
  | Duración h (horas) | 1, 4 |

- Se excluyen las 17:00 NY (la vela que cierra entonces no tiene apertura en los 120 s
  siguientes porque el mercado para de 17:00 a 18:00) y las 18:00 NY (ninguna vela cierra a
  esa hora). Con esas horas, todas las variantes tendrían 0 operaciones.
- Las posiciones abiertas el viernes que cruzan el cierre del fin de semana se cierran en la
  primera barra disponible, como en el resto del motor.

## Implementación y pruebas

- Cada estrategia tiene una versión de referencia (`decide`, con el DataView que solo ve velas
  cerradas) y una versión vectorizada para el screening.
- `tests/unit/test_families.py`: las dos versiones dan exactamente las mismas señales en datos
  sintéticos. Cambiar las velas futuras no altera las señales pasadas. El tamaño de las
  rejillas es 72, 64 y 88.
- En datos reales (2026-01 a 2026-03), 38 variantes (1 de cada 6) dieron señales idénticas con
  las dos versiones (`run.py --check`).

## Total

224 variantes nuevas. Con las 9 anteriores, **N = 233 pruebas** registradas en el proyecto.
