"""Familias de la fase F: la versión vectorizada produce exactamente las mismas señales que
la de referencia con DataView, y cambiar velas futuras no altera las señales pasadas.

Datos SINTÉTICOS.
"""

import numpy as np
import pytest

from aurum.data.storage import rates_to_frame
from aurum.strategies.base import generate_signals
from aurum.strategies.families import FAMILIES, all_variants
from synthetic import MONDAY, make_rates, resample, session_minutes


def frames(seed=0, weeks=4):
    m1 = make_rates(session_minutes(MONDAY, weeks), seed)
    return {"M1": rates_to_frame(m1), "M15": rates_to_frame(resample(m1, 900)),
            "H1": rates_to_frame(resample(m1, 3600))}


F = frames()
VARIANTS = all_variants()
SAMPLE = [v for fam in VARIANTS.values() for i, v in enumerate(fam) if i % 9 == 0]


def _key(s):
    return (s.decision_time, s.side, round(s.stop, 9), None if s.take_profit is None else round(s.take_profit, 9),
            s.max_hold_s, s.info_time <= s.decision_time)


def test_grid_sizes_match_preregistration():
    assert {k: len(v) for k, v in VARIANTS.items()} == {"TREND": 72, "MEANREV": 64, "CALENDAR": 88}
    names = [v.name for fam in VARIANTS.values() for v in fam]
    assert len(set(names)) == len(names)
    assert set(FAMILIES) == {"TREND", "MEANREV", "CALENDAR"}


@pytest.mark.parametrize("strategy", SAMPLE, ids=lambda s: s.name)
def test_vector_matches_reference(strategy):
    ref = [_key(s) for s in generate_signals(strategy, F)]
    vec = [_key(s) for s in strategy.vector_signals(F)]
    assert vec == ref
    assert all(s.tag == strategy.name for s in strategy.vector_signals(F))


def test_sample_produces_signals_in_every_family():
    for fam, vs in VARIANTS.items():
        assert any(len(v.vector_signals(F)) > 0 for v in vs[::9]), fam


@pytest.mark.parametrize("cut_index", [300, 900])
def test_future_changes_do_not_alter_past_vector_signals(cut_index):
    t_cut = int(F["M15"]["time_raw"].iloc[cut_index]) + 900
    changed = {}
    rng = np.random.default_rng(7)
    for tf, df in F.items():
        d = {"M1": 60, "M15": 900, "H1": 3600}[tf]
        df = df.copy()
        fut = (df["time_raw"] + d > t_cut).to_numpy()
        shift = rng.normal(0, 25, fut.sum())
        for col in ("open", "high", "low", "close"):
            df.loc[fut, col] = df.loc[fut, col].to_numpy() * 1.03 + shift
        df.loc[fut, "high"] = df.loc[fut, ["open", "high", "low", "close"]].max(axis=1)
        df.loc[fut, "low"] = df.loc[fut, ["open", "high", "low", "close"]].min(axis=1)
        changed[tf] = df
    for v in SAMPLE:
        before = [_key(s) for s in v.vector_signals(F) if s.decision_time <= t_cut]
        after = [_key(s) for s in v.vector_signals(changed) if s.decision_time <= t_cut]
        assert before == after, v.name
