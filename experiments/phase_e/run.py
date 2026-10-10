"""Fase E: evaluación pre-registrada (docs/PREREGISTRO_PHASE_E.md, commit 9761a90).

Ejecutar desde la raíz:
    .venv/Scripts/python experiments/phase_e/run.py            # evaluación principal
    .venv/Scripts/python experiments/phase_e/run.py --placebo  # 1000 semillas de REF-RANDOM

Los resultados se guardan en experiments/phase_e/ (no versionados) y se resumen en
docs/PHASE_E_RESULTS.md.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd

from aurum.backtesting.setup import build_backtester, load_validated
from aurum.config import PROJECT_ROOT, load_data_config
from aurum.data.storage import RawStore
from aurum.evaluation import metrics as M
from aurum.evaluation.placebo import RandomPlacebo
from aurum.evaluation.walkforward import PERIODS, SEGMENTS, aggregate, by_session, run_segment
from aurum.strategies.base import generate_signals
from aurum.strategies.registry import STRATEGIES, build
from aurum.validation.quality import apply_exclusions

OUT = Path(__file__).parent
SCENARIOS = ("base", "adverse", "stress")
CANDIDATES = ["CAND-ORB-NY-v1", "CAND-IMOM-NY-v1", "CAND-TREND-ATR-v1"]
COVID = [{"from": "2020-03-26T10:23", "to": "2020-03-26T10:24",
          "reason": "sensibilidad pre-registrada: cotización anómala del 2020-03-26 10:23"}]


def _clean(x):
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    return x


def make_bt(scenario, store):
    bt = build_backtester(scenario, store)
    bt.risk.daily_loss_fraction = None       # pre-registro, sección 4
    bt.risk.max_drawdown_fraction = None
    return bt


def load(cfg, store):
    return {tf: load_validated(store, cfg, tf) for tf in ("M1", "M15", "H1")}


def evaluate(frames, signals, store, scenarios=SCENARIOS, segments=SEGMENTS):
    out = {}
    for sc in scenarios:
        bt = make_bt(sc, store)
        for name, sigs in signals.items():
            res = {seg.label: run_segment(bt, frames["M1"], sigs, seg) for seg in segments}
            out[(sc, name)] = res
    return out


def summarize(results, initial):
    summary = {}
    for (sc, name), res in results.items():
        entry = {"periods": {}, "years": {}, "sessions": {}}
        for period, labels in PERIODS.items():
            entry["periods"][period] = aggregate(res, labels, initial, bootstrap=(sc == "base" or period == "oos"))
        for lab in res:
            entry["years"][lab] = aggregate(res, [lab], initial, bootstrap=False)
        for period in ("oos", "all"):
            tr = pd.concat([res[lab].trades for lab in PERIODS[period] if len(res[lab].trades)], ignore_index=True) \
                if any(len(res[lab].trades) for lab in PERIODS[period]) else pd.DataFrame()
            entry["sessions"][period] = by_session(tr)
        entry["stats"] = {k: int(sum(res[lab].stats.get(k, 0) for lab in res))
                          for k in ("same_bar_ambiguous", "same_bar_resolved_by_ticks", "same_bar_by_policy",
                                    "gap_exits", "rejected_signals")}
        summary.setdefault(name, {})[sc] = entry
    return summary


def main_eval():
    t0 = time.perf_counter()
    cfg = load_data_config()
    store = RawStore(PROJECT_ROOT / "data" / "raw", cfg["source"]["server"], cfg["symbol"]["name"])
    frames = load(cfg, store)
    signals, gen_s = {}, {}
    for name in STRATEGIES:
        t1 = time.perf_counter()
        signals[name] = generate_signals(build(name), frames)
        gen_s[name] = round(time.perf_counter() - t1, 1)
    print("señales:", {k: len(v) for k, v in signals.items()}, gen_s)
    initial = make_bt("base", store).risk.initial_balance
    results = evaluate(frames, signals, store)
    summary = summarize(results, initial)

    # DSR con N = 6 variantes, Sharpe diario de la prueba final (escenario base).
    trial = [summary[n]["base"]["periods"]["oos"]["daily_sharpe"] for n in STRATEGIES]
    trial = [0.0 if (t is None or not np.isfinite(t)) else t for t in trial]
    verdicts = {}
    for name in CANDIDATES:
        m = summary[name]["base"]["periods"]["oos"]
        dsr = M.deflated_sharpe(m["daily_sharpe"], m["days"], m["skew"], m["kurtosis"], trial)
        v, why = M.verdict(m, dsr)
        verdicts[name] = {"verdict": v, "reason": why, "dsr": dsr, "thresholds": M.evaluate_thresholds(m)}

    # Sensibilidad 2020-03-26: datos sin ese minuto (y sin las velas M15/H1 que lo contienen).
    covid_frames = {tf: apply_exclusions(df, COVID, duration={"M1": 60, "M15": 900, "H1": 3600}[tf])[0]
                    for tf, df in frames.items()}
    seg2020 = [s for s in SEGMENTS if s.label == "2020"]
    covid = {}
    for name in STRATEGIES:
        sigs = generate_signals(build(name), covid_frames)
        for label, fr, sg in (("con", frames, signals[name]), ("sin", covid_frames, sigs)):
            r = run_segment(make_bt("base", store), fr["M1"], sg, seg2020[0])
            m = aggregate({"2020": r}, ["2020"], initial, bootstrap=False)
            minute = int(pd.Timestamp("2020-03-26 10:23", tz="UTC").timestamp())
            open_then = bool(len(r.trades) and ((r.trades["entry_time"] <= minute)
                                                & (r.trades["exit_time"] >= minute)).any())
            covid.setdefault(name, {})[label] = {"net_usd": m["net_usd"], "pf": m["pf"], "max_dd_pct": m["max_dd_pct"],
                                                 "trades": m["trades"], "position_open_at_minute": open_then}

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    payload = {"code_commit": commit, "signals": {k: len(v) for k, v in signals.items()},
               "signal_generation_s": gen_s, "summary": summary, "verdicts": verdicts, "covid_2020": covid,
               "runtime_s": round(time.perf_counter() - t0, 1)}
    (OUT / "results.json").write_text(json.dumps(_clean(payload), indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(_clean({"verdicts": verdicts, "runtime_s": payload["runtime_s"]}), indent=1, ensure_ascii=False))


def main_placebo(n_seeds: int = 1000):
    t0 = time.perf_counter()
    cfg = load_data_config()
    store = RawStore(PROJECT_ROOT / "data" / "raw", cfg["source"]["server"], cfg["symbol"]["name"])
    frames = load(cfg, store)
    placebo = RandomPlacebo(frames["M15"])
    bt = make_bt("base", store)
    segs = [s for s in SEGMENTS if s.label in PERIODS["walk_forward"]]
    rows = []
    for seed in range(1, n_seeds + 1):
        sigs = placebo.signals(seed)
        res = {s.label: run_segment(bt, frames["M1"], sigs, s) for s in segs}
        row = {"seed": seed}
        for period in ("validation", "oos"):
            m = aggregate(res, PERIODS[period], bt.risk.initial_balance, bootstrap=False)
            for k in ("pf", "expectancy_r", "net_usd", "trades", "sharpe", "max_dd_pct"):
                row[f"{period}_{k}"] = m[k]
        rows.append(row)
        if seed % 100 == 0:
            print(seed, round(time.perf_counter() - t0, 1), flush=True)
    pd.DataFrame(rows).to_csv(OUT / "placebo.csv", index=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--placebo", action="store_true")
    args = ap.parse_args()
    main_placebo() if args.placebo else main_eval()
