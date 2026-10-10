# Resultados de la fase E

**Fecha**: 2026-10-10. Evaluación según [PREREGISTRO_PHASE_E.md](PREREGISTRO_PHASE_E.md)
(commit 9761a90, guardado antes de ejecutar nada). Código de la evaluación:
`experiments/phase_e/run.py`. Ninguna regla, parámetro ni umbral cambió después de ver
resultados. No hubo desviaciones del pre-registro.

> Ninguno de estos resultados garantiza rentabilidad futura. Los de la referencia de cruce de
> medias tampoco: ver "Observación sobre REF-SMACROSS-v1".

## Veredictos (prueba final 2025-01-01 a 2026-10-09, escenario base)

| Candidata | Veredicto | Motivo |
|---|---|---|
| CAND-ORB-NY-v1 | **REJECTED** | falla 6 de 7 estrictas y las 4 flexibles |
| CAND-IMOM-NY-v1 | **REJECTED** | falla 5 de 7 estrictas y 3 flexibles |
| CAND-TREND-ATR-v1 | **REJECTED** | falla 5 de 7 estrictas y 3 flexibles |

**No se ha encontrado ninguna estrategia validada.** Ninguna candidata supera a las referencias
ni al placebo aleatorio.

## Métricas de la prueba final (escenario base, 0,5 % de riesgo por operación)

| Métrica | Umbral | ORB-NY | IMOM-NY | TREND-ATR | REF-SMACROSS | REF-RANDOM (semilla oficial) |
|---|---|---|---|---|---|---|
| Operaciones | ≥ 300 | 453 ✓ | 420 ✓ | 697 ✓ | 601 | 265 |
| PF | ≥ 1,15 | 0,898 ✗ | 0,987 ✗ | 1,003 ✗ | 1,247 | 0,782 |
| IC90 del PF | inferior > 1,0 | 0,68-1,14 ✗ | 0,81-1,21 ✗ | 0,88-1,15 ✗ | 1,03-1,49 | 0,63-0,98 |
| DD máximo | < 20 % | 28,9 % ✗ | 2,0 % ✓ | 13,0 % ✓ | 10,9 % | 12,5 % |
| Sharpe | > 1,0 | −0,62 ✗ | −0,07 ✗ | 0,08 ✗ | 1,53 | −1,31 |
| Sortino | > 1,0 | −1,41 ✗ | −0,09 ✗ | 0,12 ✗ | 2,79 | −1,67 |
| Calmar | > 0,5 | −0,32 ✗ | −0,07 ✗ | 0,02 ✗ | 2,67 | −0,46 |
| Expectancy | > 0,10 R | −0,067 ✗ | −0,000 ✗ | −0,008 ✗ | 0,201 | −0,102 |
| SQN | > 1,5 | −0,34 ✗ | −0,02 ✗ | −0,06 ✗ | 0,85 | −1,22 |
| Recovery factor | > 2,0 | −0,44 ✗ | −0,11 ✗ | 0,03 ✗ | 4,05 | −0,81 |
| Ulcer Index | < 10 | 12,7 ✗ | 1,3 ✓ | 6,7 ✓ | 3,6 | 8,3 |
| Beneficio neto (USD) | | −1 515 | −23 | +48 | +5 298 | −1 010 |
| DSR (N = 6) | ≥ 0,95 | 0,009 | 0,041 | 0,061 | | |

PBO: no aplicable (no hubo búsqueda de parámetros; pre-registro, sección 7). REF-NOTRADE-v1: 0
operaciones y 0 USD en todos los periodos.

## Walk-forward: PF por fold (base)

| Fold (año de prueba) | ORB-NY | IMOM-NY | TREND-ATR | REF-SMACROSS | REF-RANDOM |
|---|---|---|---|---|---|
| 1 (2023) | 0,93 | 0,69 | 0,93 | 0,71 | 1,03 |
| 2 (2024) | 0,78 | 0,92 | 0,88 | 0,93 | 1,04 |
| 3 (2025) | 1,04 | 0,94 | 1,02 | 1,09 | 0,73 |
| 4 (2026) | 0,68 | 1,07 | 0,97 | 1,45 | 0,87 |
| Agregado 2023-2026 | 0,88 | 0,88 | 0,95 | 1,03 | 0,92 |

Ninguna candidata supera un PF de 1,1 en ningún fold. La validación (2023-2024)
ya era negativa para las tres: PF de 0,86, 0,80 y 0,91.

## Frente a las referencias y al placebo (prueba final, base)

| | ORB-NY | IMOM-NY | TREND-ATR |
|---|---|---|---|
| Frente a no operar (neto > 0) | no (−1 515) | no (−23) | sí, por muy poco (+48) |
| Frente a cruce de medias (PF y expectancy mayores) | no | no | no |
| Frente al placebo de 1 000 semillas (p < 0,05) | no (p = 0,68) | no (p = 0,39) | no (p = 0,33) |

**Distribución del placebo** (1 000 semillas, mismas restricciones, costes y segmentos):

| Periodo | PF p5 | PF mediana | PF p95 | Expectancy mediana | Neto mediano | % semillas con PF > 1 |
|---|---|---|---|---|---|---|
| Prueba final 2025-2026 | 0,76 | 0,95 | 1,21 | −0,018 R | −221 USD | 34 % |
| Validación 2023-2024 | 0,73 | 0,90 | 1,13 | −0,038 R | −515 USD | 23 % |

Para superar el placebo en la prueba final hacía falta un PF por encima de 1,21. Las tres
candidatas están dentro de lo que produce operar al azar con los mismos costes.

## Robustez a costes (prueba final: PF y neto en USD)

| | Base | Adverso | Estrés |
|---|---|---|---|
| ORB-NY | 0,898 / −1 515 | 0,877 / −1 791 | 0,792 / −2 873 |
| IMOM-NY | 0,987 / −23 | 0,863 / −250 | 0,547 / −978 |
| TREND-ATR | 1,003 / +48 | 0,977 / −435 | 0,888 / −1 984 |
| REF-SMACROSS | 1,247 / +5 298 | 1,229 / +4 823 | 1,183 / +3 710 |

IMOM-NY es la más sensible al coste: opera en la última media hora antes del cierre de las
16:00 NY, cuando el spread sube (COST_MODEL.md).

## Sensibilidad al 2020-03-26 10:23 (año 2020, base)

| | Posición abierta en ese minuto | Neto con / sin | PF con / sin |
|---|---|---|---|
| ORB-NY | no | +988 / +988 | 1,106 / 1,106 |
| IMOM-NY | no | −349 / −349 | 0,769 / 0,769 |
| TREND-ATR | no | +2 366 / +2 391 | 1,195 / 1,197 |
| REF-SMACROSS | **sí** | +1 462 / +1 684 | 1,116 / 1,135 |
| REF-RANDOM | no | +30 / +30 | 1,013 / 1,013 |

Ninguna candidata tenía posición abierta en ese minuto. TREND-ATR cambia ligeramente porque sin
esa vela cambian el ATR y alguna señal posterior. La cotización no afecta a la prueba final.

## Año a año (base, PF y operaciones)

| Año | ORB-NY | IMOM-NY | TREND-ATR |
|---|---|---|---|
| 2017 (desde abril) | 0,96 (189) | 0,54 (183) | 0,92 (287) |
| 2018 | 0,83 (257) | 0,35 (248) | 1,20 (405) |
| 2019 | 1,01 (258) | 0,53 (247) | 0,86 (452) |
| 2020 | 1,11 (258) | 0,77 (248) | 1,19 (401) |
| 2021 | 1,01 (257) | 0,83 (250) | 0,88 (416) |
| 2022 | 1,34 (256) | 1,11 (249) | 0,89 (439) |
| 2023 | 0,93 (255) | 0,69 (248) | 0,93 (432) |
| 2024 | 0,78 (259) | 0,92 (248) | 0,88 (454) |
| 2025 | 1,04 (257) | 0,94 (247) | 1,02 (410) |
| 2026 (hasta 9-oct) | 0,68 (196) | 1,07 (173) | 0,97 (287) |

In-sample 2017-2022 (base): ORB-NY PF 1,05 (+2 750 USD, pero negativo en el escenario adverso),
IMOM-NY 0,67 y TREND-ATR 1,00. Ningún resultado positivo es estable de un año a otro.

## Por sesión (hora de entrada en Nueva York, todo el historial, base)

| | Asia | Londres | Nueva York | Cierre |
|---|---|---|---|---|
| ORB-NY | | | 2 442 op., PF 0,99 | |
| IMOM-NY | | | | 2 341 op., PF 0,74 |
| TREND-ATR | | 1 615 op., PF 0,94 | 2 368 op., PF 1,01 | |

ORB-NY e IMOM-NY operan en una sola sesión por definición. TREND-ATR no muestra ventaja en
ninguna de sus dos sesiones.

## Observación sobre REF-SMACROSS-v1 (no cambia ningún veredicto)

La referencia de cruce de medias **cumple las 7 métricas estrictas en la prueba final**
(PF 1,25, IC90 inferior 1,03, Sharpe 1,53, p = 0,029 frente al placebo) y resiste el escenario
de estrés. Pero:

- Es una referencia, no una candidata. Promoverla ahora sería elegir una regla **después** de
  ver su resultado en la prueba final, que queda gastada para ella.
- Fuera de la prueba final es negativa: validación PF 0,83 con un DD del 42,5 %, in-sample
  PF 0,97 y PF 0,71 en 2023. Casi todo el resultado de la prueba final viene de 2026 (PF 1,45,
  +4 274 USD), un año de fuerte tendencia del oro. Es coherente con una regla de tendencia que
  funciona en un régimen concreto, no con una ventaja estable.
- Con 6 variantes probadas y este patrón por años, la evidencia es débil.

Si Juan quiere investigarla, tendría que ser una hipótesis nueva, pre-registrada y probada solo
con datos que todavía no existen (paper trading hacia delante), contando esta prueba en el DSR.

## Detalles de la ejecución

- Datos: M1, M15 y H1 validados (fase B), de 2017-04-06 a 2026-10-09. Código evaluado: commit
  9761a90. Duración: 8 minutos la evaluación y 4,5 minutos el placebo.
- Señales generadas: ORB 2 449, IMOM 2 362, TREND 9 072, SMACROSS 5 187 y RANDOM 1 445. La mayoría
  de las de TREND (5 075) se rechazan porque ya hay una posición abierta, como estaba previsto.
- Casos de stop y objetivo en la misma barra: 1 en todo el historial (TREND, resuelto con el
  supuesto conservador). Salidas por hueco: ORB 6 y TREND 13.
- Resultados completos (no versionados): `experiments/phase_e/results.json` y `placebo.csv`.

## Registro

`configs/research.yaml`: las 6 variantes pasan a `variants_tested: 1` (`variants_tested_total: 6`),
con su veredicto. Las fichas de `docs/STRATEGY_RESEARCH.md` recogen los resultados y la causa
probable de cada fallo.
