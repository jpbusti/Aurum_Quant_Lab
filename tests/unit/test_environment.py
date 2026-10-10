import datetime as dt
import json

import numpy as np

from aurum.data.mt5_client import UTC, MT5Client, decode_filling
from aurum.environment import (
    build_report,
    estimate_server_offset_hours,
    select_gold_symbol,
    summarize_bar_times,
    write_report,
)
from fake_mt5 import FakeMT5, SymbolInfo

NOW = dt.datetime.fromtimestamp(1_700_000_100, UTC)


# --- Identificación del símbolo ---------------------------------------------

def sym(name, base="XAU", profit="USD", custom=False):
    return {"name": name, "currency_base": base, "currency_profit": profit, "custom": custom}


def test_symbol_with_suffix_is_selected_only_if_configured():
    syms = [sym("XAUUSD.r"), sym("XAUEUR.r", profit="EUR"), sym("GOLD.NYSE", base="USD")]
    out = select_gold_symbol(syms, {"name": "XAUUSD.r", "currency_base": "XAU", "currency_profit": "USD"})
    assert out["selected"] == "XAUUSD.r"
    assert out["candidates"] == ["XAUUSD.r"]
    assert out["issues"] == []


def test_configured_name_missing_is_critical_and_nothing_selected():
    syms = [sym("XAUUSD.r")]
    out = select_gold_symbol(syms, {"name": "XAUUSD", "currency_base": "XAU", "currency_profit": "USD"})
    assert out["selected"] is None
    assert out["issues"][0].startswith("CRITICAL")


def test_custom_symbols_are_not_candidates():
    syms = [sym("XAUUSD_custom", custom=True)]
    out = select_gold_symbol(syms, {"name": "XAUUSD_custom", "currency_base": "XAU", "currency_profit": "USD"})
    assert out["candidates"] == []
    assert out["selected"] is None


def test_several_candidates_warns():
    syms = [sym("XAUUSD"), sym("XAUUSD.m")]
    out = select_gold_symbol(syms, {"name": "XAUUSD", "currency_base": "XAU", "currency_profit": "USD"})
    assert out["selected"] == "XAUUSD"
    assert out["issues"][0].startswith("WARN")


# --- Cobertura del historial -------------------------------------------------

def test_sparse_placeholder_bars_are_not_dense():
    # 300 barras diarias etiquetadas como M1 y después 2000 barras M1 reales.
    start = int(dt.datetime(2015, 1, 1, tzinfo=UTC).timestamp())
    sparse = start + 86400 * np.arange(300)
    dense_start = int(dt.datetime(2017, 3, 1, tzinfo=UTC).timestamp())
    dense = dense_start + 60 * np.arange(2000)
    out = summarize_bar_times(np.concatenate([sparse, dense]), 60)
    assert out["first_dense_month"] == "2017-03"
    assert out["bars"] == 2300
    assert out["sorted"] and out["duplicates"] == 0


def test_duplicates_and_disorder_are_reported():
    t = np.array([0, 60, 60, 120, 90])
    out = summarize_bar_times(t, 60)
    assert out["duplicates"] == 1
    assert out["sorted"] is False


def test_empty_history():
    out = summarize_bar_times(np.array([], dtype=np.int64), 60)
    assert out["bars"] == 0 and out["first_dense_month"] is None


# --- Desfase horario del servidor -------------------------------------------

def test_offset_detected_with_fresh_tick():
    now = 1_700_000_000
    assert estimate_server_offset_hours(now + 3 * 3600 - 2, now) == 3
    assert estimate_server_offset_hours(now - 10, now) == 0


def test_offset_unknown_when_market_closed():
    now = 1_700_000_000
    # Último tick de hace ~6,5 h (fin de semana): no se puede distinguir desfase de antigüedad.
    assert estimate_server_offset_hours(now - 23_286, now) is None


# --- Especificaciones --------------------------------------------------------

def test_filling_mask_decoding():
    assert decode_filling(2) == ["IOC"]
    assert decode_filling(3) == ["FOK", "IOC"]
    assert decode_filling(0) == []


def test_spec_enums_are_translated(fake):
    client = MT5Client(mt5=fake)
    spec = client.symbol_spec("XAUUSD.t")
    assert spec["trade_calc_mode"] == "FOREX"
    assert spec["trade_exemode"] == "MARKET"
    assert spec["filling_mode"] == ["IOC"]


# --- Informe completo --------------------------------------------------------

def test_report_ok_with_fake_terminal(cfg, fake, tmp_path):
    report = build_report(cfg, client=MT5Client(mt5=fake), now=NOW)
    mt5 = report["mt5"]
    assert mt5["available"]
    assert mt5["account"]["trade_mode"] == "DEMO"
    assert mt5["symbol_selection"]["selected"] == "XAUUSD.t"
    assert mt5["server_offset_hours"] == 0
    assert mt5["history"]["M15"]["bars"] == 500
    assert mt5["margin_min_volume"]["margin"] is not None
    assert report["status"] == "OK"
    assert fake.shutdown_called
    path = write_report(report, tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "OK"


def test_report_never_contains_identifying_account_data(cfg, fake):
    report = build_report(cfg, client=MT5Client(mt5=fake), now=NOW)
    text = json.dumps(report, default=str)
    assert "12345678" not in text
    assert "Secret Name" not in text
    assert set(report["mt5"]["account"]) <= {"server", "company", "currency", "leverage", "margin_mode", "trade_mode"}


def test_real_account_is_critical(cfg):
    report = build_report(cfg, client=MT5Client(mt5=FakeMT5(trade_mode=2)), now=NOW)
    assert report["status"] == "CRITICAL"
    assert any("REAL" in i for i in report["mt5"]["issues"])


def test_other_server_is_critical(cfg):
    report = build_report(cfg, client=MT5Client(mt5=FakeMT5(server="OtherBroker-Demo")), now=NOW)
    assert report["status"] == "CRITICAL"


def test_unavailable_terminal_is_reported_not_invented(cfg):
    report = build_report(cfg, client=MT5Client(mt5=FakeMT5(init_ok=False)), now=NOW)
    assert report["status"] == "UNAVAILABLE"
    assert report["mt5"]["available"] is False
    assert "symbol_spec" not in report["mt5"] and "history" not in report["mt5"]


def test_missing_gold_symbol_stops_before_specs(cfg):
    fake = FakeMT5(symbols=[SymbolInfo("EURUSD", "", "", "EUR", "USD", False, True)])
    report = build_report(cfg, client=MT5Client(mt5=fake), now=NOW)
    assert report["status"] == "CRITICAL"
    assert "symbol_spec" not in report["mt5"]


def test_stale_tick_leaves_offset_unverified(cfg):
    fake = FakeMT5(last_tick_time=int(NOW.timestamp()) - 23_286)
    report = build_report(cfg, client=MT5Client(mt5=fake), now=NOW)
    assert report["mt5"]["server_offset_hours"] is None
    assert report["status"] == "WARN"
