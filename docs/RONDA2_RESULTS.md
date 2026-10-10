# Resultados del filtro de backtest de la ronda 2

**Fecha**: 2026-10-10. Protocolo: [PREREGISTRO_RONDA2.md](PREREGISTRO_RONDA2.md) (commit 53b2818,
guardado antes de ejecutar nada), que reutiliza sin cambios el de la fase E. Código:
`experiments/ronda2/run.py`. Sin desviaciones del pre-registro.

> Recordatorio del pre-registro: la prueba final 2025-2026 está parcialmente gastada y este
> backtest solo filtra. Un veredicto distinto de REJECTED solo habría hecho la hipótesis
> elegible para paper trading.

## Veredictos (prueba final 2025-01-01 a 2026-10-09, escenario base)

| Candidata | Veredicto | Motivo |
|---|---|---|
| CAND-VOLX-NR7-v1 | **REJECTED** | falla 6 de 7 estrictas; solo 7 operaciones en la prueba final |
| CAND-REGIME-HMM-v1 | **REJECTED** | **0 operaciones en la prueba final**: sus 188 señales las bloquea el control de volumen mínimo; falla 6 de 7 estrictas |
| CAND-VWAP-MR-v1 | **REJECTED** | falla 6 de 7 estrictas; PF por debajo de 1 en los 10 años |

Ninguna pasa el filtro. **Ninguna hipótesis queda elegible para paper trading en esta ronda.**

## Métricas de la prueba final (base)

| Métrica | Umbral | NR7 | REGIME-HMM | VWAP-MR |
|---|---|---|---|---|
| Operaciones | ≥ 300 | 7 ✗ | 0 ✗ | 1 007 ✓ |
| PF | ≥ 1,15 | 0,36 ✗ | – ✗ | 0,90 ✗ |
| IC90 del PF | inferior > 1,0 | 0,00-1,17 ✗ | – ✗ | 0,81-1,00 ✗ |
| DD máximo | < 20 % | 0,8 % ✓ | 0 % ✓ | 24,2 % ✗ |
| Sharpe | > 1,0 | −0,75 ✗ | – ✗ | −0,97 ✗ |
| Sortino | > 1,0 | −0,87 ✗ | – ✗ | −1,26 ✗ |
| Calmar | > 0,5 | −0,44 ✗ | – ✗ | −0,53 ✗ |
| Expectancy | > 0,10 R | −0,19 ✗ | – ✗ | −0,05 ✗ |
| Beneficio neto (USD) | | −64 | 0 | −2 294 |
| Placebo (p) | < 0,05 | 1,00 | – | 0,66 |
| DSR (N = 9) | ≥ 0,95 | 0,001 | – | 0,001 |

## Por periodo (base): PF, operaciones y neto

| | In-sample 2017-2022 | Validación 2023-2024 | Prueba final 2025-2026 |
|---|---|---|---|
| NR7 | 0,91 (81; −101 USD) | 1,17 (31; +46 USD; placebo p = 0,03) | 0,36 (7; −64 USD) |
| REGIME-HMM | 1,09 (533; +231 USD) | 0,87 (200; −136 USD) | sin operaciones |
| VWAP-MR | 0,88 (3 279; −9 690 USD) | 0,93 (1 276; −2 173 USD) | 0,90 (1 007; −2 294 USD) |

Año a año (PF base): VWAP-MR queda entre 0,76 y 0,94 **todos los años**, sin excepción: es el
rechazo más claro de las tres. NR7 oscila entre 0,15 y 3,13 con 7 a 18 operaciones al año:
demasiado pocas para distinguir nada del ruido. REGIME-HMM queda entre 0,77 y 1,47 de 2019 a 2024
y no opera ni en 2017-2018 (falta de historia, previsto) ni en 2025-2026.

## Robustez a costes (prueba final, PF)

| | Base | Adverso | Estrés |
|---|---|---|---|
| NR7 | 0,36 | 0,36 | 0,34 |
| REGIME-HMM | sin operaciones | sin operaciones | sin operaciones |
| VWAP-MR | 0,90 | 0,89 | 0,80 |

In-sample, REGIME-HMM pasa de un PF de 1,09 (base) a 1,04 (adverso) y 0,91 (estrés): su único
tramo positivo no sobrevive al coste de estrés.

## Sensibilidad al 2020-03-26

Ninguna de las tres tenía posición abierta en ese minuto. NR7 y REGIME-HMM no cambian. VWAP-MR
cambia en 16 USD sobre −2 378 en 2020, porque al quitar la vela cambian el ATR y el VWAP de ese día.

## Hallazgos que conviene leer

1. **REGIME-HMM no opera en la prueba final, pero no por el régimen.**
   - El HMM sí da días tranquilos: la probabilidad del régimen volátil queda por debajo de 0,5 en
     el 58 % de los días de 2025 y en el 19 % de los de 2026. La estrategia generó 151 señales en
     2025 y 37 en 2026.
   - **Las bloqueó todas el control de riesgo.** Con un stop de 2 ATR diarios y la volatilidad
     actual del oro, el volumen mínimo de 0,01 lotes ya arriesga entre 56 y 373 USD. El límite es de
     50 USD: el 0,5 % del balance virtual de 10 000 USD. El motor no redondea hacia arriba (regla
     de la fase C), así que no opera. En 2024 ocurrió lo mismo con 157 de 203 señales.
   - Para el criterio pre-registrado el resultado es REJECTED, porque falla más de 2 estrictas.
     La hipótesis **no llegó a contrastarse** en la prueba final.
   - **No se ha cambiado nada** para que opere. Cambiar el stop, el riesgo o el balance sería una
     variante nueva (v2) y contaría en el DSR.
   - Es un dato útil para la fase H: con stops diarios, operar 0,01 lotes al 0,5 % de riesgo
     exigiría hoy un balance de unos 11 000 a 75 000 USD.
2. **NR7 genera muy pocas operaciones**: 135 señales en 9,5 años (unas 14 al año), porque exige un
   día NR7 y que la primera ruptura caiga dentro de la ventana. Con ese número, ningún resultado
   (ni el p = 0,03 de la validación) es interpretable.
3. **VWAP-MR pierde de forma estable**: con más de 5 500 operaciones y PF < 1 todos los años, la
   reversión al VWAP por ticks no tiene ventaja en XAUUSD con estas reglas.

## Registro

`configs/research.yaml`: las 3 variantes pasan a `variants_tested: 1` y el total de variantes
probadas sube a **9**. Las fichas de [STRATEGY_RESEARCH.md](STRATEGY_RESEARCH.md) recogen los
resultados y la causa probable de cada fallo.

## Detalles de la ejecución

- Código evaluado: commit 53b2818. Datos validados de 2017-04-06 a 2026-10-09. Duración: 7 minutos.
- Señales: NR7 135, REGIME-HMM 1 268 (la mitad se rechazan con posición abierta) y VWAP-MR 22 845
  (17 283 rechazadas con posición abierta, como estaba previsto).
- Placebo: las mismas 1 000 semillas de la fase E (`experiments/phase_e/placebo.csv`).
