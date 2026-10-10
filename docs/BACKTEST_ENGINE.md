# Motor de backtesting de AURUM Quant Lab

Fase C. Código en `src/aurum/backtesting/`, `src/aurum/risk/`, `src/aurum/features/align.py`,
`src/aurum/strategies/base.py` y `src/aurum/timeutils.py`. Costes en [COST_MODEL.md](COST_MODEL.md).
El motor no contiene estrategias de inversión ni optimiza nada.

## Flujo

```text
datos validados (require_usable + exclusiones de data.yaml)
  → estrategia: en el cierre de cada vela del timeframe de señal recibe un DataView
    con solo barras cerradas y devuelve (lado, stop, objetivo, cierre por tiempo) o nada
  → Signal(decision_time, info_time, ...)
  → Backtester.run(barras M1, señales): ejecución, costes, riesgo
  → operaciones, curva de equity, señales rechazadas con motivo, estadísticas
```

## Alineación de timeframes y sesiones

- Todas las barras se identifican por su **hora de apertura en hora del servidor**. Una barra
  de duración d abierta en t está disponible en **t + d**.
- Una decisión en el instante T solo ve barras con t + d <= T, en todos los timeframes
  (`features.align.last_closed_index`, `DataView.closed`). Una señal M15 se decide al cierre de
  su vela. La H1 en curso no se ve hasta que cierra: a las 10:15, 10:30 y 10:45 la última H1
  disponible es la de las 09:00.
- M5 dentro de una señal M15 sigue la misma regla. El motor no ejecuta en una barra M5 o M1
  anterior al instante de decisión.
- Los timeframes del servidor comparten rejilla (las H1 empiezan en hora en punto y las M15 en
  :00, :15, :30, :45), y los nativos coinciden al 100 % con los reconstruidos desde M1 (fase B).
- Las sesiones no se rellenan: tras la pausa diaria (00:00-01:00 del servidor) o un fin de
  semana, la información disponible es la última barra cerrada antes del cierre.
- Cada señal lleva `info_time`, el cierre de la barra más reciente consultada. Si supera
  `decision_time`, el motor la rechaza como fuga.
- Conversión a UTC: `timeutils.server_to_utc` (Nueva York + 7 h, con el horario de verano de
  EE. UU.). Falla en lugar de adivinar en las horas ambiguas, que caen en domingo con el mercado
  cerrado. **Pendiente de confirmación en vivo**; el motor no la necesita porque trabaja en hora
  del servidor.

## Ejecución

| Regla | Detalle |
|---|---|
| Precio de las barras | bid (verificado con ticks) |
| Ask | bid + spread estimado del minuto según el escenario |
| Entrada | apertura de la primera barra M1 con hora >= decision_time; compra al ask + slippage y venta al bid − slippage |
| Señal sin precio | si la primera barra llega más de 120 s después, se rechaza (cierres, huecos) |
| Stop y objetivo | un largo se compara con el bid y un corto con el ask, como en MT5 |
| Validez | stop u objetivo al otro lado del precio de ejecución: se rechaza la señal |
| Stop | se ejecuta al precio del stop con slippage en contra |
| Objetivo | se ejecuta al precio del objetivo, sin mejora ni slippage (orden límite) |
| Hueco en la apertura | más allá del stop: se cierra a la apertura con slippage (peor que el stop); más allá del objetivo: al objetivo |
| Stop y objetivo en la misma barra | se usan los ticks del minuto si reproducen su máximo y mínimo; si no, se asume que salta el stop |
| Cierre por tiempo | apertura de la primera barra tras `max_hold_s`, con slippage |
| Final de los datos | cierre al último precio (bid o ask) con slippage, marcado "fin de datos" |
| Posiciones | una a la vez; las señales que llegan con posición abierta se rechazan |

## Contabilidad

- P&L en USD (divisa de beneficio del símbolo y de la cuenta, sin conversión). 1.0 de precio
  vale 100 USD por lote.
- Comisión: al abrir y al cerrar, `3,50 x volumen` cada vez. El balance la descuenta en el
  momento y la operación guarda la suma de los dos lados.
- Swap: en cada cambio de día del servidor con posición abierta. Cuentan las noches que terminan
  de lunes a viernes, y la del miércoles vale triple (`swap_rollover3days` del bróker), así que
  una semana completa suma 7 noches.
- Equity por barra M1 = balance + resultado latente al bid (largos) o al ask (cortos).
- Comprobación: balance final = inicial + suma neta de las operaciones = último punto de equity
  (`ledger_matches_equity`).
- Margen: `volumen x 100 x precio / apalancamiento` (coincide con `order_calc_margin` del
  terminal). Si supera el balance, la señal se rechaza.

## Riesgo (`configs/risk.yaml`, valores provisionales)

- Tamaño por riesgo: `volumen = riesgo permitido / (distancia efectiva al stop x 100 + comisión
  ida y vuelta)`, redondeado **hacia abajo** al paso de 0,01. La distancia efectiva incluye el
  spread de entrada y el slippage de entrada y salida.
- Si el volumen queda por debajo de 0,01, **no se opera** y se registra el motivo.
- Límite diario: con una pérdida del 2 % desde la equity al inicio del día del servidor, no se
  abren más posiciones ese día. Drawdown máximo: con una caída del 10 % desde el máximo, se
  detienen las entradas.
- El balance virtual de 10 000 USD sirve para simular; no es una recomendación de capital
  (fase H). Hay modo de volumen fijo para comparar sin depender del capital.

## Pruebas (`pytest`: 112 unitarias; `pytest -m "mt5 or data"`: 9 con terminal y datos reales)

| Requisito | Prueba (`tests/unit/test_engine.py` salvo que se indique) |
|---|---|
| Operación ganadora calculada a mano | `test_winning_long_pnl_by_hand` |
| Operación perdedora | `test_losing_long_with_stop_slippage` |
| Stop y objetivo | `test_short_stop_hit_on_ask`, `test_short_uses_bid_to_open_and_ask_to_close` |
| Apertura y cierre al precio correcto | `test_signal_executes_at_next_bar_open_not_before`, `test_gap_through_stop_exits_at_open`, `test_time_exit` |
| Diferencia bid/ask | `test_short_target_not_reached_because_of_spread` |
| Comisión y slippage | `test_commission_is_charged_once_per_side`, `test_losing_long_with_stop_slippage` |
| Posición abierta al final | `test_position_open_at_end_is_closed_at_last_bid`, `test_mark_to_market_while_open` |
| Stop y objetivo en la misma barra | `test_same_bar_without_ticks_assumes_stop`, `test_same_bar_resolved_by_ticks_target_first`, `test_incomplete_ticks_fall_back_to_policy` |
| Volumen mínimo y paso | `test_volume_rounds_down_to_step`, `test_min_volume_exceeding_risk_blocks_trade` |
| Rechazo de información futura | `test_signal_using_future_information_is_rejected`; `test_no_lookahead.py` (cambiar datos futuros de H1, M15 y M5 no cambia señales pasadas; la H1 abierta no se usa) |
| Datos desordenados o duplicados | `test_unordered_or_duplicated_bars_raise`, `test_incoherent_ohlc_raises` |
| El coste elimina la ventaja bruta | `test_cost_turns_gross_edge_into_net_loss` |
| Libro de operaciones frente a equity | `test_ledger_and_equity_consistent_over_many_trades` y todas las que usan `ledger_matches_equity` |
| Otros | swap con miércoles triple, límite diario, margen insuficiente, retraso máximo, señal con posición abierta, zona horaria, modelo de spread, resumen de ticks |

## Pruebas con datos reales

**Prueba de humo** (`experiments/phase_c_engine_smoke/`): señales mecánicas sin intención de
inversión, dos al día durante 2017-04 a 2026-10 (4 907 señales, 3,37 M barras M1). En los tres
escenarios el libro cuadra con la equity y cada pasada tarda ~1,2 s. Spread medio de entrada:
6,45 puntos (base), 8,33 (adverso) y 18,04 (estrés). Hubo 5 casos de stop y objetivo en la
misma barra: 1 resuelto con ticks y 4 con el supuesto conservador. Una señal se rechazó por
stop al otro lado del precio. **No se reporta rentabilidad: estas señales no son una estrategia.**

**Cotización del 2020-03-26 10:23** (`experiments/phase_c_outlier_2020/`). Las barras de 10:22
y 10:25-10:26 no existen, así que la barra anómala (apertura 1 500,59 frente a ~1 602) llega tras
un hueco. Posición hipotética de 0,01 lotes abierta a las 10:15, comparada con una copia en
memoria donde esa barra se interpola:

| Posición | Distancia de stop y objetivo | Con la cotización | Sin ella | Diferencia |
|---|---|---|---|---|
| Largo | 5 USD | stop, −6,20 | stop, −6,20 | 0 |
| Largo | 10 a 100 USD | stop por hueco a 1 500,57, −102,39 | +8,82 a +11,63 | −111 a −114 USD |
| Largo | 150 USD | sin efecto | sin efecto | 0 |
| Corto | 10 a 50 USD | objetivo, +9,91 a +49,91 | −10,11 a −13,14 | +20 a +63 USD |

Conclusión: la cotización se mantiene (decisión de Juan) y su efecto se concentra en ese minuto.
Un largo abierto con stop entre ~5 y ~100 USD pierde unos 100 USD por cada 0,01 lotes,
**mucho más que el riesgo planeado**, porque el stop salta por hueco. Si una estrategia tiene un
largo abierto en ese minuto, el informe de la fase E debe mostrar el resultado con y sin esa
operación.

## Limitaciones del motor

1. Ask estimado fuera del periodo con ticks (ver COST_MODEL.md).
2. Orden intrabarra desconocido antes de abril de 2026: se asume el stop. Afecta solo cuando
   stop y objetivo caen en el mismo minuto (5 de 4 906 operaciones en la prueba de humo).
3. Slippage supuesto, sin medir. Sin rechazos ni recotizaciones del bróker.
4. Una sola posición a la vez. Sin órdenes pendientes de entrada (límite o stop): solo a mercado.
5. Sin stop-out por margen: se exige margen al abrir, pero no se simula el cierre forzoso del
   bróker (nivel no documentado).
6. Swap con los valores actuales en todo el historial.
7. La señal se ejecuta en la apertura de la barra M1 siguiente; no se modela la latencia dentro del minuto.
