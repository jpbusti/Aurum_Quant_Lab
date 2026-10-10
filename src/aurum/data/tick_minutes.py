"""Resumen de ticks por minuto, procesado día a día.

Los 87 M ticks no se cargan juntos: cada archivo diario se lee con solo las
columnas time_msc, bid y ask, se resume y se descarta. El resultado (~190 000
filas) se guarda en data/processed/ con su procedencia.

Unidades: spread en puntos del símbolo (point = 0.01 USD en XAUUSD).
Horas: del servidor (time_raw), como en los datos crudos.

Spread ponderado por tiempo: cada cotización pesa el tiempo que estuvo vigente
hasta el siguiente tick, con un tope de MAX_QUOTE_LIFE_MS para que las pausas
del mercado no cuenten como tiempo de cotización.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aurum.data.storage import RawStore

MAX_QUOTE_LIFE_MS = 60_000
TICK_READ_COLUMNS = ["time_msc", "bid", "ask"]


def summarize_day(ticks: pd.DataFrame, point: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (resumen por minuto, histograma por hora del spread ponderado por tiempo)."""
    t = ticks["time_msc"].to_numpy(np.int64)
    bid = ticks["bid"].to_numpy()
    spread = np.rint((ticks["ask"].to_numpy() - bid) / point).astype(np.int64)
    life = np.minimum(np.diff(t, append=t[-1] + MAX_QUOTE_LIFE_MS), MAX_QUOTE_LIFE_MS).astype(np.float64)
    minute = (t // 1000) // 60 * 60
    df = pd.DataFrame({"time_raw": minute, "bid": bid, "spread": spread, "life": life,
                       "sxl": spread * life})
    g = df.groupby("time_raw", sort=True)
    out = pd.DataFrame({
        "ticks": g.size(),
        "bid_open": g["bid"].first(), "bid_high": g["bid"].max(),
        "bid_low": g["bid"].min(), "bid_close": g["bid"].last(),
        "spread_min": g["spread"].min(), "spread_max": g["spread"].max(),
        "spread_mean_tick": g["spread"].mean(),
        "spread_mean_time": g["sxl"].sum() / g["life"].sum(),
        "quoted_ms": g["life"].sum(),
    }).reset_index()
    hour = (minute % 86400) // 3600
    hist = (pd.DataFrame({"hour": hour, "spread": spread, "ms": life})
            .groupby(["hour", "spread"], sort=True)["ms"].agg(["sum", "size"])
            .rename(columns={"sum": "ms", "size": "ticks"}).reset_index())
    return out, hist


def build_tick_minutes(store: RawStore, point: float) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    minutes, hists, days, rows = [], [], [], 0
    for day in store.tick_days():
        ticks = pd.read_parquet(store.tick_path(day), columns=TICK_READ_COLUMNS)
        if ticks.empty:
            continue
        m, h = summarize_day(ticks, point)
        minutes.append(m)
        hists.append(h)
        days.append(day.isoformat())
        rows += len(ticks)
    by_minute = pd.concat(minutes, ignore_index=True)
    hist = pd.concat(hists).groupby(["hour", "spread"], as_index=False)[["ms", "ticks"]].sum()
    meta = {
        "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": store.ticks_manifest().source,
        "days": len(days), "first_day": days[0], "last_day": days[-1],
        "ticks": int(rows), "minutes": int(len(by_minute)),
        "point": point, "max_quote_life_ms": MAX_QUOTE_LIFE_MS,
        "time_convention": "hora del servidor",
        "spread_unit": "puntos (1 punto = point del símbolo)",
    }
    return by_minute, hist, meta


def save_tick_minutes(out_dir: str | Path, by_minute: pd.DataFrame, hist: pd.DataFrame, meta: dict[str, Any]) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_minute.to_parquet(out_dir / "tick_minutes.parquet", index=False)
    hist.to_parquet(out_dir / "spread_hist_by_hour.parquet", index=False)
    (out_dir / "tick_minutes.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_dir
