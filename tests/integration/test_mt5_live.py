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


def test_incremental_download_and_validation_on_real_terminal(tmp_path):
    """Descarga H1 y M15 de los últimos 30 días a un almacén temporal, dos veces, y valida."""
    import datetime as dt

    from aurum.data.ingest import update_bars
    from aurum.data.storage import RawStore
    from aurum.validation.quality import run_quality

    cfg = load_data_config()
    cfg["timeframes"] = ["M15", "H1"]
    cfg["download"]["bars_start"] = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    cfg["validation"]["exclusions"] = []
    store = RawStore(tmp_path, cfg["source"]["server"], cfg["symbol"]["name"])
    try:
        with MT5Client(path=cfg["terminal"].get("path")) as client:
            first = {tf: update_bars(client, store, cfg, tf) for tf in cfg["timeframes"]}
            second = {tf: update_bars(client, store, cfg, tf) for tf in cfg["timeframes"]}
    except MT5Error as exc:
        pytest.skip(f"terminal MT5 no disponible: {exc}")
    for tf in cfg["timeframes"]:
        assert first[tf]["new_rows"] > 0
        assert second[tf]["overlap_conflicts"] == 0
        assert store.read_bars(tf)["time_raw"].is_unique
    report = run_quality(store, cfg)
    assert report["blocked"] == []
