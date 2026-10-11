"""Auditoría post-fase E y límite de riesgo del 2 % (docs/PREREGISTRO_AUDIT_RISK.md, commit e7bf24b).

Capa 1: señales de las 9 variantes (independientes del capital).
Capa 2: ejecutabilidad señal a señal con balance X y riesgo f (sin efecto de posiciones abiertas).
Motor: ejecuciones reales con 0,5 % y 2 % sobre 10 000 USD, rechazos por motivo y métricas.

Ejecutar desde la raíz:  .venv/Scripts/python experiments/audit_risk/run.py
"""

from __future__ import annotations

import importlib.util
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from aurum.config import PROJECT_ROOT, load_data_config
from aurum.data.storage import RawStore
from aurum.evaluation.walkforward import PERIODS, SEGMENTS, aggregate, run_segment
from aurum.strategies.base import generate_signals
from aurum.strategies.registry import STRATEGIES, build

OUT = Path(__file__).parent
RISKS = {"0.5%": 0.005, "2%": 0.02}
BALANCES = [200, 1_000, 10_000, 50_000]
OOS_START = int(pd.Timestamp("2025-01-01", tz="UTC").timestamp())
OOS_END = int(pd.Timestamp("2026-10-10", tz="UTC").timestamp())

_spec = importlib.util.spec_from_file_location("phase_e_run", PROJECT_ROOT / "experiments" / "phase_e" / "run.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)


def capital_layer(signals, m1, bt) -> pd.DataFrame:
    """Riesgo y margen de 0,01 lotes para cada señal, con la entrada estimada del motor (escenario base)."""
    t = m1["time_raw"].to_numpy(np.int64)
    o = m1["open"].to_numpy(float)
    spr_pts = bt.spread_model.spread_points(t, m1["spread"].to_numpy(float), bt.sc.spread_excess)
    point, slip = bt.ins.point, bt.sc.slippage_points * bt.ins.point
    rows = []
    for s in signals:
        j = int(np.searchsorted(t, s.decision_time))
        row = {"decision_time": s.decision_time, "side": s.side, "status": "ok"}
        if j >= len(t) or t[j] - s.decision_time > bt.ex.max_entry_delay_s:
            row["status"] = "sin precio"
            rows.append(row)
            continue
        spread = spr_pts[j] * point
        ask = o[j] + spread
        entry = ask + slip if s.side == 1 else o[j] - slip
        ref_close = o[j] if s.side == 1 else ask
        if (s.side == 1 and s.stop >= ref_close) or (s.side == -1 and s.stop <= ref_close):
            row["status"] = "stop inválido"
            rows.append(row)
            continue
        stop_fill = s.stop - s.side * slip
        vpp_minlot = bt.ins.value_per_price_unit(bt.ins.volume_min)
        row["stop_distance"] = abs(entry - stop_fill)
        row["risk_minlot_usd"] = abs(entry - stop_fill) * vpp_minlot + 2 * bt.sc.commission_side(bt.ins.volume_min)
        row["margin_minlot_usd"] = bt.ins.margin(bt.ins.volume_min, ask)
        rows.append(row)
    return pd.DataFrame(rows)


def executable(cap: pd.DataFrame, balance: float, f: float) -> pd.Series:
    ok = cap["status"] == "ok"
    return ok & (cap["risk_minlot_usd"] <= f * balance + 1e-9) & (cap["margin_minlot_usd"] <= balance)


def main():
    t0 = time.perf_counter()
    cfg = load_data_config()
    store = RawStore(PROJECT_ROOT / "data" / "raw", cfg["source"]["server"], cfg["symbol"]["name"])
    frames = E.load(cfg, store)
    m1 = frames["M1"]
    signals = {}
    for name in STRATEGIES:
        signals[name] = generate_signals(build(name), frames)
        print(name, len(signals[name]), round(time.perf_counter() - t0), flush=True)

    base_bt = E.make_bt("base", store)
    layers, cap_tables = {}, {}
    for name, sigs in signals.items():
        cap = capital_layer(sigs, m1, base_bt)
        cap_tables[name] = cap
        oos = (cap["decision_time"] >= OOS_START) & (cap["decision_time"] < OOS_END) if len(cap) else pd.Series(dtype=bool)
        entry = {"layer1_total": int(len(cap)), "layer1_oos": int(oos.sum()) if len(cap) else 0,
                 "status_counts": cap["status"].value_counts().to_dict() if len(cap) else {}}
        for label, f in RISKS.items():
            for bal in BALANCES:
                ex = executable(cap, bal, f) if len(cap) else pd.Series(dtype=bool)
                entry[f"exec_{label}_{bal}_total"] = int(ex.sum()) if len(cap) else 0
                entry[f"exec_{label}_{bal}_oos"] = int((ex & oos).sum()) if len(cap) else 0
        if len(cap) and (cap["status"] == "ok").any():
            ok = cap[cap["status"] == "ok"]
            ok_oos = ok[(ok["decision_time"] >= OOS_START)]
            for lab, df in (("total", ok), ("oos", ok_oos)):
                if len(df):
                    q = df["risk_minlot_usd"].quantile([0.1, 0.5, 0.9, 1.0]).round(2).tolist()
                    entry[f"risk_minlot_{lab}_p10_p50_p90_max"] = q
                    entry[f"margin_minlot_{lab}_max"] = round(float(df["margin_minlot_usd"].max()), 2)
        layers[name] = entry

    engine = {}
    for label, f in RISKS.items():
        bt = E.make_bt("base", store)
        bt.risk.risk_per_trade_fraction = f
        for name, sigs in signals.items():
            res = {seg.label: run_segment(bt, m1, sigs, seg) for seg in SEGMENTS}
            rej = Counter()
            for seg in res.values():
                if seg.rejections is not None and len(seg.rejections):
                    rej.update(seg.rejections["reason"].map(
                        lambda r: "volumen mínimo" if r.startswith("volumen mínimo") else r))
            periods = {p: aggregate(res, labs, bt.risk.initial_balance, bootstrap=(p == "oos"))
                       for p, labs in PERIODS.items()}
            oos_rej = Counter()
            for lab in PERIODS["oos"]:
                r = res[lab].rejections
                if r is not None and len(r):
                    oos_rej.update(r["reason"].map(lambda x: "volumen mínimo" if x.startswith("volumen mínimo") else x))
            engine.setdefault(name, {})[label] = {
                "trades_total": int(sum(len(x.trades) for x in res.values())),
                "trades_oos": int(sum(len(res[l].trades) for l in PERIODS["oos"])),
                "rejections_total": dict(rej), "rejections_oos": dict(oos_rej),
                "periods": {p: {k: periods[p][k] for k in ("trades", "net_usd", "pf", "pf_ci90_low", "max_dd_pct",
                                                          "sharpe", "sortino", "calmar", "expectancy_r", "sqn",
                                                          "recovery_factor", "ulcer_index")}
                            for p in ("in_sample", "validation", "oos", "all")},
            }
        print("motor", label, round(time.perf_counter() - t0), flush=True)

    payload = {"layers": layers, "engine": engine, "runtime_s": round(time.perf_counter() - t0, 1)}
    (OUT / "results.json").write_text(json.dumps(E._clean(payload), indent=1, ensure_ascii=False), encoding="utf-8")
    regime = cap_tables["CAND-REGIME-HMM-v1"]
    regime.to_csv(OUT / "regime_capital_layer.csv", index=False)
    print("listo", payload["runtime_s"])


if __name__ == "__main__":
    main()
