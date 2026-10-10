"""Resumen de ticks y modelo de spread con datos SINTÉTICOS."""

import numpy as np
import pandas as pd
import pytest

from aurum.backtesting.spread_model import SpreadModel, calibrate, evaluate_candidates, join_minutes_with_bars
from aurum.backtesting.types import CostScenario
from aurum.data.tick_minutes import MAX_QUOTE_LIFE_MS, summarize_day
from synthetic import MONDAY

M = MONDAY + 3600 * 10


def test_time_weighted_spread_by_hand():
    # 3 ticks en un minuto: 10 puntos durante 50 s, 20 puntos durante 10 s y el último hasta el tope.
    t = np.array([M * 1000, M * 1000 + 50_000, M * 1000 + 60_000 + 0])
    ticks = pd.DataFrame({"time_msc": t, "bid": [2000.0, 2000.0, 2000.0], "ask": [2000.10, 2000.20, 2000.05]})
    minutes, hist = summarize_day(ticks, 0.01)
    first = minutes.iloc[0]
    assert first.ticks == 2
    assert first.spread_mean_tick == pytest.approx(15.0)                   # por tick: (10 + 20) / 2
    assert first.spread_mean_time == pytest.approx((10 * 50 + 20 * 10) / 60)  # por tiempo
    assert first.spread_min == 10 and first.spread_max == 20
    last = minutes.iloc[1]
    assert last.quoted_ms == MAX_QUOTE_LIFE_MS                             # vida máxima de la cotización
    assert hist["ms"].sum() == 50_000 + 10_000 + MAX_QUOTE_LIFE_MS


def test_spread_in_points_is_rounded_not_truncated():
    ticks = pd.DataFrame({"time_msc": [M * 1000], "bid": [4195.86], "ask": [4195.93]})  # 0.07 -> 7 puntos
    minutes, _ = summarize_day(ticks, 0.01)
    assert minutes.iloc[0].spread_min == 7


def _joined(n_minutes=600, excess=3.0, bar_min=5):
    t = M + 60 * np.arange(n_minutes)
    minutes = pd.DataFrame({"time_raw": t, "bid_high": 2001.0, "bid_low": 1999.0,
                            "spread_mean_time": bar_min + excess + np.zeros(n_minutes)})
    m1 = pd.DataFrame({"time_raw": t, "spread": bar_min, "high": 2001.0, "low": 1999.0})
    return join_minutes_with_bars(minutes, m1)


def test_inconsistent_minutes_are_excluded_from_calibration():
    j = _joined()
    minutes = pd.DataFrame({"time_raw": [M], "bid_high": [2003.0], "bid_low": [1999.0], "spread_mean_time": [9.0]})
    m1 = pd.DataFrame({"time_raw": [M], "spread": [5], "high": [2001.0], "low": [1999.0]})
    assert join_minutes_with_bars(minutes, m1).empty
    assert len(j) == 600


def test_calibrated_model_reproduces_constant_excess():
    model = calibrate(_joined(excess=3.0), {"test": True}, {"base": "mean"})
    sm = SpreadModel(model)
    t = np.array([M, M + 3600 * 5])                   # horas 10 y 15 (15 sin datos: usa el global)
    assert sm.spread_points(t, np.array([5, 0]), "mean").tolist() == pytest.approx([8.0, 3.0])


def test_model_tracks_bar_minimum_over_time():
    sm = SpreadModel(calibrate(_joined(excess=3.0), {}, {"base": "mean"}))
    # El mismo minuto del día con un mínimo de barra mayor (p. ej. 2020) da un spread mayor.
    assert sm.spread_points(np.array([M, M]), np.array([5, 40]), "mean").tolist() == pytest.approx([8.0, 43.0])


def test_evaluation_reports_each_candidate():
    ev = evaluate_candidates(_joined(), split_raw=M + 300 * 60)
    assert set(ev["candidates"]) == {"fijo_media_global", "media_por_hora", "minimo_barra_mas_exceso_por_hora"}
    assert ev["candidates"]["minimo_barra_mas_exceso_por_hora"]["mae_points"] == pytest.approx(0.0)


def test_commission_per_side_scales_with_volume_and_multiplier():
    sc = CostScenario("x", "mean", commission_per_side_per_lot=3.5, commission_multiplier=1.5)
    assert sc.commission_side(1.0) == pytest.approx(5.25)
    assert sc.commission_side(0.01) == pytest.approx(0.0525)
