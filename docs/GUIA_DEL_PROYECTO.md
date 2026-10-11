# Guía del proyecto AURUM Quant Lab

Escrita el 2026-10-11 para responder tres preguntas de Juan: cómo funciona el proyecto, cómo
sabemos que está bien hecho y qué hacer ahora que ninguna estrategia ha pasado.

---

## 1. Cómo funciona, en una página

```text
MT5 (cuenta demo, solo lectura)
  │  download-data
  ▼
data/raw/            barras M1-H1 desde 2017 y ticks desde abril de 2026, en Parquet, con procedencia
  │  validate-data
  ▼
Informe de calidad   ¿hay huecos, duplicados, precios imposibles? Si hay errores críticos, bloquea
  │  calibrate-costs
  ▼
Modelo de costes     spread por hora medido con 87 M ticks, comisión y slippage, en 3 escenarios
  │
  ▼
Estrategias          deciden al cierre de cada vela M15 viendo solo velas cerradas → "señales"
  │
  ▼
Motor de backtest    ejecuta las señales minuto a minuto con bid/ask, stops, costes, swap y tamaño por riesgo
  │
  ▼
Evaluación           métricas por año y periodo, placebo aleatorio, DSR y veredicto pre-registrado
  │
  ▼
docs/                todo resultado, aprobado o rechazado, queda escrito
```

La idea central: **primero se escribe qué se va a probar y con qué criterio (pre-registro), y
después se prueba**. Así no se puede ajustar el criterio a lo que salió.

---

## 2. Qué hay en cada parte

### Configuración (`configs/`)

| Archivo | Para qué sirve |
|---|---|
| `data.yaml` | Fuente esperada (servidor, cuenta demo, símbolo XAUUSD), calendario de sesiones, umbrales de validación y exclusiones de datos con su motivo |
| `cost_model.yaml` | Spread por hora calibrado con ticks. Lo genera `calibrate-costs`; no se edita a mano |
| `backtest.yaml` | Comisión verificada (3,50 USD por lado), reglas de ejecución y escenarios de coste base, adverso y estrés |
| `risk.yaml` | Balance virtual (10 000 USD), riesgo por operación (0,5 %) y límites diario y de drawdown |
| `research.yaml` | Registro de todas las hipótesis: parámetros, cuántas variantes se probaron y su veredicto |

### Código (`src/aurum/`)

| Módulo | Qué hace |
|---|---|
| `cli.py` | Comandos: `check-environment`, `download-data`, `validate-data` y `calibrate-costs` |
| `environment.py` | Revisa Python, el terminal, que la cuenta sea demo, el símbolo y el historial disponible |
| `data/mt5_client.py` | Habla con MT5 **solo para leer**. No tiene ninguna función que envíe órdenes, y una prueba lo vigila |
| `data/ingest.py` | Descarga incremental: solo barras cerradas, nunca sobrescribe y registra cada descarga |
| `data/storage.py` | Guarda en Parquet por año, con un manifiesto de procedencia |
| `data/tick_minutes.py` | Resume los 87 M ticks por minuto, un día cada vez para no saturar la memoria |
| `validation/checks.py`, `quality.py` | Las pruebas de calidad de datos y el bloqueo si algo es crítico |
| `features/align.py` | La regla anti-trampa: en el instante T solo se ve una vela si ya cerró |
| `features/indicators.py`, `daily.py`, `sessions.py`, `regime.py` | ATR, medias, velas diarias, horas de Nueva York y el HMM de regímenes |
| `timeutils.py` | Conversión de la hora del servidor a UTC (Nueva York + 7 h) |
| `strategies/` | La interfaz común (`base.py`), las 3 referencias, las 6 candidatas y el registro |
| `backtesting/engine.py` | El motor: ejecuta, cobra costes, mueve stops y objetivos y lleva la contabilidad |
| `backtesting/spread_model.py`, `setup.py`, `types.py` | Modelo de spread, construcción del motor desde la configuración y tipos de datos |
| `risk/sizing.py` | Tamaño de posición por riesgo, redondeado siempre hacia abajo; bloquea si 0,01 lotes ya arriesgan demasiado |
| `evaluation/metrics.py`, `walkforward.py`, `placebo.py` | Métricas, intervalos por bootstrap, DSR, veredictos, segmentos por año y placebo de 1 000 semillas |

### Experimentos (`experiments/`)

Scripts reproducibles que generan los números de los informes. Los resultados no se versionan;
se regeneran ejecutando el script.

- `phase_c_engine_smoke`: prueba de humo del motor con 3,4 M barras.
- `phase_c_outlier_2020`: impacto de la cotización anómala del 2020-03-26.
- `phase_e`: evaluación de la ronda 1 y placebo.
- `ronda2`: filtro de la ronda 2.
- `timezone_check`: validación horaria.
- `audit_risk`: auditoría con el 0,5 % y el 2 %.

### Pruebas (`tests/`)

- 183 pruebas unitarias con datos sintéticos.
- 9 de integración con el terminal real y los datos descargados.

### Documentos (`docs/`)

| Documento | Contenido |
|---|---|
| ENVIRONMENT, DATA_DICTIONARY, TIMEZONE | Entorno, datos y su calidad, y zona horaria |
| COST_MODEL, BACKTEST_ENGINE | Cómo se calculan los costes y cómo ejecuta el motor |
| STRATEGY_RESEARCH | Ficha de cada hipótesis con fuentes, reglas y veredicto |
| PREREGISTRO_* | Lo que se decidió **antes** de cada prueba |
| PHASE_E_RESULTS, RONDA2_RESULTS, AUDIT_POST_E | Resultados |
| PHASE_H_VIABILITY | Capital necesario |
| ARCHITECTURE | Estructura y decisiones |

---

## 3. ¿Cómo sabemos que está bien hecho?

Respuesta honesta: **una parte está comprobada contra referencias externas y otra parte solo
contra mí mismo.** El mismo Claude escribió el código y sus pruebas. Si me equivoqué al entender
una regla, la prueba pudo heredar el mismo error.

### Comprobado contra algo externo

| Qué | Contra qué |
|---|---|
| Valor de 0,01 lotes (1 USD por cada 1,00 de precio) y margen (20,98 USD a 4 195) | Funciones de cálculo del propio MT5 (`order_calc_profit` y `order_calc_margin`) |
| Comisión de 3,50 USD por lado | Portal de IC Markets (verificada por Juan) |
| Barras M1 | Coinciden con los ticks en 187 800 minutos (1 diferencia explicada) |
| Barras M5-H1 | Coinciden al 100 % con las reconstruidas desde M1 |
| Zona horaria | Horario real del oro y publicaciones del informe de empleo de EE. UU. a las 08:30 NY |
| Ausencia de fuga | Se cambian los datos futuros y se comprueba que las señales pasadas no cambian. Una estrategia tramposa a propósito hace fallar la prueba |
| Que el método puede detectar un resultado | Placebo de 1 000 semillas aleatorias con los mismos costes |
| Cálculos de riesgo y beneficio | Operaciones calculadas a mano en las pruebas y en la auditoría (69,76 USD de riesgo, coincide con el motor) |

### Comprobado solo internamente (riesgo de error compartido)

- Las fórmulas de PF, Sharpe, Sortino, Calmar, SQN, Ulcer y DSR, y el bootstrap. Siguen las
  definiciones pre-registradas, pero **no se han recalculado con una herramienta externa**.
- La lógica completa del motor sobre años de datos (más allá de los casos de prueba).
- Que cada estrategia implemente exactamente la regla de su ficha.

### Lo que no se puede comprobar con datos históricos

- El slippage real (es un supuesto).
- El spread antes de abril de 2026 (es un modelo).
- El orden de los precios dentro de un minuto sin ticks (se asume el peor caso).

### Comprobaciones independientes que propongo

1. **Reproducir en el Strategy Tester de MT5** unas cuantas semanas de una estrategia sencilla
   (por ejemplo ORB, en 2026, con ticks reales) mediante un EA de MQL5, y comparar operación a
   operación entradas, salidas y P&L con nuestro motor. Es el contraste más fuerte: es otro motor,
   escrito por MetaQuotes. **Recomendada.**
2. **Recalcular las métricas con una librería externa** (por ejemplo `quantstats`) a partir de la
   curva de equity y las operaciones exportadas. Requiere instalar ese paquete, y lo haría solo con
   tu permiso.
3. **Una revisión de código hecha por otra persona** o por otra herramienta de revisión, centrada en
   el motor y en las métricas.
4. **Paper trading**: compara los precios reales de la demo con los que supone el motor.

---

## 4. Ninguna estrategia pasa. ¿Qué hacer si hay gente que opera oro?

### Lo que dice la evidencia

- Que haya gente operando no significa que gane. En Europa, los brókers de CFD deben publicar qué
  porcentaje de cuentas minoristas pierde dinero, y suele ser la mayoría. La cifra de IC Markets
  aparece en su web; conviene mirarla.
- Lo que hemos visto coincide con lo publicado. La réplica independiente del ORB encontró un
  resultado neto nulo después de costes, igual que nosotros. En intradía los costes (spread,
  comisión y slippage) se comen las ventajas pequeñas.
- Donde hay evidencia académica más sólida es en el **seguimiento de tendencia a horizontes
  largos** (semanas o meses) y en carteras diversificadas (Hurst, Ooi y Pedersen, 2017). Ahí los
  costes pesan mucho menos en relación con el movimiento. Pero los stops son amplios y piden más
  capital (PHASE_H_VIABILITY.md).

### Opciones

| Opción | Qué implica | Mi valoración |
|---|---|---|
| A. Verificación independiente (Strategy Tester) | Comprobar que el laboratorio mide bien antes de seguir | **Primero**: si el motor tuviera un error, todos los rechazos estarían en duda |
| B. Paper trading del cruce de medias pre-registrado al 0,5 % | Datos nuevos y limpios; costes y slippage reales | **Sí**: es la única evidencia nueva posible ahora |
| C. Pasar a horizonte diario o semanal | Seguimiento de tendencia como en la literatura. En la fase A el servidor devolvió una barra por día desde 2000. Si al descargarlas como D1 resultan válidas, 2000-2016 sería una muestra diaria no gastada (sin verificar todavía) | **Sí, como siguiente ronda pre-registrada**, sabiendo que exige más capital por operación |
| D. Optimizar parámetros, subir el riesgo o comprar bots o señales | Más resultados bonitos sobre datos gastados | **No**: es lo que más dinero hace perder |
| E. Cerrar el proyecto | Conservar el capital | Legítimo. No encontrar ventaja también es un resultado |

**Mi recomendación**: A → B → C, sin dinero real. La ejecución real sigue deshabilitada y solo
se activaría con tu aprobación explícita después de paper trading con evidencia suficiente.
Ninguna de estas opciones garantiza encontrar una estrategia rentable.
