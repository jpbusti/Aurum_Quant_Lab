# Pre-registro de la fase F: familias con corrección por pruebas múltiples

**Fecha**: 2026-10-11, antes de ejecutar ninguna variante de la fase F. Familias y rejillas
en [FAMILIES_RESEARCH.md](FAMILIES_RESEARCH.md). Código: `experiments/phase_f/run.py`,
`src/aurum/evaluation/screening.py` y `src/aurum/validation/statistical_corrections.py`.

Nada de este documento se cambiará después de ver resultados. Cualquier desviación se
anotará en PHASE_F_FAMILIES.md como desviación, con su motivo.

## 1. Estado de los datos

- **La muestra 2017-04-06 a 2026-10-09 está gastada** por las fases E, la ronda 2 y la
  auditoría. Ningún resultado de esta fase es una validación.
- Si alguna variante sobrevive, solo podrá pasar a **paper trading con datos posteriores al
  2026-10-09**, pre-registrada antes de empezar.
- Las exclusiones de datos son las de `configs/data.yaml`.

## 2. Ejecución

- Periodo único continuo: de 2017-04-06 01:00 a 2026-10-10 (hora del servidor). Las señales
  cuyo cierre por tiempo máximo cae después del final se descartan.
- Motor de AURUM, escenario de costes **base**, sin límites de pérdida diaria ni de drawdown,
  como en la fase E. Una posición a la vez.
- Dos capas (auditoría post-fase E):
  - **Capa de capital (principal)**: 10 000 USD virtuales y riesgo del 0,5 % por operación.
    Las señales cuyo volumen mínimo arriesga más del 0,5 % se rechazan y se cuentan.
  - **Capa de señal (secundaria)**: 0,01 lotes fijos, sin depender del balance. Se aplican
    las mismas pruebas y se informan, pero **el veredicto se basa en la capa de capital**.
- Serie de evaluación: retornos diarios de la equity al cierre de cada día del servidor con
  barras, incluidos los días sin posición (retorno 0).

## 3. Métricas por variante

PF, extremo inferior del IC90 del PF (bootstrap por bloques, como en la fase E), drawdown
máximo, Sharpe, Sortino, Calmar, número de operaciones, señales rechazadas y su motivo, y
Sharpe y retorno por periodo (2017-2022, 2023-2024 y 2025-2026), solo como descripción.

## 4. Pruebas estadísticas

Implementación propia (`statistical_corrections.py`) a partir de las referencias. Las
librerías externas solo la contrastan (sección 7).

- **Sharpe diario** SR, asimetría γ3 y curtosis no centrada γ4 de los retornos diarios.
- **PSR** (Bailey y López de Prado, 2012):
  Φ((SR − SR0)·√(T − 1) / √(1 − γ3·SR + (γ4 − 1)/4·SR²)).
- **p-valor** del exceso de retorno: unilateral, H0: SR ≤ 0, p = 1 − PSR(SR0 = 0).
- **FDR**: q-valores de Benjamini y Hochberg (1995) **dentro de cada familia** (principal).
  También se informa el q global sobre las 224 variantes.
- **DSR** (Bailey y López de Prado, 2014): PSR frente al máximo esperado de N pruebas sin
  habilidad. N = **233** (224 nuevas + las 9 anteriores del proyecto). La varianza de los
  Sharpe diarios se calcula sobre las 224 variantes de la fase F en la capa de capital.
- **PBO por CSCV** (Bailey, Borwein, López de Prado y Zhu, 2017), por familia: matriz de
  retornos diarios días × variantes, S = 16 bloques contiguos, **todas** las C(16, 8) = 12 870
  combinaciones, métrica de Sharpe. Se informan también la mediana del logit, la probabilidad
  de pérdida fuera de muestra de la mejor variante dentro de muestra y la pendiente de
  degradación.

## 5. Umbrales (fijados antes de ver resultados)

| Prueba | Pasa |
|---|---|
| FDR | q de la familia < **0,10** |
| DSR | DSR ≥ **0,95** |
| PBO de la familia | < **0,20** pasa; entre 0,20 y 0,50, aviso; ≥ **0,50**, falla |

Una variante **sobrevive** si pasa FDR y DSR. Las demás métricas (PF, IC90, drawdown,
Sharpe, etc.) se informan, pero no son un filtro adicional en esta fase.

## 6. Veredicto por familia (capa de capital)

| Veredicto | Condición |
|---|---|
| **EDGE_CANDIDATO** | Al menos una variante sobrevive (FDR y DSR) y el PBO de la familia es < 0,20 |
| **SIN_EDGE** | Ninguna variante pasa FDR, o el PBO de la familia es ≥ 0,50 |
| **INCONCLUSO** | Cualquier otro caso (pasan FDR pero no DSR, o PBO entre 0,20 y 0,50) |

Una familia no tiene ventaja solo porque una variante pase una prueba: necesita las tres.

## 7. Contraste con librerías externas

Revisadas en PyPI y en su código fuente el 2026-10-11:

| Librería | Estado | Uso |
|---|---|---|
| jsharpe 0.6.3 (Thomas Schmelzer) | Existe; 17 versiones | Contraste del PSR. Su `control_for_FDR` **no es Benjamini-Hochberg**: calcula un Sharpe crítico con un FDR bayesiano que depende de una probabilidad previa p_H1 y de un Sharpe alternativo SR1. Se informa como dato complementario con q = 0,10, p_H1 = 0,05 y SR1 = 1,0 anual, sin efecto en el veredicto |
| nullius 0.1.0 | Existe; 2 versiones, de julio de 2026, un solo autor | Contraste del PBO (CSCV) y del DSR |
| pypbo | **No existe en PyPI** (404) | No se instala; el PBO es implementación propia |
| cpz-quant 1.2.0 | Existe; 3 versiones desde julio de 2026 | **No se instala**. Su certificación es una nota compuesta propia, no una prueba pre-registrada. Su PBO duplica el de nullius, y añade dependencias (polars, pydantic) que el laboratorio no necesita |

Las diferencias entre la implementación propia y las librerías se informan. En las
pruebas unitarias, el PBO y el DSR coinciden con nullius con una diferencia menor que 1e-9.

## 8. Sensibilidad (solo para supervivientes)

Si alguna variante sobrevive, se repite en la capa de capital con:

1. el escenario de costes **adverso**;
2. el escenario base con **12 puntos de slippage**, la media medida en los stops con el
   Strategy Tester ([VERIFICACION_TESTER.md](VERIFICACION_TESTER.md)). El motor aplica ese
   slippage a todas las ejecuciones a mercado y por stop, igual en todas las variantes.

Una superviviente solo se pre-registra para paper trading si mantiene un PF > 1 en las dos
sensibilidades. Si no, se informa como frágil.

## 9. Decisión final

- Si alguna familia es EDGE_CANDIDATO y su superviviente pasa la sensibilidad: pre-registro
  de esa variante para paper trading con datos posteriores al 2026-10-09. Sin dinero real.
- Si ninguna lo es: informe de cierre de la línea "XAUUSD M15 con reglas técnicas simples",
  sin buscar variantes nuevas sobre los mismos datos.
- Un resultado INCONCLUSO no se resuelve ampliando la rejilla sobre la misma muestra.

## 10. Registro

Las 224 variantes quedan en `configs/research.yaml` (bloque `phase_f`). Todas se informan,
incluidas las que no operan o pierden.
