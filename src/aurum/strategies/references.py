"""Referencias de comparación. NO son estrategias rentables: sirven para comprobar si una
candidata hace algo mejor que operar al azar, que una regla trivial o que no operar.
Parámetros fijados a priori (docs/STRATEGY_RESEARCH.md); no se optimizan.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aurum.features.indicators import atr, sma
from aurum.features.sessions import hhmm, ny_minute_of_day
from aurum.strategies.base import DataView, Strategy


def splitmix_uniform(seed: int | np.ndarray, t: int | np.ndarray, stream: int) -> np.ndarray:
    """Uniforme en [0, 1) determinista a partir de (semilla, instante, flujo), vectorizable.

    Hash splitmix64. Sustituye a numpy.random para poder generar 1 000 placebos sin bucles;
    no depende del orden de llamada ni de datos futuros.
    """
    with np.errstate(over="ignore"):
        x = (np.asarray(seed, dtype=np.uint64) * np.uint64(0x9E3779B97F4A7C15)
             ^ np.asarray(t, dtype=np.uint64) * np.uint64(0xBF58476D1CE4E5B9)
             ^ np.uint64(stream) * np.uint64(0x94D049BB133111EB))
        x = x + np.uint64(0x9E3779B97F4A7C15)
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        x = x ^ (x >> np.uint64(31))
    return (x >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def _in_ny_window(t: int, start: str, end: str) -> bool:
    m = int(ny_minute_of_day(t))
    (h1, m1), (h2, m2) = hhmm(start), hhmm(end)
    return h1 * 60 + m1 <= m < h2 * 60 + m2


class NoTrade(Strategy):
    """REF-NOTRADE: nunca opera. Resultado esperado: 0 operaciones y 0 costes."""

    name = "REF-NOTRADE-v1"
    signal_timeframe = "M15"

    def decide(self, view: DataView):
        return None


@dataclass(frozen=True)
class RandomParams:
    seed: int = 20261010
    probability: float = 0.0125       # ~0,6 entradas por día con 48 velas M15 elegibles
    ny_start: str = "03:00"           # ventana de entradas en hora de Nueva York
    ny_end: str = "15:00"
    atr_n: int = 14
    stop_atr: float = 2.0
    target_atr: float = 2.0
    max_hold_s: int = 4 * 3600


class RandomEntry(Strategy):
    """REF-RANDOM: entrada al azar con restricciones (ventana horaria, stop y objetivo por ATR).

    El azar depende solo de (semilla, instante de decisión), así que el resultado es
    reproducible y no cambia si se alteran datos futuros.
    """

    name = "REF-RANDOM-v1"
    signal_timeframe = "M15"

    def __init__(self, params: RandomParams = RandomParams()):
        self.p = params

    def decide(self, view: DataView):
        t = view.decision_time
        if not _in_ny_window(t, self.p.ny_start, self.p.ny_end):
            return None
        u = float(splitmix_uniform(self.p.seed, t, 0))
        coin = float(splitmix_uniform(self.p.seed, t, 1))
        if u >= self.p.probability:
            return None
        bars = view.closed("M15", self.p.atr_n + 1)
        a = atr(bars, self.p.atr_n)
        if not np.isfinite(a) or a <= 0:
            return None
        side = 1 if coin < 0.5 else -1
        ref = float(bars["close"].iloc[-1])
        return side, ref - side * self.p.stop_atr * a, ref + side * self.p.target_atr * a, self.p.max_hold_s


@dataclass(frozen=True)
class SmaCrossParams:
    fast: int = 20
    slow: int = 50
    atr_n: int = 14
    stop_atr: float = 2.0
    max_hold_s: int = 24 * 3600


class SmaCross(Strategy):
    """REF-SMACROSS: cruce de medias simples en M15 (regla trivial de seguimiento)."""

    name = "REF-SMACROSS-v1"
    signal_timeframe = "M15"

    def __init__(self, params: SmaCrossParams = SmaCrossParams()):
        self.p = params

    def decide(self, view: DataView):
        need = max(self.p.slow + 1, self.p.atr_n + 1)
        bars = view.closed("M15", need)
        if len(bars) < need:
            return None
        c = bars["close"].to_numpy(float)
        f_now, s_now = sma(c, self.p.fast), sma(c, self.p.slow)
        f_prev, s_prev = sma(c[:-1], self.p.fast), sma(c[:-1], self.p.slow)
        if not np.isfinite([f_now, s_now, f_prev, s_prev]).all():
            return None
        if f_prev <= s_prev and f_now > s_now:
            side = 1
        elif f_prev >= s_prev and f_now < s_now:
            side = -1
        else:
            return None
        a = atr(bars, self.p.atr_n)
        if not np.isfinite(a) or a <= 0:
            return None
        return side, c[-1] - side * self.p.stop_atr * a, None, self.p.max_hold_s
