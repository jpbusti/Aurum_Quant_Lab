import datetime as dt
import json

import numpy as np
import pyarrow.parquet as pq
import pytest

from aurum.data.ingest import trading_days, update_bars, update_ticks
from aurum.data.mt5_client import MT5Client, MT5Error
from aurum.data.storage import Manifest, RawStore, SourceMismatchError
from fake_mt5 import FakeMT5
from synthetic import MONDAY, make_rates, resample, session_minutes, ticks_for

UTC = dt.timezone.utc


def make_fake(rates, last_tick, ticks=None):
    fake = FakeMT5(last_tick_time=last_tick)
    fake.series = {
        FakeMT5.TIMEFRAME_M1: rates,
        FakeMT5.TIMEFRAME_M15: resample(rates, 900),
        FakeMT5.TIMEFRAME_H1: resample(rates, 3600),
    }
    fake.tick_series = ticks
    return fake


@pytest.fixture
def week():
    return make_rates(session_minutes(MONDAY, 1))


@pytest.fixture
def store(tmp_path):
    return RawStore(tmp_path, "TestServer-Demo", "XAUUSD.t")


def connected(fake):
    client = MT5Client(mt5=fake)
    client.connect()
    return client


def test_initial_download_keeps_only_closed_bars(week, store, cfg_b):
    cut = int(week["time"][1000])
    fake = make_fake(week[week["time"] <= cut], last_tick=cut + 30)  # barra `cut` aún abierta
    rec = update_bars(connected(fake), store, cfg_b, "M1")
    df = store.read_bars("M1")
    assert df["time_raw"].max() == cut - 60
    assert rec["dropped_unclosed"] == 1
    assert rec["new_rows"] == 1000 and len(df) == 1000


def test_provenance_in_manifest_and_parquet(week, store, cfg_b):
    fake = make_fake(week, last_tick=int(week["time"][-1]) + 120)
    update_bars(connected(fake), store, cfg_b, "M1")
    manifest = json.loads((store.bars_dir("M1") / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"]["server"] == "TestServer-Demo"
    rec = manifest["downloads"][0]
    for key in ("downloaded_at_utc", "symbol", "timeframe", "requested_from_raw", "requested_to_raw",
                "received_first_raw", "received_last_raw", "spec_hash", "terminal_build"):
        assert key in rec
    meta = json.loads(pq.read_schema(store.bar_files("M1")[0]).metadata[b"aurum"])
    assert meta["symbol"] == "XAUUSD.t" and "servidor" in meta["time_convention"]
    assert (store.base / "specs" / f"{rec['spec_hash']}.json").exists()


def test_incremental_update_does_not_duplicate(week, store, cfg_b):
    half = int(week["time"][3000])
    update_bars(connected(make_fake(week[week["time"] <= half], half + 60)), store, cfg_b, "M1")
    first_len = len(store.read_bars("M1"))
    rec = update_bars(connected(make_fake(week, int(week["time"][-1]) + 60)), store, cfg_b, "M1")
    df = store.read_bars("M1")
    assert df["time_raw"].is_unique and df["time_raw"].is_monotonic_increasing
    assert len(df) == len(week)
    assert rec["new_rows"] == len(week) - first_len
    assert rec["overlap_identical"] == 1 and rec["overlap_conflicts"] == 0
    # Una tercera ejecución sin datos nuevos no cambia nada.
    rec3 = update_bars(connected(make_fake(week, int(week["time"][-1]) + 60)), store, cfg_b, "M1")
    assert rec3["new_rows"] == 0 and len(store.read_bars("M1")) == len(week)


def test_revised_bar_is_recorded_as_conflict_not_overwritten(week, store, cfg_b):
    half = int(week["time"][3000])
    update_bars(connected(make_fake(week[week["time"] <= half], half + 60)), store, cfg_b, "M1")
    revised = week.copy()
    revised["close"][revised["time"] == half] += 1.0
    rec = update_bars(connected(make_fake(revised, int(week["time"][-1]) + 60)), store, cfg_b, "M1")
    assert rec["overlap_conflicts"] == 1
    stored = store.read_bars("M1").set_index("time_raw")
    assert stored.loc[half, "close"] == week["close"][week["time"] == half][0]


def test_small_chunks_do_not_create_duplicates(week, store, cfg_b):
    cfg_b["download"]["chunk_days"] = 1
    update_bars(connected(make_fake(week, int(week["time"][-1]) + 60)), store, cfg_b, "M1")
    df = store.read_bars("M1")
    assert df["time_raw"].is_unique and len(df) == len(week)


def test_transient_failure_is_retried(week, store, cfg_b):
    fake = make_fake(week, int(week["time"][-1]) + 60)
    fake.fail_next_calls = 1
    update_bars(connected(fake), store, cfg_b, "M1")
    assert len(store.read_bars("M1")) == len(week)


def test_persistent_failure_raises_and_writes_nothing(week, store, cfg_b):
    fake = make_fake(week, int(week["time"][-1]) + 60)
    fake.fail_next_calls = 99
    with pytest.raises(MT5Error):
        update_bars(connected(fake), store, cfg_b, "M1")
    assert store.read_bars("M1").empty


def test_wrong_server_or_real_account_is_refused(week, store, cfg_b):
    fake = make_fake(week, int(week["time"][-1]) + 60)
    fake.server = "Other-Demo"
    with pytest.raises(MT5Error):
        update_bars(connected(fake), store, cfg_b, "M1")
    fake = make_fake(week, int(week["time"][-1]) + 60)
    fake.trade_mode = 2
    with pytest.raises(MT5Error):
        update_bars(connected(fake), store, cfg_b, "M1")


def test_manifest_refuses_other_source(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.ensure_source({"kind": "bars", "server": "A", "symbol": "XAUUSD", "timeframe": "M1"})
    with pytest.raises(SourceMismatchError):
        m.ensure_source({"kind": "bars", "server": "B", "symbol": "XAUUSD", "timeframe": "M1"})


def test_history_starting_after_request_is_noted(week, store, cfg_b):
    cfg_b["download"]["bars_start"] = "2023-01-01"
    rec = update_bars(connected(make_fake(week, int(week["time"][-1]) + 60)), store, cfg_b, "M1")
    assert "note" in rec


def test_year_partitions(store, cfg_b):
    t = session_minutes(int(dt.datetime(2024, 12, 30, tzinfo=UTC).timestamp()), 1)  # cruza 2024 -> 2025
    rates = make_rates(t)
    update_bars(connected(make_fake(rates, int(t[-1]) + 60)), store, cfg_b, "M1")
    assert [p.name for p in store.bar_files("M1")] == ["2024.parquet", "2025.parquet"]


def test_trading_days_skip_weekends():
    days = trading_days(dt.date(2024, 1, 15), 3)  # lunes
    assert days == [dt.date(2024, 1, 11), dt.date(2024, 1, 12), dt.date(2024, 1, 15)]


def test_ticks_by_day_and_incomplete_last_day(week, store, cfg_b):
    ticks = ticks_for(week)
    last_tick = int(week["time"][-1]) + 45
    fake = make_fake(week, last_tick, ticks)
    rec = update_ticks(connected(fake), store, cfg_b, 5)
    assert [d["day"] for d in rec["days"]] == ["2024-01-08", "2024-01-09", "2024-01-10", "2024-01-11", "2024-01-12"]
    assert all(d["complete"] for d in rec["days"][:-1]) and not rec["days"][-1]["complete"]
    assert len(store.read_ticks()) == len(ticks)
    # Segunda ejecución: solo se vuelve a pedir el día incompleto.
    rec2 = update_ticks(connected(fake), store, cfg_b, 5)
    assert [d["day"] for d in rec2["days"]] == ["2024-01-12"]
    assert len(store.read_ticks()) == len(ticks)


def test_ticks_before_terminal_history_are_skipped(week, store, cfg_b):
    ticks = ticks_for(week)
    ticks = ticks[ticks["time"] >= MONDAY + 3 * 86400]  # el terminal solo tiene desde el jueves
    fake = make_fake(week, int(week["time"][-1]) + 45, ticks)
    rec = update_ticks(connected(fake), store, cfg_b, 5)
    skipped = [d["day"] for d in rec["days"] if "skipped" in d]
    assert skipped == ["2024-01-08", "2024-01-09", "2024-01-10"]
    assert np.array_equal(np.sort(store.read_ticks()["time_msc"].to_numpy()), np.sort(ticks["time_msc"]))
