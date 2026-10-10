"""Indicadores calculados solo con las barras que recibe (ya cerradas).

Las funciones devuelven el valor en la última barra recibida. No miran hacia
delante porque no reciben nada posterior: la estrategia les pasa lo que el
DataView le da en el instante de decisión.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(values: np.ndarray | pd.Series, n: int) -> float:
    """Media simple de los últimos n valores; NaN si hay menos de n."""
    v = np.asarray(values, dtype=float)
    return float(v[-n:].mean()) if len(v) >= n else float("nan")


def true_range(bars: pd.DataFrame) -> np.ndarray:
    """Rango verdadero de cada barra (la primera usa solo máximo - mínimo)."""
    h, lo, c = (bars[k].to_numpy(float) for k in ("high", "low", "close"))
    prev_c = np.r_[np.nan, c[:-1]]
    tr = np.maximum(h - lo, np.maximum(np.abs(h - prev_c), np.abs(lo - prev_c)))
    tr[0] = h[0] - lo[0] if len(tr) else np.nan
    return tr


def atr(bars: pd.DataFrame, n: int) -> float:
    """ATR como media simple de los últimos n rangos verdaderos (necesita n + 1 barras)."""
    if len(bars) < n + 1:
        return float("nan")
    return float(true_range(bars)[-n:].mean())
