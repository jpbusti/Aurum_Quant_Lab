"""Fase C: prueba de humo del motor con datos reales (2017-04 a 2026-10).

NO es una estrategia ni mide rentabilidad. Genera señales mecánicas (cada día a las 10:00
y a las 16:00 del servidor, alternando compra y venta, stop y objetivo a 5 USD, 0.01 lotes)
solo para comprobar sobre el historial completo que el motor:
- procesa 3,4 M barras M1 en un tiempo razonable,
- cuadra el libro de operaciones con la curva de equity,
- aplica costes coherentes en los tres escenarios,
- resuelve con ticks los casos de stop y objetivo en la misma barra cuando existen.

Ejecutar desde la raíz:  .venv/Scripts/python experiments/phase_c_engine_smoke/run.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from aurum.backtesting.engine import ledger_matches_equity
from aurum.backtesting.setup import build_backtester, load_validated_m1
from aurum.backtesting.types import Signal
from aurum.config import load_data_config
from aurum.data.storage import RawStore

OUT = Path(__file__).parent
DIST = 5.0


def mechanical_signals(m1) -> list[Signal]:
    t = m1["time_raw"].to_numpy(np.int64)
    tod = t % 86400
    idx = np.where(np.isin(tod, [10 * 3600, 16 * 3600]))[0]
    sigs = []
    for n, i in enumerate(idx):
        side = 1 if n % 2 == 0 else -1
        ref = float(m1["open"].iat[i])
        sigs.append(Signal(decision_time=int(t[i]), side=side, info_time=int(t[i]),
                           stop=ref - side * DIST, take_profit=ref + side * DIST, max_hold_s=4 * 3600))
    return sigs


def main() -> None:
    cfg = load_data_config()
    store = RawStore(Path("data/raw"), cfg["source"]["server"], cfg["symbol"]["name"])
    t0 = time.perf_counter()
    m1 = load_validated_m1(store, cfg)
    load_s = time.perf_counter() - t0
    signals = mechanical_signals(m1)
    summary = {"bars": int(len(m1)), "signals": len(signals), "load_seconds": round(load_s, 1), "scenarios": {}}
    for scenario in ("base", "adverse", "stress"):
        bt = build_backtester(scenario, store)
        bt.risk.sizing_mode, bt.risk.fixed_volume = "fixed", 0.01
        bt.risk.daily_loss_fraction = bt.risk.max_drawdown_fraction = None
        t1 = time.perf_counter()
        r = bt.run(m1, signals)
        tr = r.trades
        summary["scenarios"][scenario] = {
            "run_seconds": round(time.perf_counter() - t1, 1),
            "trades": int(len(tr)),
            "ledger_matches_equity": bool(ledger_matches_equity(r)),
            "spread_entry_points_mean": round(float(tr["spread_entry_points"].mean()), 2),
            "commission_usd_per_trade": round(float(tr["commission_usd"].mean()), 4),
            "swap_usd_total": round(float(tr["swap_usd"].sum()), 2),
            "exit_reasons": tr["exit_reason"].value_counts().to_dict(),
            "same_bar_ambiguous": r.stats["same_bar_ambiguous"],
            "same_bar_resolved_by_ticks": r.stats["same_bar_resolved_by_ticks"],
            "same_bar_by_policy": r.stats["same_bar_by_policy"],
            "gap_exits": r.stats["gap_exits"],
            "rejections": r.rejections["reason"].value_counts().to_dict() if len(r.rejections) else {},
        }
    (OUT / "results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
