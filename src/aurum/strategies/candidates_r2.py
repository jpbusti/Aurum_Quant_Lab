"""Candidatas de la ronda 2 (docs/PREREGISTRO_RONDA2.md y fichas en docs/STRATEGY_RESEARCH.md).

Hipótesis nuevas, variantes propias, parámetros fijados a priori y sin optimizar.
Horas en hora de Nueva York (servidor − 7 h). Día de negociación = día del servidor.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aurum.features.daily import DAY, complete_days
from aurum.features.indicators import atr
from aurum.features.regime import HMM2, filter_probs, fit_hmm
from aurum.features.sessions import hhmm, ny_minute_of_day
from aurum.strategies.base import DataView, Strategy

M15 = 900


def _minute(text: str) -> int:
    h, m = hhmm(text)
    return h * 60 + m


def _hold_until_ny(decision_time: int, ny_exit: str) -> int:
    """Segundos desde la decisión hasta la hora de salida en Nueva York del mismo día NY."""
    return (_minute(ny_exit) - int(ny_minute_of_day(decision_time))) * 60


# --- Expansión de volatilidad tras compresión (NR7) ------------------------------------

@dataclass(frozen=True)
class Nr7Params:
    lookback_days: int = 7          # día de rango más estrecho de los últimos 7
    entry_start_ny: str = "03:00"
    entry_end_ny: str = "12:00"
    exit_ny: str = "15:45"          # antes de la hora de mayor spread (16:00-17:00 NY)


class Nr7Breakout(Strategy):
    """CAND-VOLX-NR7: si el día anterior fue NR7, opera la primera ruptura de su rango."""

    name = "CAND-VOLX-NR7-v1"
    signal_timeframe = "M15"

    def __init__(self, params: Nr7Params = Nr7Params()):
        self.p = params

    def decide(self, view: DataView):
        t = view.decision_time
        m = int(ny_minute_of_day(t))
        if not (_minute(self.p.entry_start_ny) <= m < _minute(self.p.entry_end_ny)):
            return None
        days = complete_days(view.closed("H1", 24 * (self.p.lookback_days + 6)), t)
        if len(days) < self.p.lookback_days:
            return None
        last = days.iloc[-1]                         # último día completo (el viernes tras un fin de semana)
        rng = (days["high"] - days["low"]).to_numpy(float)[-self.p.lookback_days:]
        if not (rng[-1] < rng[:-1].min()):
            return None
        hi, lo = float(last["high"]), float(last["low"])
        today = view.closed("M15", 120)
        today = today[today["time_raw"].to_numpy(np.int64) // DAY == t // DAY]
        if today.empty:
            return None
        closes = today["close"].to_numpy(float)
        prior_break = (closes[:-1] > hi).any() or (closes[:-1] < lo).any()
        if prior_break:
            return None                                 # solo la primera ruptura del día
        c = closes[-1]
        if c > hi:
            side, stop = 1, lo
        elif c < lo:
            side, stop = -1, hi
        else:
            return None
        hold = _hold_until_ny(t, self.p.exit_ny)
        return (side, stop, None, hold) if hold > 0 else None


# --- Régimen de volatilidad con HMM y momentum de series temporales ------------------------

@dataclass(frozen=True)
class RegimeParams:
    min_train_days: int = 250        # días completos mínimos para ajustar el HMM
    calm_prob_max: float = 0.5       # opera solo si P(estado de alta volatilidad) < 0,5
    momentum_days: int = 20          # signo del retorno de 20 días
    atr_days: int = 14
    stop_atr: float = 2.0            # stop a 2 ATR diarios
    decision_ny: str = "03:00"       # una decisión al día
    exit_ny: str = "15:45"


class RegimeMomentum(Strategy):
    """CAND-REGIME-HMM: momentum de 20 días solo cuando el HMM indica régimen tranquilo.

    El HMM se ajusta una vez por año natural con los retornos diarios de los días completos
    anteriores al 1 de enero (hora del servidor) y se aplica con el filtro hacia delante.
    """

    name = "CAND-REGIME-HMM-v1"
    signal_timeframe = "M15"

    def __init__(self, params: RegimeParams = RegimeParams()):
        self.p = params
        self._models: dict[int, HMM2 | None] = {}

    def _model_for_year(self, view: DataView, year_start_day: int) -> HMM2 | None:
        if year_start_day not in self._models:
            h1 = view.closed("H1")
            days = complete_days(h1, year_start_day * DAY)       # solo días anteriores al 1 de enero
            r = np.diff(np.log(days["close"].to_numpy(float)))
            self._models[year_start_day] = fit_hmm(r) if len(r) >= self.p.min_train_days else None
        return self._models[year_start_day]

    def decide(self, view: DataView):
        t = view.decision_time
        if int(ny_minute_of_day(t)) != _minute(self.p.decision_ny):
            return None
        today = t // DAY
        year = int(np.datetime64(int(today), "D").astype("datetime64[Y]").astype(int)) + 1970
        year_start_day = int((np.datetime64(f"{year}-01-01") - np.datetime64("1970-01-01")).astype(int))
        model = self._model_for_year(view, year_start_day)
        if model is None:
            return None
        days = complete_days(view.closed("H1", 24 * 400), t)
        closes = days["close"].to_numpy(float)
        if len(closes) < max(self.p.momentum_days, self.p.atr_days) + 2:
            return None
        this_year = days["day"].to_numpy(np.int64) >= year_start_day
        r = np.diff(np.log(closes))
        r_year = r[this_year[1:]]
        probs = filter_probs(model, r_year)
        p_high = float(probs[-1, model.high_vol_state]) if len(probs) else float(model.start[model.high_vol_state])
        if p_high >= self.p.calm_prob_max:
            return None
        mom = np.log(closes[-1] / closes[-1 - self.p.momentum_days])
        if mom == 0 or not np.isfinite(mom):
            return None
        a = atr(days[["high", "low", "close"]], self.p.atr_days)
        if not np.isfinite(a) or a <= 0:
            return None
        side = 1 if mom > 0 else -1
        ref = float(view.closed("M15", 1)["close"].iloc[-1])
        return side, ref - side * self.p.stop_atr * a, None, _hold_until_ny(t, self.p.exit_ny)


# --- Reversión a VWAP de sesión con tick_volume -----------------------------------------------

@dataclass(frozen=True)
class VwapParams:
    z_entry: float = 2.0             # distancia al VWAP en ATR para entrar
    stop_atr: float = 1.5            # stop más allá del precio de entrada
    atr_n: int = 14
    min_bars: int = 8                # velas M15 del día antes de usar el VWAP
    entry_start_ny: str = "08:00"
    entry_end_ny: str = "14:00"
    exit_ny: str = "15:45"


class VwapReversion(Strategy):
    """CAND-VWAP-MR: vuelve al VWAP del día cuando el precio se aleja más de 2 ATR.

    VWAP del día del servidor con precio típico (H+L+C)/3 de velas M15 cerradas ponderado por
    tick_volume (número de ticks, NO volumen negociado: es un sustituto, ver la ficha).
    """

    name = "CAND-VWAP-MR-v1"
    signal_timeframe = "M15"

    def __init__(self, params: VwapParams = VwapParams()):
        self.p = params

    def decide(self, view: DataView):
        t = view.decision_time
        m = int(ny_minute_of_day(t))
        if not (_minute(self.p.entry_start_ny) <= m < _minute(self.p.entry_end_ny)):
            return None
        bars = view.closed("M15", 120)
        today = bars[bars["time_raw"].to_numpy(np.int64) // DAY == t // DAY]
        if len(today) < self.p.min_bars or len(bars) < self.p.atr_n + 1:
            return None
        w = today["tick_volume"].to_numpy(float)
        if w.sum() <= 0:
            return None
        typical = (today["high"] + today["low"] + today["close"]).to_numpy(float) / 3
        vwap = float((typical * w).sum() / w.sum())
        a = atr(bars, self.p.atr_n)
        if not np.isfinite(a) or a <= 0:
            return None
        c = float(bars["close"].iloc[-1])
        z = (c - vwap) / a
        if z > self.p.z_entry:
            side = -1
        elif z < -self.p.z_entry:
            side = 1
        else:
            return None
        hold = _hold_until_ny(t, self.p.exit_ny)
        return side, c - side * self.p.stop_atr * a, vwap, hold
