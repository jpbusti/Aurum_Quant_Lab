"""Pruebas contra el terminal real (cuenta demo). Ejecutar con: pytest -m mt5

Solo leen datos. Se omiten si el terminal no está disponible.
"""

import pytest

from aurum.config import load_data_config
from aurum.data.mt5_client import MT5Client, MT5Error
from aurum.environment import build_report

pytestmark = pytest.mark.mt5


@pytest.fixture(scope="module")
def report():
    cfg = load_data_config()
    try:
        with MT5Client(path=cfg["terminal"].get("path")):
            pass
    except MT5Error as exc:
        pytest.skip(f"terminal MT5 no disponible: {exc}")
    return build_report(cfg)


def test_terminal_is_demo_on_expected_server(report):
    cfg = load_data_config()
    assert report["mt5"]["account"]["trade_mode"] == "DEMO"
    assert report["mt5"]["account"]["server"] == cfg["source"]["server"]


def test_gold_symbol_exists_with_specs(report):
    spec = report["mt5"]["symbol_spec"]
    assert spec["currency_base"] == "XAU" and spec["currency_profit"] == "USD"
    for field in ("trade_tick_size", "trade_tick_value", "trade_contract_size", "volume_min", "volume_step"):
        assert spec[field] > 0


def test_history_is_sorted_without_duplicates(report):
    for tf, h in report["mt5"]["history"].items():
        assert h["bars"] > 0, tf
        assert h["sorted"] and h["duplicates"] == 0, tf
        assert h["first_dense_month"] is not None, tf


def test_no_critical_issues(report):
    assert report["status"] in ("OK", "WARN"), report["mt5"]["issues"]
