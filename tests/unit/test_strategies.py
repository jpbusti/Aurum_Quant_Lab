"""Interfaz común y ausencia de fuga para cada estrategia. Datos SINTÉTICOS: no dicen nada
sobre la rentabilidad de ninguna estrategia."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
import yaml

from aurum.config import CONFIG_DIR
from aurum.data.storage import rates_to_frame
from aurum.features.sessions import ny_minute_of_day, server_time_at_ny
from aurum.strategies.base import DataView, Strategy, generate_signals
from aurum.strategies.candidates import (
    AtrTrendBreakout,
    IntradayMomentumNY,
    OpeningRangeBreakoutNY,
)
from aurum.strategies.references import NoTrade, RandomEntry, RandomParams, SmaCross
from aurum.strategies.registry import STRATEGIES, build, default_params
from synthetic import MONDAY, make_rates, resample, session_minutes

TF_S = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600}


def frames_from(m1_rates):
    return {"M1": rates_to_frame(m1_rates), "M5": rates_to_frame(resample(m1_rates, 300)),
            "M15": rates_to_frame(resample(m1_rates, 900)), "H1": rates_to_frame(resample(m1_rates, 3600))}


@pytest.fixture(scope="module")
def frames():
    return frames_from(make_rates(session_minutes(MONDAY, 3), seed=7))


@pytest.fixture(scope="module")
def signals_by_strategy(frames):
    return {name: generate_signals(build(name), frames) for name in STRATEGIES}


# --- Registro --------------------------------------------------------------------------

def test_registry_matches_research_yaml():
    doc = yaml.safe_load((CONFIG_DIR / "research.yaml").read_text(encoding="utf-8"))
    reg = doc["strategies"]
    assert set(reg) == set(STRATEGIES)
    for name in STRATEGIES:
        assert reg[name]["params"] == default_params(name), name
        assert reg[name]["variants_tested"] <= reg[name]["variants_defined"]
    assert doc["variants_tested_total"] == sum(r["variants_tested"] for r in reg.values())


# --- Interfaz ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_interface_and_signal_validity(name, frames, signals_by_strategy):
    strategy = build(name)
    assert isinstance(strategy, Strategy) and strategy.signal_timeframe == "M15"
    m15 = frames["M15"].set_index(frames["M15"]["time_raw"] + 900)
    for s in signals_by_strategy[name]:
        assert s.side in (1, -1) and s.tag == name
        assert s.decision_time in m15.index                     # cierre de una vela M15
        assert s.info_time <= s.decision_time
        last_close = m15.loc[s.decision_time, "close"]
        assert (s.stop < last_close) if s.side == 1 else (s.stop > last_close)
        if s.take_profit is not None:
            assert (s.take_profit > last_close) if s.side == 1 else (s.take_profit < last_close)
        assert s.max_hold_s is None or s.max_hold_s > 0


def test_notrade_never_signals(signals_by_strategy):
    assert signals_by_strategy["REF-NOTRADE-v1"] == []


def test_strategies_other_than_notrade_produce_signals_on_synthetic_data(signals_by_strategy):
    for name, sigs in signals_by_strategy.items():
        if name != "REF-NOTRADE-v1":
            assert len(sigs) > 0, name


# --- No fuga: cambiar el futuro no cambia el pasado --------------------------------------

def perturb_after(frames, t_cut, seed):
    """Sustituye cada barra no cerrada en t_cut por otra distinta y coherente: cambian el
    nivel, la dirección y el rango de la vela (no solo un desplazamiento común)."""
    rng = np.random.default_rng(seed)
    out = {}
    for tf, df in frames.items():
        df = df.copy()
        future = (df["time_raw"] + TF_S[tf] > t_cut).to_numpy()
        n = int(future.sum())
        o = df.loc[future, "open"].to_numpy() + rng.normal(0, 30, n)
        c = df.loc[future, "close"].to_numpy() + rng.normal(0, 30, n)
        df.loc[future, "open"] = o
        df.loc[future, "close"] = c
        df.loc[future, "high"] = np.maximum(o, c) + np.abs(rng.normal(0, 5, n))
        df.loc[future, "low"] = np.minimum(o, c) - np.abs(rng.normal(0, 5, n))
        out[tf] = df
    return out


@pytest.mark.parametrize("name", sorted(STRATEGIES))
@pytest.mark.parametrize("day_offset", [2, 8, 15])
def test_no_lookahead_per_strategy(name, day_offset, frames, signals_by_strategy):
    t_cut = MONDAY + day_offset * 86400 + 16 * 3600 + 45 * 60      # 09:45 NY de ese día
    changed = perturb_after(frames, t_cut, seed=day_offset)
    before = [s for s in signals_by_strategy[name] if s.decision_time <= t_cut]
    after = [s for s in generate_signals(build(name), changed) if s.decision_time <= t_cut]
    assert before == after


# --- Comportamiento concreto ------------------------------------------------------------

def _day_frames(edit):
    """Tres semanas sintéticas con una barra M1 editada para fijar el resultado."""
    rates = make_rates(session_minutes(MONDAY, 3), seed=3)
    edit(rates)
    return frames_from(rates)


def test_orb_long_on_up_first_candle():
    day = (MONDAY + 7 * 86400) // 86400            # lunes de la 2ª semana (día NY = mismo número)
    t_range = server_time_at_ny(day, 9, 30)        # vela M15 de las 09:30 NY = 16:30 servidor
    assert int(ny_minute_of_day(t_range)) == 9 * 60 + 30

    def edit(r):
        m = (r["time"] >= t_range) & (r["time"] < t_range + 900)
        base = 2000.0
        r["open"][m] = base
        r["close"][m] = base
        r["high"][m] = base + 1
        r["low"][m] = base - 1
        last = np.where(m)[0][-1]
        r["close"][last] = base + 0.5
        r["high"][last] = max(r["high"][last], base + 0.5)

    f = _day_frames(edit)
    out = OpeningRangeBreakoutNY().decide(DataView(f, t_range + 900))
    side, stop, tp, max_hold = out
    assert side == 1 and stop == pytest.approx(1999.0)
    assert tp == pytest.approx(2000.5 + 10 * 1.5)
    assert max_hold == (16 * 60 - (9 * 60 + 45)) * 60


def test_orb_no_trade_on_doji_and_outside_time(frames):
    day = (MONDAY + 7 * 86400) // 86400
    t_range = server_time_at_ny(day, 9, 30)

    def edit(r):
        m = (r["time"] >= t_range) & (r["time"] < t_range + 900)
        idx = np.where(m)[0]
        r["close"][idx[-1]] = r["open"][idx[0]]
        r["high"][idx] = np.maximum(r["high"][idx], r["open"][idx[0]])
        r["low"][idx] = np.minimum(r["low"][idx], r["open"][idx[0]])

    f = _day_frames(edit)
    assert OpeningRangeBreakoutNY().decide(DataView(f, t_range + 900)) is None
    assert OpeningRangeBreakoutNY().decide(DataView(frames, t_range + 1800)) is None


def test_intraday_momentum_follows_morning_return():
    day = (MONDAY + 8 * 86400) // 86400             # martes de la 2ª semana
    t_prev_close = server_time_at_ny(day - 1, 16, 0)
    t_ten = server_time_at_ny(day, 10, 0)
    t_decision = server_time_at_ny(day, 15, 30)

    def edit(r):
        # Cierre de la vela que termina a las 16:00 NY del lunes y de la que termina a las 10:00 NY del martes.
        for t_close, price in ((t_prev_close, 2000.0), (t_ten, 2010.0)):
            i = np.where(r["time"] == t_close - 60)[0][0]
            r["close"][i] = price
            r["high"][i] = max(r["high"][i], price)
            r["low"][i] = min(r["low"][i], price)

    f = _day_frames(edit)
    side, stop, tp, max_hold = IntradayMomentumNY().decide(DataView(f, t_decision))
    assert side == 1 and tp is None and max_hold == 1800
    assert IntradayMomentumNY().decide(DataView(f, t_decision + 900)) is None


def test_random_is_reproducible_and_seed_dependent(frames):
    a = generate_signals(RandomEntry(), frames)
    b = generate_signals(RandomEntry(), frames)
    c = generate_signals(RandomEntry(replace(RandomParams(), seed=1)), frames)
    assert a == b and a != c
    minutes = [int(ny_minute_of_day(s.decision_time)) for s in a]
    assert all(3 * 60 <= m < 15 * 60 for m in minutes)
    eligible = sum(1 for t in frames["M15"]["time_raw"] + 900 if 180 <= ny_minute_of_day(t) < 900)
    assert 0.25 * 0.0125 * eligible <= len(a) <= 4 * 0.0125 * eligible


def _trend_frames(direction):
    t = session_minutes(MONDAY, 2)
    rates = make_rates(t, seed=11)
    drift = direction * 0.05 * np.arange(len(t))   # tendencia fuerte y constante
    for k in ("open", "high", "low", "close"):
        rates[k] = rates[k] + drift
    return frames_from(rates)


@pytest.mark.parametrize("direction", [1, -1])
def test_trend_and_sma_follow_direction(direction):
    f = _trend_frames(direction)
    trend = generate_signals(AtrTrendBreakout(), f)
    assert trend and all(s.side == direction for s in trend)


def test_sma_cross_detects_crossing():
    t = session_minutes(MONDAY, 1)
    rates = make_rates(t, seed=5)
    n = len(t)
    shape = np.where(np.arange(n) < n // 2, -0.05 * np.arange(n), -0.05 * (n // 2) + 0.08 * (np.arange(n) - n // 2))
    for k in ("open", "high", "low", "close"):
        rates[k] = rates[k] + shape
    sigs = generate_signals(SmaCross(), frames_from(rates))
    longs = [s for s in sigs if s.side == 1]
    assert longs and longs[0].decision_time > t[n // 2]


class _Leaky(Strategy):
    """Estrategia defectuosa a propósito: mira la vela M15 siguiente saltándose el DataView."""

    name = "LEAKY"
    signal_timeframe = "M15"

    def decide(self, view):
        m15 = view._frames["M15"]
        nxt = m15[m15["time_raw"] == view.decision_time]
        if nxt.empty:
            return None
        side = 1 if nxt["close"].iloc[0] > nxt["open"].iloc[0] else -1
        future_close = float(nxt["close"].iloc[0])          # precio que aún no existe
        return side, future_close - side * 500, None, 900


def test_no_lookahead_check_detects_a_leaky_strategy(frames):
    """La prueba de no fuga tiene poder: con una estrategia que mira el futuro, falla."""
    t_cut = MONDAY + 2 * 86400 + 16 * 3600 + 45 * 60
    changed = perturb_after(frames, t_cut, seed=2)
    before = [s for s in generate_signals(_Leaky(), frames) if s.decision_time <= t_cut]
    after = [s for s in generate_signals(_Leaky(), changed) if s.decision_time <= t_cut]
    assert before != after
