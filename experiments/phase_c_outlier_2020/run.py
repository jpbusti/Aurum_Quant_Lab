"""Fase C: impacto de la cotización anómala del 2020-03-26 10:23 (hora del servidor).

NO es una estrategia. Abre posiciones hipotéticas idénticas en los datos reales y en una
copia en memoria donde esa barra se sustituye por una interpolación de sus vecinas, y
compara el resultado. Los datos guardados no se modifican.

Ejecutar desde la raíz:  .venv/Scripts/python experiments/phase_c_outlier_2020/run.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aurum.backtesting.setup import build_backtester, load_validated_m1
from aurum.backtesting.types import Signal
from aurum.config import load_data_config
from aurum.data.storage import RawStore

OUT = Path(__file__).parent
OUTLIER = int(pd.Timestamp("2020-03-26 10:23", tz="UTC").timestamp())
DECISION = int(pd.Timestamp("2020-03-26 10:15", tz="UTC").timestamp())   # cierre de la vela M15 de las 10:00
DISTANCES = [5, 10, 20, 50, 100, 150]


def counterfactual(m1: pd.DataFrame) -> pd.DataFrame:
    cf = m1.copy()
    i = cf.index[cf["time_raw"] == OUTLIER][0]
    prev_close, next_open = cf.at[i - 1, "close"], cf.at[i + 1, "open"]
    cf.loc[i, ["open", "high", "low", "close"]] = [prev_close, max(prev_close, next_open),
                                                   min(prev_close, next_open), next_open]
    return cf


def main() -> None:
    cfg = load_data_config()
    store = RawStore(Path("data/raw"), cfg["source"]["server"], cfg["symbol"]["name"])
    m1 = load_validated_m1(store, cfg, DECISION - 3600, DECISION + 4 * 3600)
    entry_bar = m1[m1["time_raw"] >= DECISION].iloc[0]
    rows = []
    for scenario in ("base", "stress"):
        bt = build_backtester(scenario, store)
        bt.risk.sizing_mode, bt.risk.fixed_volume = "fixed", 0.01
        bt.risk.daily_loss_fraction = bt.risk.max_drawdown_fraction = None
        for side in (1, -1):
            for d in DISTANCES:
                ref = entry_bar["open"]
                stop = ref - d if side == 1 else ref + d
                tp = ref + d if side == 1 else ref - d
                s = Signal(decision_time=DECISION, side=side, stop=stop, take_profit=tp,
                           info_time=DECISION, max_hold_s=3 * 3600, tag=f"d{d}")
                for label, data in (("real", m1), ("sin_anomalia", counterfactual(m1))):
                    t = bt.run(data, [s]).trades.iloc[0]
                    rows.append({"scenario": scenario, "side": "largo" if side == 1 else "corto",
                                 "distance_usd": d, "data": label, "exit_reason": t.exit_reason,
                                 "exit_time": pd.to_datetime(t.exit_time, unit="s").strftime("%H:%M"),
                                 "exit_price": round(t.exit_price, 2), "net_usd": round(t.net_usd, 2)})
    df = pd.DataFrame(rows)
    wide = df.pivot_table(index=["scenario", "side", "distance_usd"], columns="data",
                          values=["exit_reason", "net_usd"], aggfunc="first")
    changed = df.pivot_table(index=["scenario", "side", "distance_usd"], columns="data",
                             values="net_usd", aggfunc="first")
    changed["diferencia_usd"] = changed["real"] - changed["sin_anomalia"]
    df.to_csv(OUT / "results.csv", index=False)
    (OUT / "results.json").write_text(json.dumps({
        "outlier_bar": m1[m1["time_raw"] == OUTLIER].iloc[0][["open", "high", "low", "close", "tick_volume",
                                                                "spread"]].to_dict(),
        "entry_bar_open": float(entry_bar["open"]),
        "volume_lots": 0.01,
    }, indent=2, default=float), encoding="utf-8")
    print(wide.to_string())
    print(changed.to_string())


if __name__ == "__main__":
    main()
