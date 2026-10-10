"""Señales de REF-RANDOM-v1 vectorizadas para muchas semillas (placebo de la fase E).

Produce exactamente las mismas señales que RandomEntry.decide (lo comprueba
tests/unit/test_evaluation.py), pero sin recorrer las velas una a una.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from aurum.backtesting.types import Signal
from aurum.features.indicators import true_range
from aurum.features.sessions import hhmm, ny_minute_of_day
from aurum.strategies.references import RandomParams, splitmix_uniform

M15 = 900


class RandomPlacebo:
    """Precalcula lo que no depende de la semilla (ventana, ATR causal, cierres)."""

    def __init__(self, m15: pd.DataFrame, params: RandomParams = RandomParams()):
        self.p = params
        times = m15["time_raw"].to_numpy(np.int64)
        decision = times + M15                       # cada vela decide al cerrar
        n = params.atr_n
        tr = true_range(m15)
        atr = pd.Series(tr).rolling(n).mean().to_numpy()
        # Igual que RandomEntry: necesita n + 1 velas cerradas (la primera solo da h - l).
        atr[: n] = np.nan
        minute = ny_minute_of_day(decision)
        (h1, m1), (h2, m2) = hhmm(params.ny_start), hhmm(params.ny_end)
        ok = (minute >= h1 * 60 + m1) & (minute < h2 * 60 + m2) & np.isfinite(atr) & (atr > 0)
        self.decision = decision[ok]
        self.atr = atr[ok]
        self.close = m15["close"].to_numpy(float)[ok]

    def signals(self, seed: int) -> list[Signal]:
        u = splitmix_uniform(seed, self.decision, 0)
        coin = splitmix_uniform(seed, self.decision, 1)
        take = u < self.p.probability
        side = np.where(coin[take] < 0.5, 1, -1)
        t = self.decision[take]
        c = self.close[take]
        a = self.atr[take]
        stop = c - side * self.p.stop_atr * a
        tp = c + side * self.p.target_atr * a
        tag = f"REF-RANDOM-seed{seed}"
        return [Signal(decision_time=int(ti), side=int(si), stop=float(st), take_profit=float(tpi),
                       info_time=int(ti), max_hold_s=self.p.max_hold_s, tag=tag)
                for ti, si, st, tpi in zip(t, side, stop, tp)]
