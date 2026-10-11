"""Correcciones por pruebas múltiples de la fase F (docs/PREREGISTRO_PHASE_F.md).

Implementación propia a partir de las referencias académicas, sin dependencias externas:

- PSR: Bailey y López de Prado (2012), "The Sharpe Ratio Efficient Frontier".
- DSR: Bailey y López de Prado (2014), "The Deflated Sharpe Ratio".
- FDR: Benjamini y Hochberg (1995), "Controlling the False Discovery Rate".
- PBO por CSCV: Bailey, Borwein, López de Prado y Zhu (2017), "The Probability of
  Backtest Overfitting".

Las librerías jsharpe y nullius se usan solo para contrastar estos cálculos
(tests/unit/test_statistical_corrections.py y el informe de la fase F).

Todos los Sharpe son POR PERIODO (por día), no anualizados. La curtosis es la no
centrada (normal = 3).
"""

from __future__ import annotations

import math
from itertools import combinations
from statistics import NormalDist

import numpy as np

_N = NormalDist()
EULER_GAMMA = 0.5772156649015329


def moments(returns: np.ndarray) -> tuple[float, float, float, int]:
    """(Sharpe por periodo, asimetría, curtosis no centrada, T) de una serie de retornos."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    t = len(r)
    if t < 4:
        return float("nan"), float("nan"), float("nan"), t
    sd = r.std(ddof=1)
    if sd == 0:
        return 0.0, 0.0, 3.0, t
    z = (r - r.mean()) / r.std()
    return float(r.mean() / sd), float(np.mean(z ** 3)), float(np.mean(z ** 4)), t


def psr(sr: float, sr0: float, t: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    """Probabilistic Sharpe Ratio: P[SR verdadero > sr0] dado el SR observado en t periodos."""
    if not (np.isfinite(sr) and np.isfinite(sr0)) or t < 2:
        return float("nan")
    var = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2
    return float(_N.cdf((sr - sr0) * math.sqrt(t - 1) / math.sqrt(max(var, 1e-12))))


def sharpe_pvalue(returns: np.ndarray) -> float:
    """p-valor unilateral de H0: Sharpe <= 0 (exceso de retorno sobre cero) = 1 - PSR(0)."""
    sr, skew, kurt, t = moments(returns)
    p = psr(sr, 0.0, t, skew, kurt)
    return float("nan") if not np.isfinite(p) else 1.0 - p


def expected_max_sharpe(n_trials: int, var_trials: float) -> float:
    """Máximo esperado del Sharpe de n_trials pruebas sin habilidad (SR0 del DSR)."""
    if n_trials <= 1 or var_trials <= 0:
        return 0.0
    z1 = _N.inv_cdf(1 - 1 / n_trials)
    z2 = _N.inv_cdf(1 - 1 / (n_trials * math.e))
    return math.sqrt(var_trials) * ((1 - EULER_GAMMA) * z1 + EULER_GAMMA * z2)


def deflated_sharpe(returns: np.ndarray, n_trials: int, var_trials: float) -> dict[str, float]:
    """DSR = PSR frente al máximo esperado de n_trials pruebas sin habilidad.

    var_trials: varianza de los Sharpe por periodo de las pruebas realizadas.
    """
    sr, skew, kurt, t = moments(returns)
    sr0 = expected_max_sharpe(n_trials, var_trials)
    return {"dsr": psr(sr, sr0, t, skew, kurt), "sr": sr, "sr0": sr0, "skew": skew, "kurt": kurt, "t": t}


def benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    """q-valores de Benjamini-Hochberg (p ajustados). NaN se tratan como p = 1."""
    p = np.asarray(pvalues, dtype=float)
    p = np.where(np.isfinite(p), p, 1.0)
    m = len(p)
    if m == 0:
        return p
    order = np.argsort(p, kind="mergesort")
    ranked = p[order] * m / np.arange(1, m + 1)
    q_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    q = np.empty(m)
    q[order] = np.minimum(q_sorted, 1.0)
    return q


def _sharpe_cols(x: np.ndarray) -> np.ndarray:
    mu = x.mean(axis=0)
    sd = x.std(axis=0, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(sd > 0, mu / sd, 0.0)


def pbo_cscv(returns_matrix: np.ndarray, n_splits: int = 16) -> dict[str, float]:
    """Probabilidad de sobreajuste del backtest por validación cruzada combinatoria simétrica.

    returns_matrix: T x N (retornos por periodo de N variantes en las mismas fechas).
    Se evalúan TODAS las combinaciones C(S, S/2). Para cada una se elige la variante con
    mayor Sharpe dentro de muestra y se mide su rango relativo fuera de muestra
    (omega = rango / (N + 1), lambda = logit(omega)). PBO = fracción con lambda <= 0.
    """
    m = np.asarray(returns_matrix, dtype=float)
    t, n = m.shape
    if n < 2 or n_splits % 2 or t < 2 * n_splits:
        raise ValueError("se necesitan >= 2 variantes, S par y T >= 2S")
    blocks = np.array_split(np.arange(t), n_splits)
    lambdas, oos_best, is_best = [], [], []
    for is_blocks in combinations(range(n_splits), n_splits // 2):
        chosen = set(is_blocks)
        is_rows = np.concatenate([blocks[b] for b in is_blocks])
        oos_rows = np.concatenate([blocks[b] for b in range(n_splits) if b not in chosen])
        sr_is, sr_oos = _sharpe_cols(m[is_rows]), _sharpe_cols(m[oos_rows])
        star = int(np.argmax(sr_is))
        ranks = np.empty(n)
        ranks[np.argsort(sr_oos, kind="mergesort")] = np.arange(1, n + 1)
        omega = ranks[star] / (n + 1.0)
        lambdas.append(math.log(omega / (1 - omega)))
        oos_best.append(sr_oos[star])
        is_best.append(sr_is[star])
    lam, oos_best, is_best = np.array(lambdas), np.array(oos_best), np.array(is_best)
    slope = float(np.polyfit(is_best, oos_best, 1)[0]) if np.ptp(is_best) > 0 else float("nan")
    return {"pbo": float(np.mean(lam <= 0)), "median_logit": float(np.median(lam)), "n_combos": int(len(lam)),
            "oos_sr_of_is_best_median": float(np.median(oos_best)),
            "prob_oos_loss": float(np.mean(oos_best < 0)), "degradation_slope": slope}
