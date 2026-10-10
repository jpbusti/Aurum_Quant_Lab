"""Pruebas del motor con datos SINTÉTICOS cuyo resultado se calcula a mano.

Instrumento de prueba con las especificaciones de XAUUSD de la fase A:
contrato 100, tick 0.01 = 1 USD por lote -> 1.0 de precio = 100 USD por lote.
Con 0.01 lotes: 1.0 de precio = 1 USD.
"""

import numpy as np
import pandas as pd
import pytest

from aurum.backtesting.engine import Backtester, DataIntegrityError, ledger_matches_equity
from aurum.backtesting.spread_model import SpreadModel
from aurum.backtesting.types import CostScenario, ExecutionConfig, RiskConfig, Signal
from aurum.risk.sizing import Instrument, size_by_risk
from synthetic import MONDAY

T0 = MONDAY + 3600  # lunes 01:00 (hora del servidor)
SPEC = {"name": "XAUUSD", "point": 0.01, "trade_tick_size": 0.01, "trade_tick_value": 1.0,
        "trade_contract_size": 100.0, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01,
        "swap_long": -50.0, "swap_short": 20.0, "swap_rollover3days": 3, "digits": 2,
        "trade_calc_mode": "FOREX", "currency_profit": "USD"}
INS = Instrument.from_spec(SPEC, leverage=200)


def flat_model(excess_points: float) -> SpreadModel:
    stats = {k: excess_points for k in ("mean", "p50", "p75", "p90", "p95", "p99")}
    return SpreadModel({"scenario_excess_stat": {"t": "mean"}, "fallback_excess": stats, "by_hour": {}})


def bars(rows, start=T0, step=60):
    o, h, lo, c = np.array(rows, dtype=float).T
    return pd.DataFrame({"time_raw": start + step * np.arange(len(rows)), "open": o, "high": h, "low": lo,
                         "close": c, "spread": 0})


def bt(spread_pts=10, slippage=0, commission=3.5, fixed=0.01, risk=None, ticks=None, **ex):
    sc = CostScenario("t", "mean", slippage_points=slippage, commission_per_side_per_lot=commission)
    rk = risk or RiskConfig(initial_balance=10_000, sizing_mode="fixed", fixed_volume=fixed,
                            daily_loss_fraction=None, max_drawdown_fraction=None)
    return Backtester(INS, flat_model(spread_pts), sc, ExecutionConfig(**ex), rk, ticks)


def sig(t, side, stop, tp=None, **kw):
    return Signal(decision_time=t, side=side, stop=stop, take_profit=tp, info_time=t, **kw)


FLAT = (2000.0, 2000.5, 1999.5, 2000.0)


# --- Operaciones ganadoras y perdedoras -----------------------------------------------

def test_winning_long_pnl_by_hand():
    data = bars([FLAT, FLAT, (2000.0, 2006.0, 1999.8, 2005.5), FLAT])
    r = bt().run(data, [sig(T0, 1, stop=1990.0, tp=2005.0)])
    t = r.trades.iloc[0]
    assert t.entry_price == pytest.approx(2000.10)          # ask = bid 2000.00 + 10 puntos
    assert t.exit_price == pytest.approx(2005.0)            # objetivo, sin slippage
    assert t.gross_usd == pytest.approx(4.90)               # (2005 - 2000.10) x 1 USD
    assert t.commission_usd == pytest.approx(0.07)          # 3.50 x 0.01 x 2 lados
    assert t.net_usd == pytest.approx(4.83)
    assert t.exit_reason == "objetivo" and t.exit_time == T0 + 120
    assert ledger_matches_equity(r)


def test_losing_long_with_stop_slippage():
    data = bars([FLAT, (2000.0, 2000.2, 1994.0, 1995.0), FLAT])
    r = bt(slippage=2).run(data, [sig(T0, 1, stop=1995.0, tp=2010.0)])
    t = r.trades.iloc[0]
    assert t.entry_price == pytest.approx(2000.12)          # ask + 2 puntos de slippage
    assert t.exit_price == pytest.approx(1994.98)           # stop - 2 puntos
    assert t.net_usd == pytest.approx((1994.98 - 2000.12) - 0.07)
    assert t.exit_reason == "stop"


def test_short_uses_bid_to_open_and_ask_to_close():
    # Corto: entra al bid 2000.00; objetivo comparado con el ask = bid + 0.10.
    data = bars([FLAT, (2000.0, 2000.1, 1994.8, 1995.0), FLAT])
    r = bt().run(data, [sig(T0, -1, stop=2010.0, tp=1995.0)])
    t = r.trades.iloc[0]
    assert t.entry_price == pytest.approx(2000.0)
    assert t.exit_price == pytest.approx(1995.0)            # ask mínimo 1994.90 <= 1995
    assert t.gross_usd == pytest.approx(5.0)


def test_short_target_not_reached_because_of_spread():
    # El bid toca 1995.00 pero el ask no baja de 1995.10: el objetivo del corto no se ejecuta.
    data = bars([FLAT, (2000.0, 2000.1, 1995.0, 1996.0)])
    r = bt().run(data, [sig(T0, -1, stop=2010.0, tp=1995.0)])
    assert r.trades.iloc[0].exit_reason == "fin de datos"


def test_short_stop_hit_on_ask():
    # El bid llega a 2004.95 y el ask (bid + 0.10) toca el stop de 2005.00.
    data = bars([FLAT, (2000.0, 2004.95, 1999.9, 2003.0), FLAT])
    r = bt(slippage=1).run(data, [sig(T0, -1, stop=2005.0, tp=1990.0)])
    t = r.trades.iloc[0]
    assert t.exit_reason == "stop" and t.exit_price == pytest.approx(2005.01)


# --- Momento y precio de ejecución ------------------------------------------------------

def test_signal_executes_at_next_bar_open_not_before():
    data = bars([(2000.0, 2001, 1999, 2000.5), (2003.0, 2004, 2002, 2003.5), FLAT])
    r = bt(spread_pts=0).run(data, [sig(T0 + 30, 1, stop=1990.0)])  # señal a mitad de la primera barra
    t = r.trades.iloc[0]
    assert t.entry_time == T0 + 60 and t.entry_price == pytest.approx(2003.0)


def test_signal_without_price_within_delay_is_rejected():
    data = bars([FLAT, FLAT])
    data.loc[1, "time_raw"] = T0 + 3600   # hueco de una hora
    r = bt(max_entry_delay_s=120).run(data, [sig(T0 + 60, 1, stop=1990.0)])
    assert r.trades.empty and "retraso" in r.rejections.iloc[0].reason


def test_stop_on_wrong_side_is_rejected():
    r = bt().run(bars([FLAT, FLAT]), [sig(T0, 1, stop=2001.0)])
    assert r.trades.empty and "lado equivocado" in r.rejections.iloc[0].reason


# --- Comisión y slippage ----------------------------------------------------------------

def test_commission_is_charged_once_per_side():
    data = bars([FLAT, FLAT, (2000.0, 2006.0, 1999.8, 2005.5)])
    r1 = bt(fixed=1.0).run(data, [sig(T0, 1, stop=1990.0, tp=2005.0)])
    assert r1.trades.iloc[0].commission_usd == pytest.approx(7.00)   # 3.50 x 2 lados x 1 lote
    r2 = bt(fixed=0.01).run(data, [sig(T0, 1, stop=1990.0, tp=2005.0)])
    assert r2.trades.iloc[0].commission_usd == pytest.approx(0.07)


def test_cost_turns_gross_edge_into_net_loss():
    # Ganancia bruta de 0.05 USD (5 puntos x 0.01 lotes) que la comisión y el spread anulan.
    data = bars([FLAT, (2000.0, 2000.2, 1999.9, 2000.1)])
    r = bt(spread_pts=0, slippage=0).run(data, [sig(T0, 1, stop=1990.0, tp=2000.05)])
    t = r.trades.iloc[0]
    assert t.gross_usd == pytest.approx(0.05) and t.net_usd == pytest.approx(-0.02)
    r2 = bt(spread_pts=10).run(data, [sig(T0, 1, stop=1990.0, tp=2000.15)])
    assert r2.trades.iloc[0].net_usd < 0


# --- Huecos, tiempo y final -----------------------------------------------------------

def test_gap_through_stop_exits_at_open():
    data = bars([FLAT, (1990.0, 1991.0, 1989.0, 1990.5)])
    r = bt(slippage=2).run(data, [sig(T0, 1, stop=1995.0)])
    t = r.trades.iloc[0]
    assert t.exit_reason == "stop (hueco)" and t.exit_price == pytest.approx(1989.98)
    assert r.stats["gap_exits"] == 1


def test_time_exit():
    data = bars([FLAT] * 6)
    r = bt(spread_pts=0).run(data, [sig(T0, 1, stop=1990.0, max_hold_s=180)])
    t = r.trades.iloc[0]
    assert t.exit_reason == "tiempo" and t.exit_time == T0 + 180


def test_position_open_at_end_is_closed_at_last_bid():
    data = bars([FLAT, (2000.0, 2002.0, 1999.0, 2001.5)])
    r = bt().run(data, [sig(T0, 1, stop=1990.0)])
    t = r.trades.iloc[0]
    assert t.exit_reason == "fin de datos" and t.exit_price == pytest.approx(2001.5)
    assert ledger_matches_equity(r)


def test_mark_to_market_while_open():
    data = bars([FLAT, (2000.0, 2003.0, 1999.0, 2002.0), (2002.0, 2006.0, 2001.0, 2005.0)])
    r = bt(spread_pts=0, commission=0).run(data, [sig(T0, 1, stop=1990.0, tp=2005.0)])
    assert r.equity["equity"].iloc[1] == pytest.approx(10_000 + 2.0)   # bid 2002 - entrada 2000


# --- Stop y objetivo en la misma barra --------------------------------------------------

AMBIG = (2000.0, 2006.0, 1994.0, 2000.0)


def test_same_bar_without_ticks_assumes_stop():
    r = bt(spread_pts=0).run(bars([AMBIG]), [sig(T0, 1, stop=1995.0, tp=2005.0)])
    assert r.trades.iloc[0].exit_reason == "stop"
    assert r.stats["same_bar_by_policy"] == 1


def _ticks(prices):
    return lambda minute: pd.DataFrame({"time_msc": minute * 1000 + np.arange(len(prices)),
                                        "bid": prices, "ask": np.array(prices) + 0.0})


def test_same_bar_resolved_by_ticks_target_first():
    ticks = _ticks([2000.0, 2006.0, 1994.0, 2000.0])
    r = bt(spread_pts=0, ticks=ticks).run(bars([AMBIG]), [sig(T0, 1, stop=1995.0, tp=2005.0)])
    assert r.trades.iloc[0].exit_reason == "objetivo"
    assert r.stats["same_bar_resolved_by_ticks"] == 1


def test_incomplete_ticks_fall_back_to_policy():
    ticks = _ticks([2000.0, 2006.0, 1997.0])    # no reproducen el mínimo de la barra
    r = bt(spread_pts=0, ticks=ticks).run(bars([AMBIG]), [sig(T0, 1, stop=1995.0, tp=2005.0)])
    assert r.trades.iloc[0].exit_reason == "stop"
    assert r.stats["same_bar_by_policy"] == 1


# --- Volumen mínimo, paso y riesgo -----------------------------------------------------

def test_volume_rounds_down_to_step():
    # 0.5 % de 1 000 USD = 5 USD; stop a 1.40 USD -> 140 USD por lote -> 0.0357 -> 0.03
    s = size_by_risk(INS, 1_000, 0.005, entry=2000.0, stop=1998.6)
    assert s.volume == pytest.approx(0.03) and s.risk_usd <= s.allowed_risk_usd


def test_min_volume_exceeding_risk_blocks_trade():
    # 0.5 % de 200 USD = 1 USD; con 0.01 lotes un stop de 5 USD arriesga 5 USD.
    s = size_by_risk(INS, 200, 0.005, entry=2000.0, stop=1995.0)
    assert s.volume == 0 and "volumen mínimo" in s.reason
    risk = RiskConfig(initial_balance=200, sizing_mode="risk", risk_per_trade_fraction=0.005,
                      daily_loss_fraction=None, max_drawdown_fraction=None)
    r = bt(risk=risk).run(bars([FLAT, FLAT]), [sig(T0, 1, stop=1995.0)])
    assert r.trades.empty and "volumen mínimo" in r.rejections.iloc[0].reason


def test_risk_sizing_includes_costs_and_never_exceeds_allowance():
    risk = RiskConfig(initial_balance=10_000, sizing_mode="risk", risk_per_trade_fraction=0.005,
                      daily_loss_fraction=None, max_drawdown_fraction=None)
    data = bars([FLAT, (2000.0, 2000.2, 1994.0, 1995.0)])
    r = bt(risk=risk, slippage=2).run(data, [sig(T0, 1, stop=1995.0)])
    t = r.trades.iloc[0]
    assert -t.net_usd <= 50.0 + 1e-9                       # nunca más del 0.5 % de 10 000
    assert round(t.volume / 0.01) == t.volume / 0.01


def test_insufficient_margin_is_rejected():
    risk = RiskConfig(initial_balance=10, sizing_mode="fixed", fixed_volume=0.01,
                      daily_loss_fraction=None, max_drawdown_fraction=None)
    r = bt(risk=risk).run(bars([FLAT, FLAT]), [sig(T0, 1, stop=1990.0)])  # margen 0.01 lotes = 10 USD
    assert "margen" in r.rejections.iloc[0].reason


# --- Fuga de información e integridad -------------------------------------------------

def test_signal_using_future_information_is_rejected():
    bad = Signal(decision_time=T0, side=1, stop=1990.0, info_time=T0 + 60)
    r = bt().run(bars([FLAT, FLAT]), [bad])
    assert r.trades.empty and "fuga" in r.rejections.iloc[0].reason


@pytest.mark.parametrize("swap", [(0, 1), (1, 1)])
def test_unordered_or_duplicated_bars_raise(swap):
    data = bars([FLAT, FLAT, FLAT])
    if swap == (0, 1):
        data.loc[[0, 1], "time_raw"] = data.loc[[1, 0], "time_raw"].to_numpy()
    else:
        data.loc[1, "time_raw"] = data.loc[0, "time_raw"]
    with pytest.raises(DataIntegrityError):
        bt().run(data, [])


def test_incoherent_ohlc_raises():
    data = bars([FLAT, (2000.0, 1999.0, 1998.0, 2000.0)])
    with pytest.raises(DataIntegrityError):
        bt().run(data, [])


# --- Señales con posición abierta, swaps, límites --------------------------------------

def test_signal_while_position_open_is_rejected():
    data = bars([FLAT] * 5)
    r = bt().run(data, [sig(T0, 1, stop=1990.0), sig(T0 + 120, -1, stop=2010.0)])
    assert len(r.trades) == 1 and r.rejections.iloc[0].reason == "posición abierta"


def test_swap_charged_per_night_with_triple_wednesday():
    # Largo de lunes 01:00 a viernes 01:00: noches lun, mar, mié(x3), jue = 6 noches.
    day = 86400
    rows = [FLAT] * 5
    data = pd.DataFrame({"time_raw": [T0 + d * day for d in range(5)], "open": 2000.0, "high": 2000.5,
                         "low": 1999.5, "close": 2000.0, "spread": 0})
    r = bt(spread_pts=0, commission=0).run(data, [sig(T0, 1, stop=1990.0)])
    t = r.trades.iloc[0]
    assert len(rows) == 5
    assert t.swap_usd == pytest.approx(6 * -50.0 * 0.01 * 1.0)   # -50 puntos x 1 USD/punto/lote x 0.01
    assert ledger_matches_equity(r)


def test_daily_loss_limit_blocks_new_entries_same_day():
    risk = RiskConfig(initial_balance=100, sizing_mode="fixed", fixed_volume=0.01,
                      daily_loss_fraction=0.02, max_drawdown_fraction=None)
    data = bars([FLAT, (2000.0, 2000.0, 1996.0, 1996.0), FLAT, FLAT, FLAT])
    r = bt(spread_pts=0, commission=0, risk=risk).run(
        data, [sig(T0, 1, stop=1997.0), sig(T0 + 180, 1, stop=1990.0)])
    assert len(r.trades) == 1                               # pierde 3 USD = 3 % del día
    assert "pérdida diaria" in r.rejections.iloc[0].reason


def test_ledger_and_equity_consistent_over_many_trades():
    rng = np.random.default_rng(1)
    closes = 2000 + np.cumsum(rng.normal(0, 0.5, 2000))
    rows = [(c, c + abs(rng.normal(0, 0.3)), c - abs(rng.normal(0, 0.3)), c) for c in closes]
    data = bars(rows)
    signals = [sig(int(data.time_raw[i]), 1 if i % 2 else -1,
                   stop=closes[i] - 3 if i % 2 else closes[i] + 3,
                   tp=closes[i] + 3 if i % 2 else closes[i] - 3) for i in range(0, 1990, 25)]
    r = bt(slippage=2).run(data, signals)
    assert len(r.trades) > 20
    assert ledger_matches_equity(r)
    eq = r.equity.set_index("time_raw")["equity"]
    for t in r.trades.itertuples():
        assert np.isfinite(eq.loc[t.exit_time])
