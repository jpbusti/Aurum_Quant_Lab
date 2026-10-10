# Entorno de AURUM Quant Lab

Inspección realizada el **2026-10-10 (sábado, mercado cerrado)** con
`python -m aurum.cli check-environment`. El JSON completo de cada ejecución queda en
`data/reports/environment/` (no versionado). Todo lo de este documento viene de ese
informe o de consultas directas al terminal; lo que es inferencia está marcado como tal.

## Sistema

| Elemento | Valor |
|---|---|
| Sistema operativo | Windows 11 Pro 10.0.22631 |
| Python | 3.12.2 (entorno aislado en `.venv/`) |
| Paquete MetaTrader5 | 5.0.6231 en `.venv` (el Python global tiene 5.0.6147) |
| Dependencias fijadas | `requirements.lock` |
| Terminal | MetaTrader 5 build 6249 (8 Oct 2026), `C:\Program Files\MetaTrader 5` |

Hay una segunda instalación, `C:\Program Files\FxPro - MetaTrader 5`. El paquete se conecta
al terminal por defecto, que es el de IC Markets. Si algún día se abre el de FxPro primero,
`check-environment` lo detecta (servidor distinto, error crítico). Para fijarlo, definir
`AURUM_MT5_PATH` en `.env`.

## Conexión y cuenta

- Conexión sin credenciales, usando la sesión abierta del terminal: correcta.
- Servidor `ICMarketsSC-Demo`, empresa Raw Trading Ltd, cuenta **DEMO**, divisa USD,
  apalancamiento 1:200, modo de margen RETAIL_HEDGING.
- El botón de trading algorítmico del terminal está **desactivado** (`trade_allowed = False`).
  Así debe seguir; el código no contiene llamadas de envío de órdenes (`tests/unit/test_safety.py`).
- El informe no guarda login, nombre, balance ni equity.

## Símbolo de oro

Se buscaron símbolos no personalizados con divisa base XAU y de beneficio USD.
Único candidato: **`XAUUSD`** (sin sufijo), ruta `Commodities\Metals\XAUUSD`.
Existen otros pares de oro (XAUEUR, XAUAUD, XAUJPY, XAUCHF, XAUGBP) y acciones de mineras
(`GOLD.NYSE`) que no se usan.

### Especificaciones (MT5, 2026-10-10)

| Campo | Valor | Lectura |
|---|---|---|
| Dígitos / point | 2 / 0.01 | precio con 2 decimales |
| Tick size / tick value | 0.01 / 1.0 USD | por 1 lote; 0.01 lote = 0.01 USD por tick |
| Tamaño de contrato | 100 | 1 lote = 100 oz; un movimiento de 1 USD = 100 USD/lote, 1 USD por 0.01 lote |
| Volumen mín / máx / paso | 0.01 / 100 / 0.01 | |
| Divisa de beneficio / margen | USD / XAU | |
| Distancia mínima de stops / freeze | 0 / 0 | el servidor no impone distancia mínima |
| Cálculo de beneficio y margen | FOREX | margen = volumen x contrato x precio / apalancamiento |
| Margen de 0.01 lote | 20.98 USD a 4195.36 | calculado por el terminal con `order_calc_margin` (no es una orden) |
| Modo de trading / ejecución | FULL / MARKET | |
| Relleno permitido | IOC | |
| Spread flotante | sí; 50 puntos (0.50 USD) en el último tick del viernes | ver costes abajo |
| Swap | en puntos: largo -57.03, corto +39.767; triple el miércoles | cambia con el tiempo; hay que registrarlo por fecha |
| Comisión | **no la expone la API de símbolo** | pendiente, ver decisiones |

## Historial disponible en el terminal

Las barras se pidieron con `copy_rates_range` desde 2000-01-01.

| Timeframe | Barras | Primer registro | Denso desde | Última barra (marca del servidor) |
|---|---|---|---|---|
| M1 | 3 378 066 | 2000-01-03 | **2017-04** | 2026-10-09 23:56 |
| M5 | 686 187 | 2000-01-03 | 2017-04 | 2026-10-09 23:55 |
| M15 | 236 554 | 2000-01-03 | 2017-04 | 2026-10-09 23:45 |
| M30 | 124 141 | 2000-01-03 | 2017-04 | 2026-10-09 23:30 |
| H1 | 67 936 | 2000-01-03 | 2016-01 | 2026-10-09 23:00 |

Hallazgos:

1. **Antes de 2016 el servidor devuelve una barra por día** en todos los timeframes
   (unas 260 por año). Durante 2016 M1, M5, M15 y M30 devuelven barras horarias
   (5 688 en el año, igual que H1). Esos tramos no son M1 ni M15 reales y no deben
   usarse como tales. "Denso desde" = primer mes en que la separación mediana entre barras
   es exactamente el timeframe.
2. El historial M15 utilizable empieza en **abril de 2017**: unos 9,5 años. No hay minutos
   reales desde enero de 2017.
3. Barras ordenadas y sin duplicados en todos los timeframes (validación completa en fase B).
4. **Ticks**: el terminal solo devuelve ticks desde **2026-04-01 01:49** (marca del servidor),
   unos 6 meses. En las 24 h previas al último tick hubo 420 557 ticks. Para backtests largos
   solo hay barras; los ticks sirven para calibrar spread y resolver el orden intrabarra en
   el periodo reciente.
5. El campo `spread` de las barras (en puntos, último año): M1 p50 = 5, p95 = 11, p99 = 40;
   en M15 y superiores el p5 es 0. Un spread 0 no es realista, así que ese campo parece un
   mínimo o un valor de muestra dentro de la barra, no el coste real. **No se usará como coste
   sin calibrarlo con ticks.**
6. La columna `real_volume` no es cero en parte de las barras; su significado para un CFD
   no está documentado por el bróker y no se usará sin verificarlo.

## Zona horaria

La API documenta UTC, pero la última barra del viernes es 23:56 y el último tick 23:56:58,
convertidos directamente desde el epoch. El oro cierra los viernes a las 17:00 de Nueva York
(21:00 UTC en horario de verano). Eso es coherente con marcas en **hora del servidor UTC+3**
(horario de verano de IC Markets). **Es una inferencia, no una medición.**

`check-environment` mide el desfase comparando el último tick con el reloj del PC, y solo
lo acepta si el tick tiene menos de 5 minutos. Hoy el mercado está cerrado y el resultado es
"no verificable". Hay que repetir el comando con el mercado abierto (desde el domingo
~21:00 UTC) y documentar también cuándo pasa a UTC+2 (horario de invierno). Hasta entonces
las marcas se guardan tal cual, como "hora del servidor", sin convertir.

## Limitaciones conocidas

- Desfase horario sin verificar (ver arriba).
- Comisión del bróker no disponible en la API.
- Ticks solo de los últimos 6 meses en este terminal.
- El spread de las barras no representa el coste real.
- Las especificaciones (swap, margen) pueden cambiar; se registran con fecha en cada informe.
