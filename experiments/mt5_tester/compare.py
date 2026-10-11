"""Compara CAND-ORB-NY-v1 en nuestro motor con el Strategy Tester de MT5 (AurumOrbCheck.ex5).

Mismas reglas, 0,01 lotes fijos, 2026-04-01 a 2026-10-09. En el motor: escenario base sin
slippage (el tester con ticks reales no aplica slippage), para aislar diferencias de lógica.

1. Ejecutar el tester con experiments/mt5_tester/tester.ini (deja aurum_orb_check.csv en la
   carpeta Common\\Files de MetaQuotes).
2. .venv/Scripts/python experiments/mt5_tester/compare.py
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import numpy as np
import pandas as pd

from aurum.config import PROJECT_ROOT, load_data_config
from aurum.data.storage import RawStore
from aurum.strategies.base import generate_signals
from aurum.strategies.registry import build

OUT = Path(__file__).parent
TESTER_CSV = Path(os.environ["APPDATA"]) / "MetaQuotes" / "Terminal" / "Common" / "Files" / "aurum_orb_check.csv"
START, END = "2026-04-01", "2026-10-10"

_spec = importlib.util.spec_from_file_location("phase_e_run", PROJECT_ROOT / "experiments" / "phase_e" / "run.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)


def ours() -> pd.DataFrame:
    cfg = load_data_config()
    store = RawStore(PROJECT_ROOT / "data" / "raw", cfg["source"]["server"], cfg["symbol"]["name"])
    frames = E.load(cfg, store)
    a, b = (int(pd.Timestamp(x, tz="UTC").timestamp()) for x in (START, END))
    sigs = [s for s in generate_signals(build("CAND-ORB-NY-v1"), frames) if a <= s.decision_time < b]
    bt = E.make_bt("base", store)
    bt.sc.slippage_points = 0
    bt.risk.sizing_mode, bt.risk.fixed_volume = "fixed", 0.01
    m1 = frames["M1"]
    t = m1["time_raw"].to_numpy(np.int64)
    i, j = np.searchsorted(t, [a, b])
    r = bt.run(m1.iloc[i:j], sigs)
    tr = r.trades.copy()
    tr["day"] = pd.to_datetime(tr["entry_time"], unit="s").dt.date
    return tr


def tester() -> pd.DataFrame:
    df = pd.read_csv(TESTER_CSV)
    df["ts"] = pd.to_datetime(df["server_time"], format="%Y.%m.%d %H:%M:%S")
    ins = df[df["event"] == "in"].reset_index(drop=True)
    outs = df[df["event"] == "out"].reset_index(drop=True)
    n = min(len(ins), len(outs))
    tr = pd.DataFrame({
        "day": ins["ts"].dt.date[:n], "side_t": ins["side"][:n], "entry_t": ins["price"][:n],
        "sl_t": ins["sl"][:n], "tp_t": ins["tp"][:n], "entry_time_t": ins["ts"][:n],
        "exit_time_t": outs["ts"][:n], "exit_t": outs["price"][:n], "reason_t": outs["reason"][:n],
        "profit_t": outs["profit"][:n], "commission_t": ins["commission"][:n].values + outs["commission"][:n].values,
    })
    return tr


def main() -> None:
    a, b = ours(), tester()
    m = a.merge(b, on="day", how="outer", indicator=True)
    both = m[m["_merge"] == "both"].copy()
    both["same_side"] = both["side"] == both["side_t"]
    both["d_entry"] = both["entry_price"] - both["entry_t"]
    both["d_exit"] = both["exit_price"] - both["exit_t"]
    both["gross_t"] = both["profit_t"]
    both["d_gross"] = both["gross_usd"] - both["gross_t"]
    reason_map = {"stop": "sl", "stop (hueco)": "sl", "objetivo": "tp", "objetivo (hueco)": "tp",
                  "tiempo": "otro", "fin de datos": "otro"}
    both["same_reason"] = both["exit_reason"].map(reason_map) == both["reason_t"]
    summary = {
        "dias_motor": int(len(a)), "dias_tester": int(len(b)),
        "solo_motor": int((m["_merge"] == "left_only").sum()), "solo_tester": int((m["_merge"] == "right_only").sum()),
        "coinciden_dia": int(len(both)), "mismo_lado": int(both["same_side"].sum()),
        "mismo_motivo_salida": int(both["same_reason"].sum()),
        "dif_entrada_media": round(float(both["d_entry"].abs().mean()), 3),
        "dif_entrada_p95": round(float(both["d_entry"].abs().quantile(0.95)), 3),
        "dif_salida_media": round(float(both["d_exit"].abs().mean()), 3),
        "pnl_bruto_motor": round(float(both["gross_usd"].sum()), 2),
        "pnl_bruto_tester": round(float(both["gross_t"].sum()), 2),
        "comision_tester": round(float(both["commission_t"].sum()), 2),
    }
    both.to_csv(OUT / "comparison.csv", index=False)
    m[m["_merge"] != "both"].to_csv(OUT / "unmatched.csv", index=False)
    for k, v in summary.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
