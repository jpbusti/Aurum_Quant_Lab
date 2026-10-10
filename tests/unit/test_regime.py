"""HMM de 2 estados, velas diarias causales y CAND-REGIME-HMM-v1. Datos SINTÉTICOS."""

import numpy as np
import pandas as pd
import pytest

from aurum.data.storage import rates_to_frame
from aurum.features.daily import DAY, complete_days
from aurum.features.regime import filter_probs, fit_hmm
from aurum.features.sessions import ny_minute_of_day
from aurum.strategies.base import generate_signals
from aurum.strategies.candidates_r2 import RegimeMomentum
from fake_mt5 import RATES_DTYPE
from synthetic import MONDAY, resample


def two_regime_returns(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    state = np.zeros(n, dtype=int)
    for k in range(1, n):
        state[k] = state[k - 1] if rng.random() < 0.98 else 1 - state[k - 1]
    sd = np.where(state == 0, 0.005, 0.02)
    return rng.normal(0, sd), state


def test_hmm_recovers_two_volatility_regimes():
    x, state = two_regime_returns()
    m = fit_hmm(x)
    hi = m.high_vol_state
    assert np.sqrt(m.variances[hi]) == pytest.approx(0.02, rel=0.15)
    assert np.sqrt(m.variances[1 - hi]) == pytest.approx(0.005, rel=0.15)
    assert m.trans[0, 0] > 0.9 and m.trans[1, 1] > 0.9
    probs = filter_probs(m, x[1:])          # filtrado sobre la propia muestra, solo para medir acierto
    acc = ((probs[:, hi] > 0.5).astype(int) == (state[1:] == 1)).mean()
    assert acc > 0.9


def test_hmm_fit_is_deterministic():
    x, _ = two_regime_returns(seed=3)
    a, b = fit_hmm(x), fit_hmm(x)
    assert np.array_equal(a.means, b.means) and np.array_equal(a.trans, b.trans)


def test_filter_is_causal():
    x, _ = two_regime_returns(seed=5)
    m = fit_hmm(x[:800])
    p_full = filter_probs(m, x[800:])
    x2 = x.copy()
    x2[1000:] = np.random.default_rng(1).normal(0, 0.05, len(x2) - 1000)
    p_changed = filter_probs(m, x2[800:])
    assert np.allclose(p_full[:200], p_changed[:200])          # antes del cambio, idéntico
    assert not np.allclose(p_full[200:], p_changed[200:])


def test_complete_days_excludes_the_current_day():
    t = MONDAY + np.arange(0, 3 * 24) * 3600
    h1 = pd.DataFrame({"time_raw": t, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5})
    d = complete_days(h1, MONDAY + 2 * DAY + 5 * 3600)
    assert d["day"].tolist() == [MONDAY // DAY, MONDAY // DAY + 1]


# --- Estrategia con historia larga ----------------------------------------------------------

def long_frames(weeks=130, seed=11):
    """~2,5 años de velas M15 (lunes-viernes, 01:00-23:45 del servidor) con dos regímenes de
    volatilidad que alternan cada 12 semanas."""
    rng = np.random.default_rng(seed)
    times = []
    for w in range(weeks):
        for d in range(5):
            base = MONDAY + (w * 7 + d) * DAY
            times.append(base + 900 * np.arange(4, 96))
    t = np.concatenate(times).astype(np.int64)
    week = (t - MONDAY) // (7 * DAY)
    sd = np.where((week // 12) % 2 == 0, 0.6, 3.0)
    close = 2000 + np.cumsum(rng.normal(0.02, sd))
    open_ = np.r_[2000.0, close[:-1]]
    out = np.zeros(len(t), dtype=RATES_DTYPE)
    out["time"], out["open"], out["close"] = t, open_, close
    out["high"] = np.maximum(open_, close) + np.abs(rng.normal(0, sd / 3))
    out["low"] = np.minimum(open_, close) - np.abs(rng.normal(0, sd / 3))
    out["tick_volume"] = 100
    return {"M15": rates_to_frame(out), "H1": rates_to_frame(resample(out, 3600))}


@pytest.fixture(scope="module")
def lf():
    return long_frames()


@pytest.fixture(scope="module")
def regime_signals(lf):
    return generate_signals(RegimeMomentum(), lf)


def test_regime_needs_a_year_of_training(regime_signals):
    first_jan = int((np.datetime64("2025-01-01") - np.datetime64("1970-01-01")).astype(int)) * DAY
    assert MONDAY < first_jan
    assert regime_signals
    # Con ~250 días completos por año, no hay modelo hasta tener 250 retornos antes de un 1 de enero.
    assert all(s.decision_time >= first_jan for s in regime_signals)


def test_regime_trades_once_a_day_at_three_ny(regime_signals):
    days = [s.decision_time // DAY for s in regime_signals]
    assert len(days) == len(set(days))
    assert all(int(ny_minute_of_day(s.decision_time)) == 180 for s in regime_signals)
    assert all(int(ny_minute_of_day(s.decision_time + s.max_hold_s)) == 15 * 60 + 45 for s in regime_signals)


def test_regime_mostly_trades_in_calm_weeks(regime_signals):
    week = np.array([(s.decision_time - MONDAY) // (7 * DAY) for s in regime_signals])
    calm = (week // 12) % 2 == 0
    assert calm.mean() > 0.75


def _perturb(frames, t_cut, seed):
    rng = np.random.default_rng(seed)
    out = {}
    for tf, d in (("M15", 900), ("H1", 3600)):
        df = frames[tf].copy()
        fut = (df["time_raw"] + d > t_cut).to_numpy()
        o = df.loc[fut, "open"].to_numpy() + rng.normal(0, 40, fut.sum())
        c = df.loc[fut, "close"].to_numpy() + rng.normal(0, 40, fut.sum())
        df.loc[fut, "open"], df.loc[fut, "close"] = o, c
        df.loc[fut, "high"] = np.maximum(o, c) + 1
        df.loc[fut, "low"] = np.minimum(o, c) - 1
        out[tf] = df
    return out


@pytest.mark.parametrize("weeks_after_start", [70, 110])
def test_regime_no_lookahead(lf, regime_signals, weeks_after_start):
    t_cut = MONDAY + weeks_after_start * 7 * DAY + 2 * DAY + 10 * 3600   # miércoles 03:00 NY
    changed = _perturb(lf, t_cut, seed=weeks_after_start)
    after = generate_signals(RegimeMomentum(), changed)
    assert [s for s in regime_signals if s.decision_time <= t_cut] == [s for s in after if s.decision_time <= t_cut]
