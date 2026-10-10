# AURUM Quant Lab

Laboratorio para investigar, probar y validar estrategias sobre oro (XAU/USD) con datos de
MetaTrader 5 (IC Markets, cuenta demo). La rentabilidad es una hipótesis que se intenta
refutar, no un resultado: ningún informe de este proyecto garantiza beneficios futuros.

**La ejecución real está deshabilitada.** El código solo lee datos del terminal.

## Estado

| Fase | Contenido | Estado |
|---|---|---|
| A | Inspección del entorno y arquitectura | hecha |
| B | Ingesta de datos e integridad | hecha |
| C | Motor de backtesting y pruebas | hecha |
| D | Estrategias de referencia | rondas 1 y 2 hechas |
| E | Evaluación estadística y walk-forward | ronda 1 y filtro de la ronda 2 hechos: 6 candidatas REJECTED |
| F | Selección de candidatos | pendiente |
| G | Paper trading en demo | pendiente |
| H | Viabilidad de capital | pendiente |

## Instalación (Windows)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.lock
.venv/Scripts/python -m pip install -e . --no-deps
```

Requiere el terminal MetaTrader 5 abierto y conectado a la cuenta demo. No se piden ni se
guardan credenciales.

## Uso

```bash
.venv/Scripts/python -m aurum.cli check-environment
```

Comprueba Python, el terminal, la cuenta (debe ser demo y del servidor de `configs/data.yaml`),
el símbolo de oro, sus especificaciones y el historial disponible. Guarda el informe en
`data/reports/environment/`. Código de salida: 0 correcto o con avisos, 1 error crítico,
2 terminal no disponible.

```bash
.venv/Scripts/python -m aurum.cli download-data --ticks-days 5
.venv/Scripts/python -m aurum.cli validate-data
```

`download-data` descarga de forma incremental las barras M1, M5, M15, M30 y H1 (desde abril de
2017) y, si se pide, los ticks de los N últimos días laborables, a Parquet en `data/raw/`.
`validate-data` revisa la integridad y guarda el informe en `data/reports/quality/`; sale con
código 1 si algún conjunto queda bloqueado por errores críticos.

```bash
.venv/Scripts/python -m aurum.cli calibrate-costs
```

Resume los ticks por minuto (archivo diario por archivo diario) y calibra el modelo de spread en
`configs/cost_model.yaml`. Ver [docs/COST_MODEL.md](docs/COST_MODEL.md).

## Pruebas

```bash
.venv/Scripts/python -m pytest
.venv/Scripts/python -m pytest -m "mt5 or data"
```

La primera ejecuta las pruebas unitarias con datos sintéticos; la segunda, las de integración
contra el terminal real (solo lectura) y contra los datos descargados.

## Documentación

- [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md): entorno, especificaciones del símbolo e historial real.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): estructura, flujo y decisiones pendientes.
- [docs/TIMEZONE.md](docs/TIMEZONE.md): hora del servidor = Nueva York + 7 h y regla de conversión.
- [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md): almacén, columnas, convención horaria, calendario y calidad.
- [docs/COST_MODEL.md](docs/COST_MODEL.md): perfil de spread por hora, modelo de costes y escenarios.
- [docs/STRATEGY_RESEARCH.md](docs/STRATEGY_RESEARCH.md): fichas de las referencias y candidatas, y registro de variantes.
- [docs/PREREGISTRO_PHASE_E.md](docs/PREREGISTRO_PHASE_E.md) y [docs/PHASE_E_RESULTS.md](docs/PHASE_E_RESULTS.md): evaluación pre-registrada y resultados.
- [docs/PREREGISTRO_RONDA2.md](docs/PREREGISTRO_RONDA2.md) y [docs/RONDA2_RESULTS.md](docs/RONDA2_RESULTS.md): ronda 2 (prueba final gastada, paper como evidencia principal) y su filtro.
- [docs/BACKTEST_ENGINE.md](docs/BACKTEST_ENGINE.md): reglas de ejecución, alineación sin fuga, riesgo y pruebas del motor.
