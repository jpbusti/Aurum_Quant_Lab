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
