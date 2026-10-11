"""Familias de la fase F (docs/FAMILIES_RESEARCH.md y docs/PREREGISTRO_PHASE_F.md).

Cada familia tiene una lógica central y una rejilla de parámetros fijada antes de ver
resultados. Cada combinación de la rejilla es una prueba independiente, no un paso de
optimización.

Cada estrategia tiene dos implementaciones de la misma regla:
- decide(view): la de referencia, con el DataView que solo ve velas cerradas.
- vector_signals(frames): la rápida para el screening masivo. Calcula en el índice i
  solo con las velas 0..i, que son las cerradas en el instante de decisión
  (apertura de i + 900 s). tests/unit/test_families.py comprueba que ambas producen
  exactamente las mismas señales y que cambiar el futuro no altera el pasado.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from aurum.backtesting.types import Signal
from aurum.features.indicators import atr, true_range
from aurum.features.sessions import ny_minute_of_day
from aurum.strategies.base import DataView, Strategy
from aurum.strategies.references import SmaCross, SmaCrossParams

M15 = 900
H = 3600


def _rolling_mean(x: np.ndarray, n: int) -> np.ndarray:
    """Media de x[i-n+1..i] en cada i (NaN si no hay n valores), misma suma que x[-n:].mean()."""
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = sliding_window_view(x, n).mean(axis=1)
    return out


def _rolling_std(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = sliding_window_view(x, n).std(axis=1)
    return out


def _atr_series(m15: pd.DataFrame, n: int) -> np.ndarray:
    """ATR en cada i como media de los n rangos verdaderos que terminan en i (exige n + 1 velas)."""
    tr = true_range(m15)
    out = _rolling_mean(tr, n)
    out[:n] = np.nan
    return out


def _signals(m15: pd.DataFrame, idx: np.ndarray, side: np.ndarray, stop: np.ndarray, tp: np.ndarray | None,
             hold: int, tag: str) -> list[Signal]:
    t = m15["time_raw"].to_numpy(np.int64)
    out = []
    for k, i in enumerate(idx):
        dt = int(t[i]) + M15
        out.append(Signal(decision_time=dt, side=int(side[k]), stop=float(stop[k]),
                          take_profit=None if tp is None else float(tp[k]), max_hold_s=hold,
                          info_time=dt, tag=tag))
    return out


# --- Familia 1: tendencia (cruce de medias simples) --------------------------------------

class TrendSmaCross(SmaCross):
    """FAM-TREND: la regla de REF-SMACROSS con la rejilla de la familia."""

    def __init__(self, params: SmaCrossParams, name: str):
        super().__init__(params)
        self.name = name

    def vector_signals(self, frames: dict[str, pd.DataFrame]) -> list[Signal]:
        m15 = frames["M15"]
        p = self.p
        c = m15["close"].to_numpy(float)
        f, s = _rolling_mean(c, p.fast), _rolling_mean(c, p.slow)
        a = _atr_series(m15, p.atr_n)
        f_prev, s_prev = np.r_[np.nan, f[:-1]], np.r_[np.nan, s[:-1]]
        need = max(p.slow + 1, p.atr_n + 1)
        ok = (np.arange(len(c)) >= need - 1) & np.isfinite(f) & np.isfinite(s) & np.isfinite(f_prev) \
            & np.isfinite(s_prev) & np.isfinite(a) & (a > 0)
        up = ok & (f_prev <= s_prev) & (f > s)
        dn = ok & (f_prev >= s_prev) & (f < s)
        idx = np.flatnonzero(up | dn)
        side = np.where(up[idx], 1, -1)
        return _signals(m15, idx, side, c[idx] - side * p.stop_atr * a[idx], None, p.max_hold_s, self.name)


# --- Familia 2: reversión a la media (z-score del cierre) --------------------------------

@dataclass(frozen=True)
class ZRevParams:
    lookback: int = 50
    z_entry: float = 2.0
    stop_atr: float = 2.0
    max_hold_s: int = 4 * H
    atr_n: int = 14


class ZScoreReversion(Strategy):
    """FAM-MEANREV: entra contra el movimiento cuando el z-score del cierre cruza ±k;
    objetivo en la media, stop por ATR y cierre por tiempo."""

    signal_timeframe = "M15"

    def __init__(self, params: ZRevParams, name: str):
        self.p = params
        self.name = name

    def decide(self, view: DataView):
        p = self.p
        need = max(p.lookback + 1, p.atr_n + 1)
        bars = view.closed("M15", need)
        if len(bars) < need:
            return None
        c = bars["close"].to_numpy(float)
        w, w_prev = c[-p.lookback:], c[-p.lookback - 1:-1]
        mu, sd = w.mean(), w.std()
        mu_p, sd_p = w_prev.mean(), w_prev.std()
        if sd <= 0 or sd_p <= 0:
            return None
        z, z_prev = (c[-1] - mu) / sd, (c[-2] - mu_p) / sd_p
        if z_prev > -p.z_entry and z <= -p.z_entry:
            side = 1
        elif z_prev < p.z_entry and z >= p.z_entry:
            side = -1
        else:
            return None
        a = atr(bars, p.atr_n)
        if not np.isfinite(a) or a <= 0:
            return None
        return side, c[-1] - side * p.stop_atr * a, mu, p.max_hold_s

    def vector_signals(self, frames: dict[str, pd.DataFrame]) -> list[Signal]:
        m15 = frames["M15"]
        p = self.p
        c = m15["close"].to_numpy(float)
        mu, sd = _rolling_mean(c, p.lookback), _rolling_std(c, p.lookback)
        a = _atr_series(m15, p.atr_n)
        with np.errstate(divide="ignore", invalid="ignore"):
            z = (c - mu) / sd
        z_prev = np.r_[np.nan, z[:-1]]
        sd_prev = np.r_[np.nan, sd[:-1]]
        need = max(p.lookback + 1, p.atr_n + 1)
        ok = (np.arange(len(c)) >= need - 1) & (sd > 0) & (sd_prev > 0) & np.isfinite(a) & (a > 0)
        up = ok & (z_prev > -p.z_entry) & (z <= -p.z_entry)
        dn = ok & ~up & (z_prev < p.z_entry) & (z >= p.z_entry)
        idx = np.flatnonzero(up | dn)
        side = np.where(up[idx], 1, -1)
        return _signals(m15, idx, side, c[idx] - side * p.stop_atr * a[idx], mu[idx], p.max_hold_s, self.name)


# --- Familia 3: calendario (hora del día en Nueva York) -------------------------------

@dataclass(frozen=True)
class HourParams:
    ny_hour: int = 9                 # decisión al cierre de la vela M15 que termina a las HH:00 NY
    side: int = 1
    hold_h: int = 1
    stop_atr: float = 3.0
    atr_n: int = 14


class HourOfDay(Strategy):
    """FAM-CALENDAR: posición fija (compra o venta) a una hora de Nueva York durante h horas."""

    signal_timeframe = "M15"

    def __init__(self, params: HourParams, name: str):
        self.p = params
        self.name = name

    def decide(self, view: DataView):
        p = self.p
        if int(ny_minute_of_day(view.decision_time)) != p.ny_hour * 60:
            return None
        bars = view.closed("M15", p.atr_n + 1)
        a = atr(bars, p.atr_n)
        if not np.isfinite(a) or a <= 0:
            return None
        c = float(bars["close"].iloc[-1])
        return p.side, c - p.side * p.stop_atr * a, None, p.hold_h * H

    def vector_signals(self, frames: dict[str, pd.DataFrame]) -> list[Signal]:
        m15 = frames["M15"]
        p = self.p
        t = m15["time_raw"].to_numpy(np.int64)
        c = m15["close"].to_numpy(float)
        a = _atr_series(m15, p.atr_n)
        ok = (ny_minute_of_day(t + M15) == p.ny_hour * 60) & np.isfinite(a) & (a > 0)
        idx = np.flatnonzero(ok)
        side = np.full(len(idx), p.side)
        return _signals(m15, idx, side, c[idx] - side * p.stop_atr * a[idx], None, p.hold_h * H, self.name)


# --- Rejillas pre-registradas -------------------------------------------------------------
# Calendario: sin las 17:00 NY (la vela que cierra entonces no tiene apertura posterior en
# 120 s: el mercado para de 17:00 a 18:00) ni las 18:00 NY (no hay vela que cierre a esa hora).

def trend_grid() -> list[TrendSmaCross]:
    out = []
    for fast, slow, k, hold in product((5, 10, 20, 40), (50, 100, 200), (1.5, 3.0), (8, 24, 72)):
        name = f"FAM-TREND-f{fast}-s{slow}-k{k}-h{hold}"
        out.append(TrendSmaCross(SmaCrossParams(fast=fast, slow=slow, atr_n=14, stop_atr=k, max_hold_s=hold * H), name))
    return out


def meanrev_grid() -> list[ZScoreReversion]:
    out = []
    for lb, z, k, hold in product((20, 50, 100, 200), (1.5, 2.0, 2.5, 3.0), (2.0, 4.0), (4, 24)):
        name = f"FAM-MEANREV-l{lb}-z{z}-k{k}-h{hold}"
        out.append(ZScoreReversion(ZRevParams(lookback=lb, z_entry=z, stop_atr=k, max_hold_s=hold * H), name))
    return out


def calendar_grid() -> list[HourOfDay]:
    out = []
    for hour, side, hold in product([h for h in range(24) if h not in (17, 18)], (1, -1), (1, 4)):
        name = f"FAM-CALENDAR-h{hour:02d}-{'L' if side == 1 else 'S'}-d{hold}"
        out.append(HourOfDay(HourParams(ny_hour=hour, side=side, hold_h=hold), name))
    return out


FAMILIES = {"TREND": trend_grid, "MEANREV": meanrev_grid, "CALENDAR": calendar_grid}


def all_variants() -> dict[str, list[Strategy]]:
    return {fam: grid() for fam, grid in FAMILIES.items()}


def variant_params(strategy: Strategy) -> dict:
    return asdict(strategy.p)
