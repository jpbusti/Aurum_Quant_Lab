# Verificación independiente del motor con el Strategy Tester de MT5

**Fecha**: 2026-10-11. Código: `experiments/mt5_tester/` (EA `AurumOrbCheck.mq5`, `tester.ini`,
`compare.py`). El EA solo arranca dentro del Strategy Tester (`MQL_TESTER`); no puede operar en
la cuenta.

## Qué se comparó

- Regla: CAND-ORB-NY-v1 (vela M15 de las 16:30 del servidor; stop en el extremo opuesto;
  objetivo 10R; cierre por tiempo a las 23:00 del servidor).
- Volumen fijo de 0,01 lotes en los dos motores, para comparar precios y no el tamaño.
- Periodo: 2026-04-01 a 2026-10-09, el tramo con ticks reales descargados.
- Strategy Tester: modo "cada tick basado en ticks reales", depósito de 10 000 USD, 1:200.
- Nuestro motor: escenario de costes base **sin slippage**, porque el tester no añade slippage.
  Así se aíslan las diferencias de lógica y de precios.

## Resultado

| Medida | Valor |
|---|---|
| Operaciones del motor / del tester | 137 / 136 |
| Días coincidentes | 136 |
| Mismo lado (compra o venta) | 136 de 136 |
| Mismo motivo de salida | 135 de 136 |
| Diferencia absoluta del precio de entrada: media / p95 | 0,011 / 0,03 USD |
| Diferencia absoluta del precio de salida: media / mediana | 0,262 / 0,015 USD |
| P&L bruto de los 136 días: motor / tester | −502,61 / −537,72 USD |

**Conclusión**: el motor reproduce la señal, el lado, la entrada y el motivo de salida de todas
las operaciones comparables. Las diferencias de precio tienen dos causas identificadas (abajo).
Ninguna cambia el signo del resultado: con los dos motores la estrategia pierde antes de
comisiones.

## Diferencias explicadas

1. **Operación del 2026-10-09 (solo en el motor)**: el tester no simula el día de `ToDate`.
   Es una cuestión de configuración, no del motor.
2. **2026-06-19 (único motivo de salida distinto)**: era el festivo de Juneteenth y el mercado
   cerró antes de las 23:00 del servidor. El motor cerró la venta en el primer precio después
   del límite (lunes 01:00, +13,45 USD). El EA solo comprueba la hora dentro del mismo día, así
   que no la cerró y la posición tocó el stop el lunes a las 03:16 (−9,48 USD). Es un fallo del
   EA de verificación, no del motor: el motor aplica la regla de la ficha.
3. **Slippage en los stops (la diferencia relevante)**: con ticks reales, el stop se ejecuta en
   el primer tick que lo atraviesa, que puede estar más allá del nivel. Nuestro motor trabaja con
   barras M1 y llena el stop exactamente en el nivel, salvo si la barra abre más allá (hueco).

   | Stops (102) | Media | Mediana | p90 | p95 | Máximo |
   |---|---|---|---|---|---|
   | Peor precio del tester frente al nivel del stop (puntos) | 12,3 | 3,5 | 27,7 | 63,8 | 176 |

   Sin el día 2026-06-19, la diferencia de P&L bruto entre los motores es de unos 12 USD en
   135 operaciones, y se explica casi entera por este slippage (12,46 USD).

4. Entradas y cierres por tiempo: diferencias de 1 a 3 puntos. Vienen de usar el spread
   modelado en lugar del ask real del tick.

## Qué implica

- **El motor no tiene errores de lógica detectables en esta regla**: mismas señales, mismos
  lados, mismos motivos de salida y entradas a 1 punto de media.
- **El escenario base subestima el coste de los stops en esta estrategia.** Supone 2 puntos de
  slippage por lado. Los ticks reales muestran una media de unos 12 puntos en los stops, entre el
  escenario adverso (10) y el de estrés (30). Esto **empeora** los resultados de las estrategias
  con stops en momentos volátiles; no puede convertir ningún rechazo en aprobación.
- No se cambian los escenarios ni los veredictos ya publicados (sería un cambio a posteriori).
  Para futuras rondas pre-registradas propongo medir el slippage de los stops con ticks, o usar el
  escenario adverso como referencia en las estrategias que salen por stop.
- **La comisión no se verificó con el tester**: el tester cobró 0 USD. Sigue verificada solo con
  el portal de IC Markets.

## Lo que esta verificación no cubre

- Una sola regla (ORB-NY) y seis meses. El resto de estrategias usa el mismo motor, pero sus
  caminos de código específicos (por ejemplo, el swap nocturno o la gestión de varias posiciones)
  no se contrastaron.
- El tamaño por riesgo y las métricas: aquí el volumen fue fijo y solo se compararon operaciones.
- La ejecución real del bróker: el tester con ticks reales tampoco modela la latencia ni las
  recotizaciones. Eso solo lo dará el paper trading.
