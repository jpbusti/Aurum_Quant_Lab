"""Fase B: descarga incremental de barras y ticks desde MT5 al almacén Parquet.

Reglas:
- Solo se guardan barras cerradas: una barra con hora de apertura t se guarda si
  t + duración <= hora del último tick. La barra en formación se descarta y se
  descargará en la siguiente ejecución.
- Las barras ya guardadas no se sobrescriben. Si el servidor devuelve otra versión
  de una barra existente, se registra como conflicto en el manifiesto.
- Cada descarga deja una entrada en el manifiesto con fuente, rango, filas y hash
  de las especificaciones del símbolo en ese momento.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import numpy as np
import pandas as pd

from aurum.data.mt5_client import TIMEFRAME_SECONDS, UTC, MT5Client, MT5Error
from aurum.data.storage import BAR_COLUMNS, RawStore, rates_to_frame, ticks_to_frame
from aurum.environment import check_source

log = logging.getLogger(__name__)
VALUE_COLUMNS = [c for c in BAR_COLUMNS if c != "time_raw"]
MAX_CONFLICT_EXAMPLES = 20


def _dt(epoch: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(int(epoch), UTC)


def _epoch(day: str | dt.date) -> int:
    d = dt.date.fromisoformat(day) if isinstance(day, str) else day
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())


def source_info(client: MT5Client, cfg: dict[str, Any], kind: str, timeframe: str | None = None) -> dict[str, Any]:
    """Identifica la fuente y se niega a continuar si no es la configurada."""
    account = client.account_info_safe()
    critical = [i for i in check_source(account, cfg["source"]) if i.startswith("CRITICAL")]
    if critical:
        raise MT5Error("; ".join(critical))
    terminal = client.terminal_info()
    return {
        "kind": kind,
        "server": account["server"],
        "company": account["company"],
        "account_trade_mode": account["trade_mode"],
        "symbol": cfg["symbol"]["name"],
        "timeframe": timeframe,
        "terminal_build": terminal["build"],
        "mt5_package": client.package_version(),
    }


def compare_overlap(stored: pd.DataFrame, fetched: pd.DataFrame) -> tuple[int, list[dict[str, Any]]]:
    """Compara barras re-descargadas con las guardadas. Devuelve (idénticas, conflictos)."""
    merged = stored.merge(fetched, on="time_raw", suffixes=("_old", "_new"))
    if merged.empty:
        return 0, []
    diff = np.zeros(len(merged), dtype=bool)
    for c in VALUE_COLUMNS:
        diff |= merged[f"{c}_old"].to_numpy() != merged[f"{c}_new"].to_numpy()
    conflicts = []
    for row in merged[diff].to_dict("records"):
        conflicts.append({
            "time_raw": int(row["time_raw"]),
            "old": {c: row[f"{c}_old"] for c in VALUE_COLUMNS},
            "new": {c: row[f"{c}_new"] for c in VALUE_COLUMNS},
        })
    return int((~diff).sum()), conflicts


def fetch_bars(client: MT5Client, symbol: str, timeframe: str, start: int, end: int,
               chunk_days: int, retries: int, wait_s: float) -> tuple[pd.DataFrame, int]:
    """Descarga [start, end] por bloques. Devuelve barras únicas y conflictos entre bloques."""
    frames = []
    step = chunk_days * 86400
    a = start
    while a <= end:
        b = min(a + step, end)
        rates = client.retrying(lambda a=a, b=b: client.rates(symbol, timeframe, _dt(a), _dt(b)), retries, wait_s)
        frames.append(rates_to_frame(rates))
        a = b + 1
    df = pd.concat(frames, ignore_index=True) if frames else rates_to_frame(None)
    df = df.sort_values("time_raw", kind="stable")
    exact = df.duplicated()
    df = df[~exact]
    clashing = int(df["time_raw"].duplicated().sum())
    df = df.drop_duplicates("time_raw", keep="first").reset_index(drop=True)
    return df, clashing


def update_bars(client: MT5Client, store: RawStore, cfg: dict[str, Any], timeframe: str,
                now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(UTC)
    dl = cfg["download"]
    symbol = cfg["symbol"]["name"]
    tf_s = TIMEFRAME_SECONDS[timeframe]
    source = source_info(client, cfg, "bars", timeframe)
    manifest = store.bars_manifest(timeframe)
    manifest.ensure_source(source)
    spec_h = store.save_spec(client.symbol_spec(symbol))

    last_tick = int(client.last_tick(symbol)["time"])
    last_stored = store.last_bar_time(timeframe)
    start = last_stored if last_stored is not None else _epoch(dl["bars_start"])
    end = last_tick + tf_s
    fetched, clashing = fetch_bars(client, symbol, timeframe, start, end,
                                   dl["chunk_days"], dl["retries"], dl["retry_wait_s"])

    closed_mask = fetched["time_raw"] + tf_s <= last_tick
    unclosed = int((~closed_mask).sum())
    closed = fetched[closed_mask]

    identical, conflicts = 0, []
    if last_stored is not None:
        overlap = closed[closed["time_raw"] <= last_stored]
        if not overlap.empty:
            stored = store.read_bars(timeframe)
            stored = stored[stored["time_raw"] >= int(overlap["time_raw"].min())]
            identical, conflicts = compare_overlap(stored, overlap)
        fresh = closed[closed["time_raw"] > last_stored]
    else:
        fresh = closed
    store.append_bars(timeframe, fresh.reset_index(drop=True), source)

    record = {
        **source,
        "downloaded_at_utc": now.isoformat(),
        "spec_hash": spec_h,
        "requested_from_raw": start,
        "requested_to_raw": end,
        "last_tick_raw": last_tick,
        "received": int(len(fetched)),
        "received_first_raw": int(fetched["time_raw"].min()) if len(fetched) else None,
        "received_last_raw": int(fetched["time_raw"].max()) if len(fetched) else None,
        "new_rows": int(len(fresh)),
        "overlap_identical": identical,
        "overlap_conflicts": len(conflicts),
        "conflict_examples": conflicts[:MAX_CONFLICT_EXAMPLES],
        "chunk_clashes": clashing,
        "dropped_unclosed": unclosed,
    }
    if last_stored is None and len(fetched) and int(fetched["time_raw"].min()) > start + 7 * 86400:
        record["note"] = "el historial del servidor empieza después de la fecha pedida"
    if conflicts:
        log.warning("%s %s: %d barras re-descargadas difieren de las guardadas", symbol, timeframe, len(conflicts))
    manifest.append(record)
    return record


def trading_days(last_day: dt.date, n: int) -> list[dt.date]:
    """Los n últimos días laborables (lunes-viernes, calendario del servidor) hasta last_day."""
    days, d = [], last_day
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= dt.timedelta(days=1)
    return sorted(days)


def update_ticks(client: MT5Client, store: RawStore, cfg: dict[str, Any], n_days: int,
                 now: dt.datetime | None = None) -> dict[str, Any]:
    """Descarga ticks bid/ask por día. Un día ya completo no se vuelve a pedir."""
    now = now or dt.datetime.now(UTC)
    dl = cfg["download"]
    symbol = cfg["symbol"]["name"]
    source = source_info(client, cfg, "ticks")
    manifest = store.ticks_manifest()
    manifest.ensure_source(source)
    spec_h = store.save_spec(client.symbol_spec(symbol))
    known_days: dict[str, Any] = manifest.data.setdefault("days", {})

    last_tick = int(client.last_tick(symbol)["time"])
    last_day = _dt(last_tick).date()
    first = client.first_tick(symbol, dt.datetime(2000, 1, 1, tzinfo=UTC))
    first_day = _dt(first["time"]).date() if first else None

    done = []
    for day in trading_days(last_day, n_days):
        if first_day is None or day < first_day:
            done.append({"day": day.isoformat(), "rows": 0, "skipped": "fuera del historial de ticks del terminal"})
            continue
        if known_days.get(day.isoformat(), {}).get("complete"):
            continue
        a = _epoch(day)
        b = a + 86400
        raw = client.retrying(lambda a=a, b=b: client.ticks(symbol, _dt(a), _dt(b)), dl["retries"], dl["retry_wait_s"])
        ticks = ticks_to_frame(raw)
        ticks = ticks[ticks["time_msc"] < b * 1000].reset_index(drop=True)
        store.write_ticks(day, ticks, source)
        entry = {
            "rows": int(len(ticks)),
            "first_msc": int(ticks["time_msc"].min()) if len(ticks) else None,
            "last_msc": int(ticks["time_msc"].max()) if len(ticks) else None,
            # El día del último tick puede estar incompleto (mercado abierto o cierre del viernes).
            "complete": day < last_day,
            "downloaded_at_utc": now.isoformat(),
        }
        known_days[day.isoformat()] = entry
        done.append({"day": day.isoformat(), **entry})

    record = {**source, "downloaded_at_utc": now.isoformat(), "spec_hash": spec_h,
              "last_tick_raw": last_tick, "first_tick_day": first_day.isoformat() if first_day else None,
              "days": done}
    manifest.append(record)
    return record
