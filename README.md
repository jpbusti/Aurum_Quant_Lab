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
| C | Motor de backtesting y pruebas | pendiente |
| D | Estrategias de referencia | pendiente |
| E | Evaluación estadística y walk-forward | pendiente |
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

## Pruebas

```bash
.venv/Scripts/python -m pytest
.venv/Scripts/python -m pytest -m mt5
```

La primera ejecuta las pruebas unitarias con datos sintéticos; la segunda, las de integración
contra el terminal real (solo lectura).

## Documentación

- [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md): entorno, especificaciones del símbolo e historial real.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): estructura, flujo y decisiones pendientes.
- [docs/TIMEZONE.md](docs/TIMEZONE.md): hora del servidor = Nueva York + 7 h y regla de conversión.
- [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md): almacén, columnas, convención horaria, calendario y calidad.
