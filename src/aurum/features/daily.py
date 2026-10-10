"""Velas diarias del oro construidas con velas H1 cerradas.

El día de negociación es el día del servidor: con la convención Nueva York + 7 h,
la medianoche del servidor son las 17:00 de Nueva York, el cierre diario del oro.
Un día está COMPLETO cuando ya ha empezado el siguiente día del servidor; antes de
eso sus valores podrían cambiar y no se usan.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DAY = 86400


def complete_days(h1_closed: pd.DataFrame, decision_time: int) -> pd.DataFrame:
    """OHLC por día del servidor, solo de días terminados antes de `decision_time`."""
    if h1_closed.empty:
        return pd.DataFrame(columns=["day", "open", "high", "low", "close", "bars"])
    t = h1_closed["time_raw"].to_numpy(np.int64)
    day = t // DAY
    keep = day < int(decision_time) // DAY
    df = h1_closed[keep]
    if df.empty:
        return pd.DataFrame(columns=["day", "open", "high", "low", "close", "bars"])
    g = df.groupby(day[keep], sort=True)
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "bars": g.size()})
    out.index.name = "day"
    return out.reset_index()
