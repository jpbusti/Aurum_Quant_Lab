"""Ronda 2: filtro de backtest pre-registrado (docs/PREREGISTRO_RONDA2.md, commit 53b2818).

Reutiliza sin cambios el protocolo de la fase E (experiments/phase_e/run.py) y su placebo de
1000 semillas (experiments/phase_e/placebo.csv). DSR con N = 9: las 6 variantes de la fase E
más las 3 de esta ronda.

Ejecutar desde la raíz:  .venv/Scripts/python experiments/ronda2/run.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd

from aurum.config import PROJECT_ROOT, load_data_config
from aurum.data.storage import RawStore
from aurum.evaluation import metrics as M
from aurum.evaluation.walkforward import SEGMENTS, aggregate, run_segment
from aurum.strategies.base import generate_signals
from aurum.strategies.registry import build
from aurum.validation.quality import apply_exclusions

OUT = Path(__file__).parent
PHASE_E = PROJECT_ROOT / "experiments" / "phase_e"
CANDIDATES = ["CAND-VOLX-NR7-v1", "CAND-REGIME-HMM-v1", "CAND-VWAP-MR-v1"]

_spec = importlib.util.spec_from_file_location("phase_e_run", PHASE_E / "run.py")
E = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(E)


def main():
    t0 = time.perf_counter()
    cfg = load_data_config()
    store = RawStore(PROJECT_ROOT / "data" / "raw", cfg["source"]["server"], cfg["symbol"]["name"])
    frames = E.load(cfg, store)
    signals, gen_s = {}, {}
    for name in CANDIDATES:
        t1 = time.perf_counter()
        signals[name] = generate_signals(build(name), frames)
        gen_s[name] = round(time.perf_counter() - t1, 1)
    print("señales:", {k: len(v) for k, v in signals.items()}, gen_s, flush=True)
    initial = E.make_bt("base", store).risk.initial_balance
    summary = E.summarize(E.evaluate(frames, signals, store), initial)

    # DSR con N = 9: Sharpe diario de la prueba final de todas las variantes probadas.
    phase_e = json.loads((PHASE_E / "results.json").read_text(encoding="utf-8"))["summary"]
    trial = {n: phase_e[n]["base"]["periods"]["oos"]["daily_sharpe"] for n in phase_e}
    trial.update({n: summary[n]["base"]["periods"]["oos"]["daily_sharpe"] for n in CANDIDATES})
    trial_list = [0.0 if (v is None or not np.isfinite(v)) else v for v in trial.values()]
    assert len(trial_list) == 9

    placebo = pd.read_csv(PHASE_E / "placebo.csv")
    verdicts = {}
    for name in CANDIDATES:
        m = summary[name]["base"]["periods"]["oos"]
        dsr = M.deflated_sharpe(m["daily_sharpe"], m["days"], m["skew"], m["kurtosis"], trial_list)
        v, why = M.verdict(m, dsr)
        pv = {per: float((placebo[f"{per}_pf"] >= summary[name]["base"]["periods"][per]["pf"]).mean())
              if summary[name]["base"]["periods"][per]["pf"] is not None and
              np.isfinite(summary[name]["base"]["periods"][per]["pf"]) else None
              for per in ("oos", "validation")}
        verdicts[name] = {"verdict": v, "reason": why, "dsr": dsr, "placebo_p": pv,
                          "thresholds": M.evaluate_thresholds(m)}

    covid_frames = {tf: apply_exclusions(df, E.COVID, duration={"M1": 60, "M15": 900, "H1": 3600}[tf])[0]
                    for tf, df in frames.items()}
    seg2020 = [s for s in SEGMENTS if s.label == "2020"][0]
    minute = int(pd.Timestamp("2020-03-26 10:23", tz="UTC").timestamp())
    covid = {}
    for name in CANDIDATES:
        sigs = generate_signals(build(name), covid_frames)
        for label, fr, sg in (("con", frames, signals[name]), ("sin", covid_frames, sigs)):
            r = run_segment(E.make_bt("base", store), fr["M1"], sg, seg2020)
            m = aggregate({"2020": r}, ["2020"], initial, bootstrap=False)
            open_then = bool(len(r.trades) and ((r.trades["entry_time"] <= minute)
                                                & (r.trades["exit_time"] >= minute)).any())
            covid.setdefault(name, {})[label] = {"net_usd": m["net_usd"], "pf": m["pf"], "trades": m["trades"],
                                                 "position_open_at_minute": open_then}

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    payload = {"code_commit": commit, "n_trials": 9, "signals": {k: len(v) for k, v in signals.items()},
               "signal_generation_s": gen_s, "summary": summary, "verdicts": verdicts, "covid_2020": covid,
               "runtime_s": round(time.perf_counter() - t0, 1)}
    (OUT / "results.json").write_text(json.dumps(E._clean(payload), indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(E._clean({k: {kk: vv for kk, vv in v.items() if kk != "thresholds"}
                               for k, v in verdicts.items()}), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
