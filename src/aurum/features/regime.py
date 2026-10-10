"""Modelo oculto de Markov gaussiano de 2 estados (Hamilton, 1989), implementado con numpy.

Uso sin fuga de información:
- `fit_hmm` se ajusta SOLO con retornos anteriores al periodo en que se aplicará
  (la estrategia lo reajusta una vez al año con los días completos previos al 1 de enero).
- `filter_probs` es el filtro hacia delante: la probabilidad de cada estado en el día k usa
  solo los retornos hasta k. No se usa el suavizado (forward-backward), que mira al futuro.

El ajuste es determinista: inicialización fija, número máximo de iteraciones y tolerancia fijos.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_LOG2PI = np.log(2 * np.pi)


@dataclass(frozen=True)
class HMM2:
    means: np.ndarray        # (2,)
    variances: np.ndarray    # (2,)
    trans: np.ndarray        # (2, 2), filas suman 1
    start: np.ndarray        # (2,) probabilidad del estado al final del entrenamiento
    loglik: float
    iterations: int

    @property
    def high_vol_state(self) -> int:
        return int(np.argmax(self.variances))


def _emission(x: np.ndarray, means: np.ndarray, variances: np.ndarray) -> np.ndarray:
    """Densidades gaussianas (n, 2)."""
    d = x[:, None] - means[None, :]
    return np.exp(-0.5 * (_LOG2PI + np.log(variances)[None, :] + d * d / variances[None, :]))


def _forward(x: np.ndarray, means, variances, trans, init) -> tuple[np.ndarray, np.ndarray]:
    """Filtro hacia delante normalizado. Devuelve (alpha (n,2), factores de escala (n,))."""
    b = _emission(x, means, variances)
    n = len(x)
    alpha = np.empty((n, 2))
    scale = np.empty(n)
    a = init * b[0]
    scale[0] = a.sum()
    alpha[0] = a / scale[0]
    for k in range(1, n):
        a = (alpha[k - 1] @ trans) * b[k]
        scale[k] = a.sum()
        alpha[k] = a / scale[k]
    return alpha, scale


def fit_hmm(x: np.ndarray, max_iter: int = 200, tol: float = 1e-6, var_floor: float = 1e-12) -> HMM2:
    """Baum-Welch para 2 estados gaussianos con inicialización fija:
    medias 0, varianzas 0,5 y 2 veces la varianza muestral, permanencia 0,95."""
    x = np.asarray(x, dtype=float)
    v = max(float(x.var()), var_floor)
    means = np.zeros(2)
    variances = np.array([0.5 * v, 2.0 * v])
    trans = np.array([[0.95, 0.05], [0.05, 0.95]])
    init = np.array([0.5, 0.5])
    prev = -np.inf
    it = 0
    for it in range(1, max_iter + 1):
        b = _emission(x, means, variances)
        alpha, scale = _forward(x, means, variances, trans, init)
        n = len(x)
        beta = np.empty((n, 2))
        beta[-1] = 1.0
        for k in range(n - 2, -1, -1):
            beta[k] = (trans @ (b[k + 1] * beta[k + 1])) / scale[k + 1]
        gamma = alpha * beta
        gamma /= gamma.sum(axis=1, keepdims=True)
        xi = (alpha[:-1, :, None] * trans[None, :, :] * (b[1:] * beta[1:])[:, None, :]) / scale[1:, None, None]
        loglik = float(np.log(scale).sum())
        init = gamma[0]
        trans = xi.sum(axis=0) / gamma[:-1].sum(axis=0)[:, None]
        trans /= trans.sum(axis=1, keepdims=True)
        w = gamma.sum(axis=0)
        means = (gamma * x[:, None]).sum(axis=0) / w
        variances = np.maximum((gamma * (x[:, None] - means[None, :]) ** 2).sum(axis=0) / w, var_floor)
        if loglik - prev < tol:
            break
        prev = loglik
    alpha, _ = _forward(x, means, variances, trans, init)
    return HMM2(means, variances, trans, alpha[-1], loglik, it)


def filter_probs(model: HMM2, x_new: np.ndarray) -> np.ndarray:
    """Probabilidades filtradas de cada estado para retornos posteriores al entrenamiento.

    Parte de la probabilidad al final del entrenamiento y avanza un paso por retorno.
    """
    x_new = np.asarray(x_new, dtype=float)
    if len(x_new) == 0:
        return np.empty((0, 2))
    prior = model.start @ model.trans
    alpha, _ = _forward(x_new, model.means, model.variances, model.trans, prior)
    return alpha
