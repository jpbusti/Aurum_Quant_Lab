import datetime as dt

import numpy as np
import pandas as pd
import pytest

from aurum.data.ingest import update_bars, update_ticks
from aurum.data.mt5_client import MT5Client
from aurum.data.storage import RawStore, rates_to_frame, ticks_to_frame
from aurum.validation import checks as C
from aurum.validation.quality import DataBlockedError, apply_exclusions, require_usable, run_quality
from fake_mt5 import FakeMT5
from synthetic import MONDAY, make_rates, resample, session_minutes, ticks_for

UTC = dt.timezone.utc
NOW = int(dt.datetime(2026, 1, 1, tzinfo=UTC).timestamp())
SESSIONS = {"daily_open": "01:00", "open_tolerance_min": 5, "daily_break_max_min": 75, "early_close_max_hours": 6}


def frame(times, seed=0):
    return rates_to_frame(make_rates(np.asarray(times, dtype=np.int64), seed))


# --- Estructura -------------------------------------------------------------------

def test_schema_missing_column_is_critical():
    df = frame(session_minutes()[:10]).drop(columns="spread")
    assert C.check_schema(df)["severity"] == "CRITICAL"


@pytest.mark.parametrize("times", [
    [60, 0, 120],          # desordenado
    [0, 60, 60, 120],      # duplicado
    [0, 61, 120],          # fuera de la rejilla
])
def test_bad_timestamps_are_critical(times):
    t = np.array(times) + MONDAY
    assert C.check_timestamps(t, 60, NOW)["severity"] == "CRITICAL"


def test_future_date_is_critical():
    assert C.check_timestamps(np.array([NOW + 10 * 86400]), 60, NOW)["severity"] == "CRITICAL"


@pytest.mark.parametrize("col,value", [("high", 1000.0), ("low", 3000.0), ("close", np.nan),
                                       ("open", -1.0), ("close", np.inf)])
def test_bad_prices_are_critical(col, value):
    df = frame(session_minutes()[:50])
    df.loc[10, col] = value
    res = C.check_prices(df)
    assert res["severity"] == "CRITICAL"


def test_clean_prices_ok():
    assert C.check_prices(frame(session_minutes()))["severity"] == "OK"


# --- Huecos -----------------------------------------------------------------------

def test_gap_classification_on_server_calendar():
    t = session_minutes(MONDAY, 3)
    tue_noon = MONDAY + 86400 + 12 * 3600
    wed = MONDAY + 2 * 86400
    keep = ~((t >= tue_noon) & (t < tue_noon + 45 * 60))          # 45 min sin explicar
    keep &= ~((t >= tue_noon + 3 * 3600) & (t < tue_noon + 3 * 3600 + 120))  # 2 min sin explicar
    keep &= ~((t >= wed + 20 * 3600) & (t < wed + 24 * 3600))       # cierre anticipado a las 20:00
    fri2 = MONDAY + 11 * 86400
    keep &= ~((t >= fri2) & (t < fri2 + 86400))                     # festivo: viernes de la 2ª semana
    gaps = C.classify_gaps(t[keep], 60, SESSIONS)
    kinds = gaps["kind"].value_counts().to_dict()
    assert kinds["unexplained"] == 2
    assert kinds["early_close"] == 1
    assert kinds["weekend"] == 2  # uno normal y otro alargado por el festivo del viernes
    assert kinds["daily_break"] == 10
    res = C.check_gaps(t[keep], 60, SESSIONS, warn_min=30)
    assert res["severity"] == "WARN"
    assert res["metrics"]["unexplained_long"] == 1 and res["metrics"]["unexplained_short"] == 1


def test_midweek_holiday_is_classified():
    t = session_minutes(MONDAY, 1)
    wed = MONDAY + 2 * 86400
    t = t[~((t >= wed - 3600) & (t < wed + 86400 + 3600))]  # cierre desde el martes 23:00 al jueves 01:00
    gaps = C.classify_gaps(t, 60, SESSIONS)
    assert "holiday" in set(gaps["kind"])


def test_clean_calendar_has_no_unexplained_gaps():
    res = C.check_gaps(session_minutes(MONDAY, 3), 60, SESSIONS, warn_min=30)
    assert res["severity"] == "OK"
    assert res["metrics"]["by_kind"] == {"daily_break": 12, "weekend": 2}


def test_weekly_open_detected_at_server_open():
    opens = C.weekly_open_times(session_minutes(MONDAY, 3), 60, SESSIONS)
    assert set(opens) == {"01:00"}


# --- Saltos y spread --------------------------------------------------------------

def test_price_jump_is_flagged_not_removed():
    df = frame(session_minutes())
    df.loc[2000:, ["open", "high", "low", "close"]] += 80.0
    res = C.check_returns(df, 60, k=25)
    assert res["severity"] == "WARN" and res["metrics"]["flagged"] >= 1
    assert len(df) == len(session_minutes())


def test_jump_across_weekend_gap_is_not_counted():
    t = session_minutes(MONDAY, 2)
    df = frame(t)
    second_week = t >= MONDAY + 7 * 86400
    df.loc[second_week, ["open", "high", "low", "close"]] += 80.0
    assert C.check_returns(df, 60, k=25)["metrics"]["flagged"] == 0


def test_negative_spread_is_critical():
    df = frame(session_minutes()[:10])
    df.loc[3, "spread"] = -1
    assert C.check_spread_field(df)["severity"] == "CRITICAL"


# --- Coherencia entre timeframes y con ticks ----------------------------------

def test_native_matches_resampled_m1():
    rates = make_rates(session_minutes())
    res = C.check_resample(rates_to_frame(rates), rates_to_frame(resample(rates, 900)), 900, 0.011, 0.001, "M15")
    assert res["severity"] == "OK" and res["metrics"]["mismatched"] == 0


def test_native_mismatch_is_reported():
    rates = make_rates(session_minutes())
    native = rates_to_frame(resample(rates, 900))
    native.loc[5, "high"] += 1.0
    res = C.check_resample(rates_to_frame(rates), native, 900, 0.011, 0.0, "M15")
    assert res["severity"] == "WARN" and res["metrics"]["mismatched"] == 1


def test_bars_vs_ticks_match():
    rates = make_rates(session_minutes()[:500])
    res = C.check_bars_vs_ticks(rates_to_frame(rates), C.ticks_per_minute(ticks_to_frame(ticks_for(rates)), 0.01))
    assert res["metrics"]["high_match_fraction"] == 1.0
    assert res["metrics"]["low_match_fraction"] == 1.0
    assert res["metrics"]["tick_spread_mean_pts_p50"] == 5.0


def test_bars_vs_ticks_disagreement_warns():
    rates = make_rates(session_minutes()[:500])
    ticks = ticks_for(rates)
    ticks["bid"][1::4] += 0.5  # los ticks del máximo no coinciden con la barra
    res = C.check_bars_vs_ticks(rates_to_frame(rates), C.ticks_per_minute(ticks_to_frame(ticks), 0.01))
    assert res["severity"] == "WARN"


def test_ticks_ask_below_bid_is_critical():
    rates = make_rates(session_minutes()[:10])
    ticks = ticks_for(rates)
    ticks["ask"][3] = ticks["bid"][3] - 0.1
    assert C.check_ticks(ticks_to_frame(ticks))["severity"] == "CRITICAL"


# --- Procedencia y archivos ---------------------------------------------------------

def _dl(server="S", h="a"):
    return {"server": server, "company": "C", "symbol": "XAUUSD", "account_trade_mode": "DEMO", "spec_hash": h}


def test_mixed_sources_are_critical():
    res = C.check_provenance({"downloads": [_dl("S"), _dl("T")]}, {})
    assert res["severity"] == "CRITICAL"


def test_swap_change_is_info_and_contract_change_is_warn():
    specs = {"a": {"swap_long": -1.0, "trade_contract_size": 100}, "b": {"swap_long": -2.0, "trade_contract_size": 100},
             "c": {"swap_long": -2.0, "trade_contract_size": 50}}
    assert C.check_provenance({"downloads": [_dl(h="a"), _dl(h="b")]}, specs)["severity"] == "INFO"
    res = C.check_provenance({"downloads": [_dl(h="a"), _dl(h="b"), _dl(h="c")]}, specs)
    assert res["severity"] == "WARN"
    assert res["examples"][-1]["fields"] == ["trade_contract_size"]


def test_row_in_wrong_year_file_is_critical():
    df = frame(session_minutes()[:5])
    df["_file"] = "2023.parquet"
    assert C.check_file_overlaps(df)["severity"] == "CRITICAL"


def test_exclusion_requires_reason_and_removes_rows():
    df = frame(session_minutes()[:120])
    a = pd.Timestamp(int(df["time_raw"][10]), unit="s").isoformat()
    b = pd.Timestamp(int(df["time_raw"][20]), unit="s").isoformat()
    with pytest.raises(ValueError):
        apply_exclusions(df, [{"from": a, "to": b}])
    out, applied = apply_exclusions(df, [{"from": a, "to": b, "reason": "prueba"}])
    assert len(out) == 110 and applied[0]["rows_removed"] == 10


def test_exclusion_removes_higher_timeframe_bar_that_contains_it():
    rates = make_rates(session_minutes()[:240])
    h1 = rates_to_frame(resample(rates, 3600))
    a = pd.Timestamp(int(rates["time"][70]), unit="s").isoformat()  # minuto dentro de la 2ª hora
    b = pd.Timestamp(int(rates["time"][71]), unit="s").isoformat()
    out, applied = apply_exclusions(h1, [{"from": a, "to": b, "reason": "tick erróneo"}], duration=3600)
    assert applied[0]["rows_removed"] == 1
    assert int(h1["time_raw"][1]) not in set(out["time_raw"])


# --- Informe completo y bloqueo -----------------------------------------------------

@pytest.fixture
def populated(tmp_path, cfg_b):
    rates = make_rates(session_minutes(MONDAY, 2))
    fake = FakeMT5(last_tick_time=int(rates["time"][-1]) + 45)
    fake.series = {FakeMT5.TIMEFRAME_M1: rates, FakeMT5.TIMEFRAME_M15: resample(rates, 900),
                   FakeMT5.TIMEFRAME_H1: resample(rates, 3600)}
    fake.tick_series = ticks_for(rates[-3000:])
    client = MT5Client(mt5=fake)
    client.connect()
    store = RawStore(tmp_path, "TestServer-Demo", "XAUUSD.t")
    for tf in cfg_b["timeframes"]:
        update_bars(client, store, cfg_b, tf)
    update_ticks(client, store, cfg_b, 2)
    return store


def test_quality_report_on_clean_data(populated, cfg_b):
    now = dt.datetime(2024, 2, 1, tzinfo=UTC)
    report = run_quality(populated, cfg_b, now)
    assert report["blocked"] == []
    for tf, section in report["timeframes"].items():
        assert section["status"] in ("OK", "INFO"), (tf, [c for c in section["checks"] if c["severity"] != "OK"])
    names = {c["name"]: c for c in report["cross_checks"]}
    assert names["resample_M15"]["metrics"]["mismatched"] == 0
    assert report["ticks"]["status"] in ("OK", "INFO")
    require_usable(report, ["M1", "M15", "H1"])


def test_corrupted_file_blocks_timeframe(populated, cfg_b):
    path = populated.bar_files("M1")[0]
    df = pd.read_parquet(path)
    df.loc[100, "high"] = df.loc[100, "low"] - 1
    df.to_parquet(path)
    report = run_quality(populated, cfg_b, dt.datetime(2024, 2, 1, tzinfo=UTC))
    assert report["blocked"] == ["M1"]
    with pytest.raises(DataBlockedError):
        require_usable(report, ["M15", "M1"])
    require_usable(report, ["M15"])


def test_unvalidated_timeframe_is_not_usable(populated, cfg_b):
    report = run_quality(populated, cfg_b, dt.datetime(2024, 2, 1, tzinfo=UTC))
    with pytest.raises(DataBlockedError):
        require_usable(report, ["M5"])
