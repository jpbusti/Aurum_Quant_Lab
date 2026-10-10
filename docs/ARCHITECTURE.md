# Arquitectura de AURUM Quant Lab

Estado: **fase A completada** (inspección del entorno). El resto es diseño; cada módulo se
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

## Pendiente de decidir con datos del terminal

1. **Desfase horario del servidor** y fechas de cambio de horario de verano: medir con mercado abierto.
2. **Comisión** por lote de la cuenta Raw: la API de símbolo no la da. Opciones: que Juan la
   confirme desde las condiciones de su cuenta, o medirla de operaciones demo (eso implica
   abrir órdenes en demo, y no se hará sin aprobación).
3. **Modelo de spread** para backtests largos: el campo de las barras tiene ceros, así que se
   calibrará con los 6 meses de ticks (por hora del día y día de la semana) y se aplicará con
   escenarios base y adverso.
4. **Periodos de la división temporal**: con M15 denso desde 2017-04, la propuesta inicial
   (a aprobar antes de ver resultados) se presentará en la fase E.
5. **Resolución intrabarra** (stop y objetivo en la misma vela): ticks solo en el periodo
   reciente; para el resto, supuesto conservador (primero el stop) y medición de su impacto
   en el tramo con ticks.
6. **Swap**: cambia con el tiempo y no hay histórico en la API; se registrará cada día en
   paper trading y se usarán escenarios en el backtest.
