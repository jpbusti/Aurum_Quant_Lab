# Arquitectura de AURUM Quant Lab

Estado: **fases A a E completadas** (las tres candidatas de la ronda 1, REJECTED); **ronda 2 de la fase D implementada y pre-registrada, sin backtest** (docs/PREREGISTRO_RONDA2.md). El resto es diseño; cada módulo se
crea en su fase y solo cuando pasan las pruebas de la anterior.

## Principios

1. MT5 es una fuente de datos de solo lectura. La ejecución real está deshabilitada y el
   código no tiene llamadas de envío de órdenes (prueba `test_safety.py`).
2. Las estrategias solo producen señales. El motor de backtesting decide cuándo y a qué precio
   se ejecutan, con información estrictamente anterior.
3. Toda salida (datos, experimentos, informes) lleva procedencia: fuente, servidor, símbolo,
   timeframe, rango, versión del código y configuración.
4. Una sola fuente por conjunto de datos (ICMarketsSC-Demo, XAUUSD). Si cambia, es un conjunto
   nuevo.
5. Configuración versionada en `configs/`; nada de parámetros escondidos en el código.

## Estructura

```text
Aurum_Quant_Lab/
├── pyproject.toml, requirements.lock, .env.example, .gitignore
├── configs/
│   ├── data.yaml            fase A: fuente, símbolo, timeframes
│   ├── backtest.yaml        fase C
│   ├── risk.yaml            fase C/H
│   └── research.yaml        fase D/E
├── docs/                    ENVIRONMENT (A), ARCHITECTURE (A), DATA_DICTIONARY (B),
│                            STRATEGY_RESEARCH (D), RISK_POLICY (C/H), VALIDATION (E)
├── data/{raw,processed,reports}/   no versionado; se regenera desde MT5
├── src/aurum/
│   ├── cli.py               punto de entrada: python -m aurum.cli <comando>
│   ├── config.py            carga de YAML
│   ├── environment.py       fase A: inspección del entorno
│   ├── data/                mt5_client (A), descarga incremental y Parquet (B)
│   ├── validation/          integridad de datos (B)
│   ├── features/            indicadores y alineación multi-timeframe sin fuga (C/D)
│   ├── backtesting/         motor de eventos, costes, ejecución (C)
│   ├── strategies/          interfaz común y referencias (D)
│   ├── risk/                tamaño de posición, límites, viabilidad de capital (C/H)
│   ├── evaluation/          métricas, walk-forward, bootstrap por bloques, PBO/DSR (E)
│   ├── paper_trading/       bucle en demo con estado persistente (G)
│   └── reporting/           informes (E-H)
├── tests/{unit,integration,fixtures}/
├── experiments/             un directorio por experimento con id, config y resultados
└── logs/
```

Cambio respecto a la propuesta original: `execution/` no se crea. Hasta que haya aprobación
para operar en real no hay nada que poner ahí, y la simulación de ejecución vive en
`backtesting/` y `paper_trading/`. Un módulo vacío solo invitaría a rellenarlo antes de tiempo.

## Flujo de datos

```text
MT5 (solo lectura) → data/ (raw Parquet + metadatos) → validation/ (informe de calidad, bloqueo)
  → processed/ (barras M1 válidas; M5/M15/M30/H1 nativas verificadas o reconstruidas desde M1)
  → features/ (solo velas cerradas) → strategies/ (señales) → backtesting/ (+ risk/)
  → evaluation/ (walk-forward, incertidumbre) → reporting/ → paper_trading/ (demo)
```

## Decisiones tomadas en la fase A

| Decisión | Motivo |
|---|---|
| Python 3.12 en `.venv` con versiones fijadas | reproducibilidad; el Python global tiene paquetes ajenos |
| Paquete oficial MetaTrader5 sin credenciales | usa la sesión del terminal; nada que filtrar |
| Marcas de tiempo guardadas tal cual hasta medir el desfase | evitar una conversión UTC errónea |
| Identificación del símbolo por divisas, no por nombre | el nombre puede llevar sufijo; se fija en `data.yaml` tras verificarlo |
| Pruebas contra el terminal marcadas `mt5`, aparte de las unitarias | las unitarias corren sin terminal y con datos sintéticos etiquetados |
| Dependencias mínimas (numpy, PyYAML) | pandas y pyarrow entran en la fase B, cuando hacen falta |

## Decisiones tomadas en la fase B

| Decisión | Motivo |
|---|---|
| Parquet anual por timeframe + manifiesto JSON, sin base de datos | suficiente para ~3,4 M barras M1; legible y versionable por fuente |
| Guardar timeframes nativos (M5-H1) además de M1 | validados: coinciden al 100 % con los reconstruidos desde M1 |
| Solo barras cerradas; nunca sobrescribir una barra guardada | reproducibilidad: un experimento ve siempre los mismos datos |
| Calendario de sesiones derivado de los datos, en hora del servidor | clasificar huecos sin suponer horarios; ver DATA_DICTIONARY.md |
| Excluir 2017-04-01 a 2017-04-06 01:00 | barras horarias con etiqueta M1 (evidencia en DATA_DICTIONARY.md) |
| Los saltos de precio se reportan, no se eliminan | un salto puede ser real (datos macro); excluir exige decisión y motivo |
| numpy 2.x (antes <2) | pyarrow actual exige numpy 2; el paquete MetaTrader5 5.0.6231 funciona con él (pruebas `mt5` pasan) |
| `validation.quality.require_usable()` como puerta | las fases C+ no pueden usar un timeframe bloqueado o sin validar |

## Decisiones aprobadas por Juan (2026-10-10)

| Decisión | Detalle |
|---|---|
| Zona horaria | servidor = Nueva York + 7 h (docs/TIMEZONE.md); falta confirmarlo en vivo |
| Comisión de la cuenta Raw | 3,50 USD por lado y lote (7,00 USD ida y vuelta; 0,07 USD con 0,01 lotes). **Verificada en el portal de IC Markets el 2026-10-10** |
| Cotización del 2020-03-26 10:23 | **se mantiene** (1 500,59 entre barras de ~1 600, 3 ticks): el bróker la cotizó y pudo ejecutar stops, así que es lo conservador. Su impacto se medirá en la fase C |
| Ticks | descargados los 6 meses disponibles (2026-04-01 a 2026-10-09, 87 M ticks) para calibrar el spread por hora y régimen |

## Decisiones tomadas en la fase C

| Decisión | Motivo |
|---|---|
| Ticks procesados archivo diario por archivo diario y solo 3 columnas | 87 M ticks (~5 GB en memoria) no caben con holgura; resumen por minuto en `data/processed/` |
| Spread = mínimo de la barra M1 + exceso por hora del servidor | error fuera de muestra 1,39 puntos frente a 2,29 de un spread fijo (COST_MODEL.md) |
| Sin régimen de volatilidad en el modelo de spread | no mejoró la predicción fuera de muestra |
| Escenarios base, adverso y estrés fijados antes de probar estrategias | evitar ajustar costes a resultados |
| Ejecución simulada sobre M1 aunque la señal sea M15 | ver el recorrido del precio dentro de la vela de señal |
| Ticks para el orden intrabarra solo si reproducen el máximo y mínimo del minuto | el hueco de ticks del 2026-06-29 15:37-15:41 no puede decidir nada |
| Motor en hora del servidor; conversión a UTC aparte y estricta | la conversión aún no está confirmada en vivo |
| Sin carpeta `execution/` | no hay operativa real; sigue deshabilitada |

## Decisiones tomadas en la fase D

| Decisión | Motivo |
|---|---|
| Horas de sesión en hora de Nueva York = servidor − 7 h (`features/sessions.py`) | las referencias de las fuentes son horas de NY; no requiere zonas horarias mientras la convención se mantenga |
| Azar de REF-RANDOM determinado por (semilla, instante) | reproducible y sin dependencia del orden ni del futuro |
| Parámetros en dataclasses congeladas, reflejados en `configs/research.yaml` | una prueba impide que código y registro diverjan |
| Ruptura de Londres y VWAP no implementadas | conversión UTC sin confirmar y volumen real no verificado; registradas como no implementadas |

## Pendiente de decidir con datos del terminal

1. **Periodos de la división temporal**: con M15 denso desde 2017-04, la propuesta inicial
   (a aprobar antes de ver resultados) se presentará en la fase E.
2. **Resolución intrabarra**: implementada (ticks si cubren el minuto; si no, primero el stop).
   Medir su impacto por estrategia en la fase E.
3. **Swap**: cambia con el tiempo y no hay histórico en la API; se registrará cada día en
   paper trading y se usarán escenarios en el backtest.
4. **Modelo de spread**: calibrado en la fase C (COST_MODEL.md). Pendiente: el exceso por hora se
   midió en 2026 y se aplica a 2017-2025 sin poder verificarlo.
5. **Slippage**: los valores de los escenarios son supuestos; medirlos en paper trading (fase G).
6. **Zona horaria**: confirmar Nueva York + 7 h en vivo con el mercado abierto.
