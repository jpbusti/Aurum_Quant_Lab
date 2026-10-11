# Pre-registro: auditoría post-fase E y límite de riesgo del 2 %

**Fecha**: 2026-10-11 (hora UTC del commit). **Decisión de**: Juan (mensaje del 2026-10-11,
00:06 UTC). **Redactado por**: Claude, antes de ejecutar ningún cálculo con el 2 %.
**Firma**: este documento y su commit en git, que fija la fecha y el contenido.

## 1. Cambio

Se añade un segundo límite de riesgo por operación: **2 % del balance**, además del 0,5 % de
referencia original (`configs/risk.yaml`). Los dos se corren por separado. **El 0,5 % no se
sustituye.**

## 2. Motivo y justificación

- **Motivo (Juan)**: ver el efecto de subir el riesgo por operación sobre las señales que hoy
  bloquea el control de volumen mínimo. Con el 0,5 % de 10 000 USD (50 USD), 0,01 lotes con un
  stop de 2 ATR diarios ya superan el límite (RONDA2_RESULTS.md).
- **Justificación técnica**: el bloqueo depende del cociente entre el riesgo de 0,01 lotes y el
  riesgo permitido. Cambiar ese límite es la forma explícita y documentada de medir cuánto de
  cada rechazo se debe al capital y cuánto a la estrategia. No cambia ninguna regla de señal.
- **Advertencia**: el 2 % es **4 veces** el riesgo por operación del 0,5 % (2 / 0,5 = 4), no el
  doble. Es más agresivo y está más cerca del límite de ruina: 10 pérdidas seguidas al 2 %
  dejan el balance en 0,98^10 ≈ 81,7 %, frente a 0,995^10 ≈ 95,1 % al 0,5 %. No se asume que el 2 %
  sea mejor.

## 3. Reglas fijadas antes de ver resultados

1. Se aplica **a las 9 variantes probadas por igual**: REF-NOTRADE-v1, REF-RANDOM-v1,
   REF-SMACROSS-v1, CAND-ORB-NY-v1, CAND-IMOM-NY-v1, CAND-TREND-ATR-v1, CAND-VOLX-NR7-v1,
   CAND-REGIME-HMM-v1 y CAND-VWAP-MR-v1. No es selectivo.
2. **Balance virtual sin cambios: 10 000 USD.** Las cifras de 200, 1 000 y 50 000 USD son solo
   análisis de viabilidad de la capa 2, no backtests nuevos.
3. Todo lo demás, igual que en el pre-registro de la fase E: datos, periodos, folds, purga,
   costes (escenario base para la comparación principal), métricas y umbrales. Los límites
   operativos de pérdida diaria y drawdown siguen desactivados.
4. El límite no se cambia después de ver resultados. No hay un tercer nivel.
5. **Los veredictos pre-registrados (fase E y ronda 2) no se reescriben.** Los resultados con el
   2 % son una sensibilidad sobre datos ya gastados: no pueden convertir una variante en
   CANDIDATE_FOR_PAPER. Si con el 2 % una variante cambiara de forma relevante, eso solo podría
   justificar una prueba nueva con datos futuros (paper trading), nunca una aprobación.
6. Estas ejecuciones se registran como pruebas adicionales en `configs/research.yaml`
   (sensibilidad de tamaño, 9 ejecuciones), aunque no crean variantes nuevas de señal.

## 4. Separación de capas

- **Capa 1, señales**: lo que decide cada estrategia, independiente del capital. Se cuentan
  todas las señales generadas.
- **Capa 2, ejecutabilidad con balance X y riesgo f**, señal a señal y sin el efecto de
  posiciones abiertas:
  - entrada estimada = apertura de la primera barra M1 en o después de la decisión, + spread base
    + slippage base (compras) o − slippage (ventas);
  - riesgo de 0,01 lotes = |entrada − stop con slippage| × 1 USD por cada 1,0 de precio + 0,07 USD
    de comisión de ida y vuelta;
  - ejecutable si 0,01 lotes arriesgan ≤ f × X **y** el margen de 0,01 lotes ≤ X.
- **Motor completo**: además, las ejecuciones reales del motor con el 0,5 % y con el 2 %, con
  los rechazos por motivo (volumen mínimo, posición abierta, margen, etc.).

## 5. Qué se reporta

1. Errores y limitaciones detectados.
2. Cálculo de riesgo a mano para un día concreto de REGIME-HMM, con el 0,5 % y con el 2 %.
3. Verificación de contrato, valor por punto, comisión, spread, slippage y margen frente a MT5.
4. Tabla por variante: señales de la capa 1 y ejecutables de la capa 2 con el 0,5 % y con el 2 %
   (diferencia), en todo el historial y en 2025-2026.
5. Métricas y drawdown con el 0,5 % y con el 2 %. El efecto esperado sobre el drawdown es de
   unas **4 veces** en drawdowns pequeños; con drawdowns grandes, algo menos por la composición.
6. Clasificación de las 9 variantes: REJECTED por rendimiento, rechazada por evidencia
   insuficiente, o no evaluada por bloqueo operativo.
7. Viabilidad con 200, 1 000, 10 000 y 50 000 USD con ambos límites (PHASE_H_VIABILITY.md).
8. Estado de la muestra: qué datos se usaron para elegir o descartar hipótesis.
9. Recomendación: paper trading, más investigación o cierre.
