"""Fase F: screening de familias con FDR, DSR y PBO (docs/PREREGISTRO_PHASE_F.md).

Ejecutar desde la raíz:
    .venv/Scripts/python experiments/phase_f/run.py --check     # vectorizada == referencia en datos reales
    .venv/Scripts/python experiments/phase_f/run.py --screen    # todas las variantes, capas de señal y capital
    .venv/Scripts/python experiments/phase_f/run.py --analyze   # correcciones y veredictos
    .venv/Scripts/python experiments/phase_f/run.py --sensitivity  # solo supervivientes (si los hay)

Salidas (no versionadas) en experiments/phase_f/: variants_<capa>.csv,
returns_<capa>.parquet y results.json. Resumen en docs/PHASE_F_FAMILIES.md.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd

from aurum.backtesting.setup import build_backtester, load_validated
from aurum.config import PROJECT_ROOT, load_data_config
from aurum.data.storage import RawStore
from aurum.evaluation import screening as S
from aurum.strategies.base import generate_signals
from aurum.strategies.families import all_variants, variant_params
from aurum.validation import statistical_corrections as SC

OUT = Path(__file__).parent
START = int(pd.Timestamp("2017-04-06 01:00", tz="UTC").timestamp())
END = int(pd.Timestamp("2026-10-10", tz="UTC").timestamp())
PERIODS = {"in_sample": ("2017-04-06 01:00", "2023-01-01"), "validation": ("2023-01-01", "2025-01-01"),
           "oos": ("2025-01-01", "2026-10-10")}

# Pre-registro, sección 6
Q_FDR = 0.10
DSR_MIN = 0.95
PBO_PASS, PBO_FAIL = 0.20, 0.50
PBO_SPLITS = 16
PREVIOUS_TRIALS = 9
SENS_STOP_SLIPPAGE_POINTS = 12

_W: dict = {}


def _init_worker():
    cfg = load_data_config()
    store = RawStore(PROJECT_ROOT / "data" / "raw", cfg["source"]["server"], cfg["symbol"]["name"])
    _W["frames"] = {tf: load_validated(store, cfg, tf) for tf in ("M1", "M15")}
    bt = build_backtester("base", store)
    _W["bt"] = {layer: S.layer_backtester(bt, layer) for layer in S.LAYERS}
    _W["variants"] = {fam: vs for fam, vs in all_variants().items()}


def _task(job):
    fam, i = job
    v = _W["variants"][fam][i]
    sigs = v.vector_signals(_W["frames"])
    out = {}
    for layer in S.LAYERS:
        m, rets = S.run_variant(_W["bt"][layer], _W["frames"]["M1"], sigs, START, END)
        row = {"family": fam, "variant": v.name, "layer": layer, **variant_params(v), **m}
        for per, (a, b) in PERIODS.items():
            ra, rb = (int(pd.Timestamp(x, tz="UTC").timestamp()) // 86400 for x in (a, b))
            sub = rets[(rets.index >= ra) & (rets.index < rb)]
            row[f"{per}_sharpe"] = float(sub.mean() / sub.std(ddof=1) * math.sqrt(252)) if sub.std(ddof=1) > 0 else 0.0
            row[f"{per}_return_pct"] = float((np.prod(1 + sub.to_numpy()) - 1) * 100)
        out[layer] = (row, rets)
    return out


def main_check():
    """Equivalencia en datos reales (2026-01 a 2026-03) para 1 de cada 6 variantes."""
    cfg = load_data_config()
    store = RawStore(PROJECT_ROOT / "data" / "raw", cfg["source"]["server"], cfg["symbol"]["name"])
    a, b = (int(pd.Timestamp(x, tz="UTC").timestamp()) for x in ("2025-10-01", "2026-04-01"))
    frames = {tf: load_validated(store, cfg, tf, a, b) for tf in ("M1", "M15")}
    lo = int(pd.Timestamp("2026-01-01", tz="UTC").timestamp())
    bad, n = [], 0
    for fam, vs in all_variants().items():
        for v in vs[::6]:
            key = lambda s: (s.decision_time, s.side, round(s.stop, 6), None if s.take_profit is None else round(s.take_profit, 6))
            ref = [key(s) for s in generate_signals(v, frames) if s.decision_time >= lo]
            vec = [key(s) for s in v.vector_signals(frames) if s.decision_time >= lo]
            n += 1
            if ref != vec:
                bad.append(v.name)
    print(f"variantes comprobadas: {n}; distintas: {bad}")


def main_screen(workers: int = 4):
    t0 = time.perf_counter()
    jobs = [(fam, i) for fam, vs in all_variants().items() for i in range(len(vs))]
    rows = {layer: [] for layer in S.LAYERS}
    rets = {layer: {} for layer in S.LAYERS}
    with mp.Pool(workers, initializer=_init_worker) as pool:
        for k, res in enumerate(pool.imap_unordered(_task, jobs), 1):
            for layer, (row, r) in res.items():
                rows[layer].append(row)
                rets[layer][row["variant"]] = r
            if k % 20 == 0:
                print(k, len(jobs), round(time.perf_counter() - t0), flush=True)
    for layer in S.LAYERS:
        S.export(rows[layer], rets[layer], OUT / f"variants_{layer}.csv", OUT / f"returns_{layer}.parquet")
    print("listo", round(time.perf_counter() - t0), "s")


def _clean(x):
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def analyze_layer(layer: str) -> dict:
    df = pd.read_csv(OUT / f"variants_{layer}.csv")
    mat = pd.read_parquet(OUT / f"returns_{layer}.parquet").fillna(0.0)
    n_new = len(df)
    n_trials = PREVIOUS_TRIALS + n_new
    srs = np.array([SC.moments(mat[v].to_numpy())[0] for v in df["variant"]])
    var_trials = float(np.var(srs[np.isfinite(srs)], ddof=1))
    df["sr_daily"] = srs
    df["q_family"] = np.nan
    for fam, g in df.groupby("family"):
        df.loc[g.index, "q_family"] = SC.benjamini_hochberg(g["p_value"].to_numpy())
    df["q_global"] = SC.benjamini_hochberg(df["p_value"].to_numpy())
    d = [SC.deflated_sharpe(mat[v].to_numpy(), n_trials, var_trials) for v in df["variant"]]
    df["dsr"] = [x["dsr"] for x in d]
    sr0 = d[0]["sr0"]
    df["pass_fdr"] = df["q_family"] < Q_FDR
    df["pass_dsr"] = df["dsr"] >= DSR_MIN
    out = {"n_trials": n_trials, "n_new": n_new, "var_trials_daily": var_trials, "sr0_daily": sr0,
           "sr0_annual": sr0 * math.sqrt(252), "families": {}}
    for fam, g in df.groupby("family"):
        cols = [c for c in g["variant"]]
        pbo = SC.pbo_cscv(mat[cols].to_numpy(), PBO_SPLITS)
        survivors = g[g["pass_fdr"] & g["pass_dsr"]]["variant"].tolist()
        if pbo["pbo"] >= PBO_FAIL or not g["pass_fdr"].any():
            verdict = "SIN_EDGE"
        elif survivors and pbo["pbo"] < PBO_PASS:
            verdict = "EDGE_CANDIDATO"
        else:
            verdict = "INCONCLUSO"
        out["families"][fam] = {
            "variants": int(len(g)), "pbo": pbo, "survivors_fdr": int(g["pass_fdr"].sum()),
            "survivors_dsr": int(g["pass_dsr"].sum()), "survivors_both": survivors, "verdict": verdict,
            "min_q": float(g["q_family"].min()), "max_dsr": float(g["dsr"].max()),
            "dist": {k: g[k].describe(percentiles=[.1, .5, .9]).to_dict() for k in ("pf", "sharpe", "p_value", "max_dd_pct")},
            "positive_net": int((g["net_usd"] > 0).sum()), "pf_above_1": int((g["pf"] > 1).sum()),
            "pf_above_115": int((g["pf"] >= 1.15).sum()),
            "zero_trades": int((g["trades"] == 0).sum()),
        }
    df.to_csv(OUT / f"analysis_{layer}.csv", index=False)
    return out


def cross_checks(layer: str) -> dict:
    """Contraste con nullius (PBO y DSR) y jsharpe (PSR y Sharpe crítico por FDR bayesiano)."""
    out = {}
    df = pd.read_csv(OUT / f"analysis_{layer}.csv")
    mat = pd.read_parquet(OUT / f"returns_{layer}.parquet").fillna(0.0)
    try:
        import nullius as nl
        for fam, g in df.groupby("family"):
            m = mat[list(g["variant"])].to_numpy()
            theirs = nl.probability_of_backtest_overfitting(m, n_splits=PBO_SPLITS, max_combos=20_000)
            out[f"nullius_pbo_{fam}"] = theirs["pbo"]
        best = df.loc[df["dsr"].idxmax()]
        theirs = nl.deflated_sharpe_ratio(mat[best["variant"]].to_numpy(), n_trials=PREVIOUS_TRIALS + len(df),
                                         var_across_trials=float(np.var(df["sr_daily"], ddof=1)))
        out["nullius_dsr_best"] = {"variant": best["variant"], "ours": best["dsr"], "nullius": theirs["dsr"]}
    except ImportError:
        out["nullius"] = "no instalado"
    try:
        from jsharpe.sharpe.corrections import control_for_FDR
        from jsharpe.sharpe.psr import probabilistic_sharpe_ratio
        t = len(mat)
        alpha, beta, src, qhat = control_for_FDR(Q_FDR, SR0=0.0, SR1=1.0 / math.sqrt(252), p_H1=0.05, T=t)
        out["jsharpe_fdr"] = {"alpha": alpha, "power": 1 - beta, "sr_critical_daily": src,
                              "sr_critical_annual": src * math.sqrt(252), "q_hat": qhat,
                              "variants_above": int((df["sr_daily"] > src).sum())}
        diffs = []
        for v in df["variant"]:
            sr, sk, ku, n = SC.moments(mat[v].to_numpy())
            if np.isfinite(sr) and n > 3:
                diffs.append(abs(SC.psr(sr, 0, n, sk, ku) - probabilistic_sharpe_ratio(sr, 0.0, T=n, gamma3=sk, gamma4=ku)))
        out["jsharpe_psr_max_abs_diff"] = max(diffs) if diffs else None
    except ImportError:
        out["jsharpe"] = "no instalado"
    return out


def main_analyze():
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    res = {"code_commit": commit}
    for layer in S.LAYERS:
        res[layer] = analyze_layer(layer)
        res[layer]["cross_checks"] = cross_checks(layer)
    (OUT / "results.json").write_text(json.dumps(_clean(res), indent=1, ensure_ascii=False), encoding="utf-8")
    for layer in S.LAYERS:
        print(layer, {f: (v["verdict"], v["survivors_fdr"], v["survivors_dsr"], round(v["pbo"]["pbo"], 3))
                      for f, v in res[layer]["families"].items()})


def main_sensitivity():
    """Supervivientes de la capa de capital: escenario adverso y slippage de stops medido."""
    df = pd.read_csv(OUT / "analysis_capital.csv")
    surv = df[df["pass_fdr"] & df["pass_dsr"]]
    if surv.empty:
        print("sin supervivientes: no hay sensibilidad que correr")
        return
    _init_worker()
    cfg = load_data_config()
    store = RawStore(PROJECT_ROOT / "data" / "raw", cfg["source"]["server"], cfg["symbol"]["name"])
    lookup = {v.name: v for vs in _W["variants"].values() for v in vs}
    rows = []
    for name in surv["variant"]:
        sigs = lookup[name].vector_signals(_W["frames"])
        for label in ("adverse", "stop_slippage_12"):
            bt = build_backtester("adverse" if label == "adverse" else "base", store)
            if label == "stop_slippage_12":
                bt.sc.slippage_points = SENS_STOP_SLIPPAGE_POINTS
            m, _ = S.run_variant(S.layer_backtester(bt, "capital"), _W["frames"]["M1"], sigs, START, END, bootstrap=False)
            rows.append({"variant": name, "scenario": label, **{k: m[k] for k in ("trades", "net_usd", "pf", "sharpe", "max_dd_pct")}})
    pd.DataFrame(rows).to_csv(OUT / "sensitivity.csv", index=False)
    print(pd.DataFrame(rows).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    for flag in ("--check", "--screen", "--analyze", "--sensitivity"):
        g.add_argument(flag, action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    if args.check:
        main_check()
    elif args.screen:
        main_screen(args.workers)
    elif args.analyze:
        main_analyze()
    else:
        main_sensitivity()
