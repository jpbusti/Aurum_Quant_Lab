"""Evaluación: placebo vectorizado, métricas y veredictos. Datos SINTÉTICOS."""

from dataclasses import replace

import numpy as np
import pytest

from aurum.data.storage import rates_to_frame
from aurum.evaluation.placebo import RandomPlacebo
from aurum.strategies.base import generate_signals
from aurum.strategies.references import RandomEntry, RandomParams, splitmix_uniform
from synthetic import MONDAY, make_rates, resample, session_minutes


@pytest.fixture(scope="module")
def frames():
    m1 = make_rates(session_minutes(MONDAY, 3), seed=7)
    return {"M15": rates_to_frame(resample(m1, 900)), "H1": rates_to_frame(resample(m1, 3600))}


@pytest.mark.parametrize("seed", [1, 2, 20261010])
def test_vectorized_placebo_equals_strategy(frames, seed):
    p = replace(RandomParams(), seed=seed)
    expected = generate_signals(RandomEntry(p), frames)
    got = RandomPlacebo(frames["M15"], p).signals(seed)
    assert [(s.decision_time, s.side) for s in got] == [(s.decision_time, s.side) for s in expected]
    for a, b in zip(got, expected):
        assert a.stop == pytest.approx(b.stop) and a.take_profit == pytest.approx(b.take_profit)


def test_splitmix_uniform_range_and_independence():
    u = splitmix_uniform(5, np.arange(100_000), 0)
    assert u.min() >= 0 and u.max() < 1 and abs(u.mean() - 0.5) < 0.01
    v = splitmix_uniform(5, np.arange(100_000), 1)
    assert abs(np.corrcoef(u, v)[0, 1]) < 0.02


# --- Métricas y veredictos -----------------------------------------------------------------

import math

import pandas as pd

from aurum.evaluation import metrics as M
from aurum.evaluation.walkforward import Segment, run_segment, session_of


def _trades(nets, rs=None):
    rs = rs if rs is not None else [n / 10 for n in nets]
    return pd.DataFrame({"net_usd": nets, "r_multiple": rs, "commission_usd": 0.07, "swap_usd": 0.0,
                         "entry_time": 0})


def test_profit_factor_and_basic_metrics_by_hand():
    tr = _trades([30.0, -10.0, 20.0, -20.0])
    eq = pd.Series([1000.0, 1030.0, 1020.0, 1040.0, 1020.0])
    m = M.compute(tr, eq, days_span=365.25, bootstrap=False)
    assert m["pf"] == pytest.approx(50 / 30)
    assert m["max_dd_pct"] == pytest.approx((1040 - 1020) / 1040 * 100)
    assert m["expectancy_r"] == pytest.approx(0.5)
    assert m["total_return_pct"] == pytest.approx(2.0)
    assert m["calmar"] == pytest.approx(0.02 / ((1040 - 1020) / 1040))
    assert m["recovery_factor"] == pytest.approx(20 / 20)


def test_sqn_caps_n_at_100():
    r = np.tile([1.0, -0.5], 200)
    m = M.compute(_trades(list(r * 10), list(r)), pd.Series([1000.0, 1001.0]), 10, bootstrap=False)
    assert m["sqn"] == pytest.approx(10 * r.mean() / r.std(ddof=1))


def test_block_bootstrap_is_deterministic_and_brackets_pf():
    rng = np.random.default_rng(0)
    net = rng.normal(1, 10, 500)
    b1, b2 = M.block_bootstrap_pf(net), M.block_bootstrap_pf(net)
    assert np.array_equal(b1, b2)
    lo, hi = np.percentile(b1, [5, 95])
    assert lo < M.profit_factor(net) < hi


GOOD = {"pf": 1.3, "pf_ci90_low": 1.05, "max_dd_pct": 10, "sharpe": 1.5, "sortino": 2.0, "calmar": 1.0,
        "trades": 400, "expectancy_r": 0.2, "sqn": 2.0, "recovery_factor": 3.0, "ulcer_index": 5}


def test_verdicts_follow_preregistered_rules():
    assert M.verdict(GOOD, 0.99)[0] == "CANDIDATE_FOR_PAPER"
    assert M.verdict(GOOD, 0.80)[0] == "INCONCLUSIVE"                       # regla DSR
    two_fail = {**GOOD, "sharpe": 0.9, "trades": 250}
    assert M.verdict(two_fail, 0.99)[0] == "INCONCLUSIVE"
    assert M.verdict({**two_fail, "sqn": 1.0}, 0.99)[0] == "REJECTED"        # estrictas y flexibles
    assert M.verdict({**GOOD, "pf": 1.1, "sharpe": 0.5, "sortino": 0.5}, 0.99)[0] == "REJECTED"  # >2 estrictas
    assert M.verdict({**GOOD, "pf": 1.15}, 0.99)[0] == "CANDIDATE_FOR_PAPER"  # PF >= 1,15 incluido
    assert M.verdict({**GOOD, "pf_ci90_low": float("nan")}, 0.99)[0] == "INCONCLUSIVE"  # NaN cuenta como fallo


def test_deflated_sharpe_penalizes_more_trials():
    one = M.deflated_sharpe(0.1, 500, 0.0, 3.0, [0.1])
    many = M.deflated_sharpe(0.1, 500, 0.0, 3.0, [0.1, 0.0, -0.05, 0.08, 0.02, 0.06])
    assert 0 <= many < one <= 1


def test_run_segment_purges_signals_that_would_cross_the_end():
    from aurum.backtesting.types import Signal
    from test_engine import FLAT, T0, bars, bt as make_bt

    data = bars([FLAT] * 10)
    seg = Segment("x", T0, T0 + 600)
    ok = Signal(decision_time=T0, side=1, stop=1990.0, info_time=T0, max_hold_s=120)
    crosses = Signal(decision_time=T0 + 300, side=1, stop=1990.0, info_time=T0 + 300, max_hold_s=600)
    res = run_segment(make_bt(), data, [ok, crosses], seg)
    assert len(res.trades) == 1 and res.trades.iloc[0].decision_time == T0


def test_sessions_in_new_york_time():
    ny = lambda h, m=0: MONDAY + (h + 7) * 3600 + m * 60     # servidor = NY + 7 h
    got = session_of(np.array([ny(20), ny(4), ny(9, 45), ny(15, 30), ny(17, 30)]))
    assert got.tolist() == ["asia", "londres", "nueva_york", "cierre", "otra"]
