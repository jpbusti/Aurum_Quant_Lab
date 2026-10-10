"""Validación histórica de la convención horaria Nueva York + 7 h (docs/TIMEZONE.md).

A. 10 lunes aleatorios (semilla 20261010) entre 2018 y 2026: primer precio del lunes y último del
   viernes de la misma semana (ticks si existen; si no, barras M1).
B. Primer viernes de cada mes: minuto de mayor rango entre las 13:00 y las 18:00 del servidor.

Ejecutar desde la raíz:  .venv/Scripts/python experiments/timezone_check/run.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from aurum.backtesting.setup import load_bars
from aurum.config import PROJECT_ROOT
from aurum.data.storage import RawStore
from aurum.timeutils import server_offset_hours

DAY = 86400


def main() -> None:
    st = RawStore(PROJECT_ROOT / "data" / "raw", "ICMarketsSC-Demo", "XAUUSD")
    m1 = load_bars(st, "M1")
    t = m1["time_raw"].to_numpy(np.int64)
    tick_days = {p.stem for p in st.ticks_dir().glob("*.parquet")}

    def edge(day: pd.Timestamp, last: bool):
        a = int(day.timestamp())
        if day.strftime("%Y-%m-%d") in tick_days:
            ms = pd.read_parquet(st.tick_path(day.date()), columns=["time_msc"])["time_msc"]
            return pd.to_datetime(int((ms.max() if last else ms.min()) // 1000), unit="s").strftime("%H:%M:%S"), "tick"
        sel = t[(t >= a) & (t < a + DAY)]
        if len(sel) == 0:
            return None, "sin datos"
        v = sel.max() + 59 if last else sel.min()
        return pd.to_datetime(int(v), unit="s").strftime("%H:%M:%S"), "barra M1"

    mondays = list(pd.date_range("2018-01-01", "2026-10-05", freq="W-MON"))
    pick = sorted(np.random.default_rng(20261010).choice(len(mondays), 10, replace=False))
    rows = []
    for i in pick:
        mon = mondays[i]
        fri = mon + pd.Timedelta(days=4)
        f, fs = edge(mon, False)
        lst, ls = edge(fri, True)
        rows.append((mon.date(), f, fs, fri.date(), lst, ls,
                     int(server_offset_hours(int(mon.timestamp()) + 12 * 3600)[0])))
    print(pd.DataFrame(rows, columns=["lunes", "primero", "fuente", "viernes", "ultimo", "fuente", "desfase"]).to_string(index=False))

    m1["ts"] = pd.to_datetime(m1["time_raw"], unit="s")
    m1["rng"] = m1["high"] - m1["low"]
    out = []
    for f in pd.date_range("2018-01-01", "2026-10-09", freq="WOM-1FRI"):
        d = m1[(m1["ts"] >= f + pd.Timedelta(hours=13)) & (m1["ts"] < f + pd.Timedelta(hours=18))]
        if len(d) < 200:
            continue
        top = d.loc[d["rng"].idxmax(), "ts"].strftime("%H:%M")
        out.append((f.date(), top, int(server_offset_hours(int(f.timestamp()) + 12 * 3600)[0])))
    r = pd.DataFrame(out, columns=["viernes", "minuto", "desfase"])
    near = r["minuto"].isin(["15:29", "15:30", "15:31", "15:32", "15:33"])
    print(r.assign(a_1530=r["minuto"] == "15:30", cerca=near).groupby("desfase")[["a_1530", "cerca"]].agg(["sum", "count"]))


if __name__ == "__main__":
    main()
