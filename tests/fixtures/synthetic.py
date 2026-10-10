"""Generadores de datos SINTÉTICOS para pruebas. No representan el mercado real.

Siguen el calendario observado del servidor (hora del servidor): sesión de lunes a
viernes de 01:00 a 23:58 (última barra M1), fin de semana hasta el lunes 01:00.
"""

from __future__ import annotations

import datetime as dt

import numpy as np

from fake_mt5 import RATES_DTYPE, TICKS_DTYPE

UTC = dt.timezone.utc
MONDAY = int(dt.datetime(2024, 1, 8, tzinfo=UTC).timestamp())  # lunes


def session_minutes(start_monday: int = MONDAY, weeks: int = 1) -> np.ndarray:
    times = []
    for w in range(weeks):
        for day in range(5):
            base = start_monday + (w * 7 + day) * 86400
            times.append(base + 60 * np.arange(60, 24 * 60 - 1))  # 01:00 .. 23:58
    return np.concatenate(times).astype(np.int64)


def make_rates(times: np.ndarray, seed: int = 0, start_price: float = 2000.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = len(times)
    close = np.round(start_price + np.cumsum(rng.normal(0, 0.3, n)), 2)
    open_ = np.round(np.r_[start_price, close[:-1]], 2)
    high = np.round(np.maximum(open_, close) + np.abs(rng.normal(0, 0.1, n)), 2)
    low = np.round(np.minimum(open_, close) - np.abs(rng.normal(0, 0.1, n)), 2)
    out = np.zeros(n, dtype=RATES_DTYPE)
    out["time"], out["open"], out["high"], out["low"], out["close"] = times, open_, high, low, close
    out["tick_volume"] = rng.integers(1, 100, n)
    out["spread"] = 5
    return out


def resample(rates: np.ndarray, tf_seconds: int) -> np.ndarray:
    bucket = rates["time"] - rates["time"] % tf_seconds
    keys, first = np.unique(bucket, return_index=True)
    last = np.r_[first[1:], len(rates)] - 1
    out = np.zeros(len(keys), dtype=RATES_DTYPE)
    out["time"] = keys
    out["open"] = rates["open"][first]
    out["close"] = rates["close"][last]
    out["high"] = np.maximum.reduceat(rates["high"], first)
    out["low"] = np.minimum.reduceat(rates["low"], first)
    out["tick_volume"] = np.add.reduceat(rates["tick_volume"], first)
    out["spread"] = 5
    return out


def ticks_for(rates: np.ndarray, spread: float = 0.05) -> np.ndarray:
    """Cuatro ticks por minuto que reproducen exactamente el OHLC bid de cada barra."""
    n = len(rates)
    out = np.zeros(4 * n, dtype=TICKS_DTYPE)
    for k, (field, off) in enumerate((("open", 0), ("high", 15), ("low", 30), ("close", 45))):
        sl = slice(k, None, 4)
        out["time"][sl] = rates["time"] + off
        out["time_msc"][sl] = (rates["time"] + off) * 1000
        out["bid"][sl] = rates[field]
        out["ask"][sl] = rates[field] + spread
    return out
