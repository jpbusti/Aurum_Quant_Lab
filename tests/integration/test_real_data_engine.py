"""Motor con los datos y la configuración reales (sin terminal). Ejecutar con: pytest -m data"""

from pathlib import Path

import pandas as pd
import pytest

from aurum.backtesting.engine import ledger_matches_equity
from aurum.backtesting.setup import build_backtester, load_validated_m1, make_tick_provider
from aurum.backtesting.types import Signal
from aurum.config import PROJECT_ROOT, load_data_config
from aurum.data.storage import RawStore

pytestmark = pytest.mark.data


@pytest.fixture(scope="module")
def store():
    cfg = load_data_config()
    st = RawStore(PROJECT_ROOT / "data" / "raw", cfg["source"]["server"], cfg["symbol"]["name"])
    if not st.bar_files("M1"):
        pytest.skip("no hay datos descargados")
    return st


def _raw(s):
    return int(pd.Timestamp(s, tz="UTC").timestamp())


def test_scenarios_order_costs(store):
    cfg = load_data_config()
    m1 = load_validated_m1(store, cfg, _raw("2026-06-01"), _raw("2026-06-06"))
    s = Signal(decision_time=_raw("2026-06-02 10:00"), side=1, info_time=_raw("2026-06-02 10:00"),
               stop=float(m1.set_index("time_raw").loc[_raw("2026-06-02 10:00"), "open"]) - 20, max_hold_s=3600)
    costs = {}
    for sc in ("base", "adverse", "stress"):
        bt = build_backtester(sc, store)
        bt.risk.sizing_mode = "fixed"
        r = bt.run(m1, [s])
        assert ledger_matches_equity(r)
        t = r.trades.iloc[0]
        costs[sc] = t.net_usd   # mismo recorrido de precios; solo cambian los costes
    assert costs["base"] > costs["adverse"] > costs["stress"]


def test_excluded_placeholder_period_is_not_loaded(store):
    m1 = load_validated_m1(store, load_data_config(), _raw("2017-04-01"), _raw("2017-04-08"))
    assert m1["time_raw"].min() >= _raw("2017-04-06 01:00")


def test_tick_provider_reproduces_bar_extremes(store):
    provider = make_tick_provider(store)
    m1 = load_validated_m1(store, load_data_config(), _raw("2026-09-01 10:00"), _raw("2026-09-01 10:10"))
    for row in m1.itertuples():
        ticks = provider(row.time_raw)
        assert abs(ticks["bid"].max() - row.high) < 0.005 and abs(ticks["bid"].min() - row.low) < 0.005


def test_known_tick_gap_minute_is_not_used_for_intrabar(store):
    """2026-06-29 15:41: los ticks no reproducen la barra (faltan 15:37-15:41), así que el
    motor no debe usarlos para decidir el orden de stop y objetivo."""
    provider = make_tick_provider(store)
    minute = _raw("2026-06-29 15:41")
    m1 = load_validated_m1(store, load_data_config(), minute, minute + 60)
    ticks = provider(minute)
    assert abs(ticks["bid"].max() - m1["high"].iloc[0]) > 0.005
    assert Path(PROJECT_ROOT / "configs" / "cost_model.yaml").exists()
