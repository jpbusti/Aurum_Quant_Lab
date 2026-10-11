"""Segmentos anuales con purga, agregados por periodo y desglose por sesión
(docs/PREREGISTRO_PHASE_E.md, secciones 2, 3 y 8)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from aurum.backtesting.engine import Backtester
from aurum.backtesting.types import Signal
from aurum.evaluation import metrics as M
from aurum.features.sessions import ny_minute_of_day


def _raw(text: str) -> int:
    return int(pd.Timestamp(text, tz="UTC").timestamp())


@dataclass(frozen=True)
class Segment:
    label: str
    start: int      # incluido (hora del servidor)
    end: int        # excluido


SEGMENTS = [Segment(str(y), _raw(f"{y}-01-01"), _raw(f"{y + 1}-01-01")) for y in range(2018, 2026)]
SEGMENTS = [Segment("2017", _raw("2017-04-06 01:00"), _raw("2018-01-01"))] + SEGMENTS + \
           [Segment("2026", _raw("2026-01-01"), _raw("2026-10-10"))]
PERIODS = {
    "in_sample": ["2017", "2018", "2019", "2020", "2021", "2022"],
    "validation": ["2023", "2024"],
    "oos": ["2025", "2026"],
    "walk_forward": ["2023", "2024", "2025", "2026"],
    "all": [s.label for s in SEGMENTS],
}
SESSIONS_NY = [("asia", 18 * 60, 3 * 60), ("londres", 3 * 60, 8 * 60), ("nueva_york", 8 * 60, 15 * 60),
               ("cierre", 15 * 60, 17 * 60)]


@dataclass
class SegmentResult:
    trades: pd.DataFrame
    daily: pd.Series
    span_days: float
    stats: dict
    rejections: pd.DataFrame | None = None


def run_segment(bt: Backtester, m1: pd.DataFrame, signals: Sequence[Signal], seg: Segment) -> SegmentResult:
    t = m1["time_raw"].to_numpy(np.int64)
    a, b = np.searchsorted(t, [seg.start, seg.end])
    bars = m1.iloc[a:b]
    # Purga: solo señales cuyo cierre por tiempo máximo cae dentro del segmento.
    sigs = [s for s in signals if seg.start <= s.decision_time and s.decision_time + (s.max_hold_s or 0) <= seg.end]
    r = bt.run(bars, sigs)
    daily = M.daily_equity(r.equity, bt.risk.initial_balance)
    span = (min(seg.end, int(t[b - 1]) + 60) - seg.start) / 86400
    return SegmentResult(r.trades, daily, span, r.stats, r.rejections)


def aggregate(results: dict[str, SegmentResult], labels: list[str], initial: float,
              bootstrap: bool = True) -> dict:
    """Encadena los retornos diarios de los segmentos y une sus operaciones."""
    rets, trades, span = [], [], 0.0
    for lab in labels:
        res = results[lab]
        eq = res.daily.to_numpy(float)
        rets.append(eq[1:] / eq[:-1] - 1)
        trades.append(res.trades)
        span += res.span_days
    r = np.concatenate(rets) if rets else np.array([])
    eq = pd.Series(initial * np.concatenate([[1.0], np.cumprod(1 + r)]))
    tr = pd.concat([x for x in trades if len(x)], ignore_index=True) if any(len(x) for x in trades) else pd.DataFrame(
        columns=["net_usd", "r_multiple", "commission_usd", "swap_usd", "entry_time"])
    return M.compute(tr, eq, span, bootstrap=bootstrap)


def session_of(entry_time: np.ndarray) -> np.ndarray:
    m = ny_minute_of_day(np.asarray(entry_time, dtype=np.int64))
    out = np.full(len(m), "otra", dtype=object)
    for name, a, b in SESSIONS_NY:
        out[((m >= a) & (m < b)) if a < b else ((m >= a) | (m < b))] = name
    return out


def by_session(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {}
    s = session_of(trades["entry_time"].to_numpy())
    out = {}
    for name in [x[0] for x in SESSIONS_NY] + ["otra"]:
        t = trades[s == name]
        if len(t):
            net = t["net_usd"].to_numpy(float)
            out[name] = {"trades": int(len(t)), "net_usd": float(net.sum()), "pf": M.profit_factor(net),
                         "expectancy_r": float(t["r_multiple"].mean())}
    return out
