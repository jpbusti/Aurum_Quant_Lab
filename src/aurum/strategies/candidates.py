"""Estrategias candidatas transparentes (fase D). Fichas completas en docs/STRATEGY_RESEARCH.md.

Son HIPÓTESIS, no estrategias con ventaja demostrada. Cada una es una variante propia
inspirada en una fuente publicada; los resultados de la fuente no se atribuyen a estas
variantes. Parámetros fijados a priori, sin optimizar.

Horas en hora de Nueva York (servidor - 7 h, docs/TIMEZONE.md).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aurum.features.indicators import atr, sma
from aurum.features.sessions import hhmm, ny_day, ny_minute_of_day
from aurum.strategies.base import DataView, Strategy

M15 = 900


def _minute(text: str) -> int:
    h, m = hhmm(text)
    return h * 60 + m


@dataclass(frozen=True)
class OrbParams:
    range_start_ny: str = "09:30"     # apertura del mercado de acciones de EE. UU.
    range_minutes: int = 15           # una vela M15
    session_close_ny: str = "16:00"   # cierre por tiempo
    target_r: float = 10.0            # objetivo = 10 veces el riesgo inicial (regla de la fuente)


class OpeningRangeBreakoutNY(Strategy):
    """CAND-ORB-NY: dirección de la primera vela M15 tras las 09:30 de Nueva York.

    Al cierre de esa vela (09:45 NY): compra si cerró por encima de su apertura y vende si
    cerró por debajo; sin operación si cerró igual. Stop en el extremo opuesto de la vela,
    objetivo a 10R y cierre a las 16:00 NY.
    """

    name = "CAND-ORB-NY-v1"
    signal_timeframe = "M15"

    def __init__(self, params: OrbParams = OrbParams()):
        self.p = params

    def decide(self, view: DataView):
        t = view.decision_time
        start = _minute(self.p.range_start_ny)
        if int(ny_minute_of_day(t)) != start + self.p.range_minutes:
            return None
        bar = view.closed("M15", 1)
        if bar.empty:
            return None
        b = bar.iloc[-1]
        if int(b["time_raw"]) != t - M15:          # la vela del rango debe existir (sin hueco)
            return None
        o, h, lo, c = float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])
        if c > o:
            side, stop = 1, lo
        elif c < o:
            side, stop = -1, h
        else:
            return None
        risk = abs(c - stop)
        if risk <= 0:
            return None
        max_hold = (_minute(self.p.session_close_ny) - (start + self.p.range_minutes)) * 60
        return side, stop, c + side * self.p.target_r * risk, max_hold


@dataclass(frozen=True)
class IntradayMomentumParams:
    first_window_end_ny: str = "10:00"    # fin de la primera media hora de la sesión de acciones
    prev_close_ny: str = "16:00"          # cierre de referencia del día anterior
    last_window_start_ny: str = "15:30"   # última media hora
    last_window_minutes: int = 30
    atr_n: int = 14
    stop_atr: float = 3.0                 # stop de protección (añadido; la fuente no usa stop)


class IntradayMomentumNY(Strategy):
    """CAND-IMOM-NY: el retorno desde el cierre de las 16:00 NY del día anterior hasta las
    10:00 NY de hoy decide la dirección de la operación de 15:30 a 16:00 NY."""

    name = "CAND-IMOM-NY-v1"
    signal_timeframe = "M15"

    def __init__(self, params: IntradayMomentumParams = IntradayMomentumParams()):
        self.p = params

    def decide(self, view: DataView):
        t = view.decision_time
        if int(ny_minute_of_day(t)) != _minute(self.p.last_window_start_ny):
            return None
        bars = view.closed("M15", 400)               # cubre fin de semana y festivos cortos
        if len(bars) < self.p.atr_n + 1:
            return None
        times = bars["time_raw"].to_numpy(np.int64)
        closes_at = times + M15                       # instante en que cada vela cierra
        today = int(ny_day(t))
        day = ny_day(closes_at)
        minute = ny_minute_of_day(closes_at)
        first = np.where((day == today) & (minute == _minute(self.p.first_window_end_ny)))[0]
        prev = np.where((day < today) & (minute == _minute(self.p.prev_close_ny)))[0]
        if len(first) == 0 or len(prev) == 0:
            return None
        if today - int(day[prev[-1]]) > 4:            # referencia demasiado antigua: no operar
            return None
        c = bars["close"].to_numpy(float)
        r1 = np.log(c[first[-1]] / c[prev[-1]])
        if r1 == 0 or not np.isfinite(r1):
            return None
        a = atr(bars, self.p.atr_n)
        if not np.isfinite(a) or a <= 0:
            return None
        side = 1 if r1 > 0 else -1
        return side, c[-1] - side * self.p.stop_atr * a, None, self.p.last_window_minutes * 60


@dataclass(frozen=True)
class AtrTrendParams:
    donchian_n: int = 20          # ruptura del máximo o mínimo de las 20 velas M15 anteriores
    h1_sma: int = 50              # filtro de tendencia en H1 (solo velas H1 cerradas)
    atr_n: int = 14
    stop_atr: float = 2.0
    target_atr: float = 4.0
    max_hold_s: int = 24 * 3600
    ny_start: str = "03:00"       # ventana de entradas (evita la pausa diaria y la hora previa)
    ny_end: str = "15:00"


class AtrTrendBreakout(Strategy):
    """CAND-TREND-ATR: ruptura de canal M15 a favor de la tendencia H1, con stop y objetivo en ATR."""

    name = "CAND-TREND-ATR-v1"
    signal_timeframe = "M15"

    def __init__(self, params: AtrTrendParams = AtrTrendParams()):
        self.p = params

    def decide(self, view: DataView):
        t = view.decision_time
        m = int(ny_minute_of_day(t))
        if not (_minute(self.p.ny_start) <= m < _minute(self.p.ny_end)):
            return None
        need = max(self.p.donchian_n + 1, self.p.atr_n + 1)
        bars = view.closed("M15", need)
        h1 = view.closed("H1", self.p.h1_sma)
        if len(bars) < need or len(h1) < self.p.h1_sma:
            return None
        hi = bars["high"].to_numpy(float)[:-1]
        lo = bars["low"].to_numpy(float)[:-1]
        c = float(bars["close"].iloc[-1])
        h1_close = float(h1["close"].iloc[-1])
        h1_avg = sma(h1["close"].to_numpy(float), self.p.h1_sma)
        a = atr(bars, self.p.atr_n)
        if not np.isfinite([h1_avg, a]).all() or a <= 0:
            return None
        if c > hi[-self.p.donchian_n:].max() and h1_close > h1_avg:
            side = 1
        elif c < lo[-self.p.donchian_n:].min() and h1_close < h1_avg:
            side = -1
        else:
            return None
        return side, c - side * self.p.stop_atr * a, c + side * self.p.target_atr * a, self.p.max_hold_s
