"""Comprobaciones de integridad de datos de mercado.

Cada función recibe un DataFrame del almacén y devuelve un dict de comprobación:
    {"name", "severity", "summary", "metrics", "examples"}
con severity en OK | INFO | WARN | CRITICAL. Ninguna comprobación modifica ni
rellena los datos.

Todas las horas son del servidor del bróker (time_raw sin convertir).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd

from aurum.data.storage import BAR_COLUMNS, TICK_COLUMNS

SEVERITY_ORDER = {"OK": 0, "INFO": 1, "WARN": 2, "CRITICAL": 3}
MAX_EXAMPLES = 10
MIN_EPOCH = int(dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc).timestamp())


def check(name: str, severity: str, summary: str, metrics: dict | None = None, examples: list | None = None) -> dict:
    return {"name": name, "severity": severity, "summary": summary,
            "metrics": metrics or {}, "examples": (examples or [])[:MAX_EXAMPLES]}


def iso(epoch: int | float) -> str:
    return dt.datetime.fromtimestamp(int(epoch), dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


def _hhmm_to_min(text: str) -> int:
    h, m = text.split(":")
    return int(h) * 60 + int(m)


# --- Estructura -----------------------------------------------------------------

def check_schema(df: pd.DataFrame, expected: dict[str, str] = BAR_COLUMNS) -> dict:
    missing = [c for c in expected if c not in df.columns]
    wrong = {c: str(df[c].dtype) for c in expected if c in df.columns and str(df[c].dtype) != expected[c]}
    if missing or wrong:
        return check("schema", "CRITICAL", "columnas o tipos inesperados", {"missing": missing, "wrong_dtype": wrong})
    return check("schema", "OK", "columnas y tipos correctos")


def check_timestamps(times: np.ndarray, tf_seconds: int, now_epoch: int) -> dict:
    times = np.asarray(times, dtype=np.int64)
    diffs = np.diff(times)
    unsorted = int((diffs < 0).sum())
    dups = int(pd.Series(times).duplicated().sum())
    off_grid = int((times % tf_seconds != 0).sum())
    # Margen de 2 días por el desfase del servidor respecto a UTC.
    invalid = int(((times < MIN_EPOCH) | (times > now_epoch + 2 * 86400)).sum())
    metrics = {"unsorted": unsorted, "duplicates": dups, "off_grid": off_grid, "invalid_dates": invalid}
    if any(metrics.values()):
        return check("timestamps", "CRITICAL", "orden, duplicados, rejilla o fechas inválidas", metrics)
    return check("timestamps", "OK", "ordenadas, únicas, en la rejilla del timeframe y en rango", metrics)


def check_prices(df: pd.DataFrame) -> dict:
    o, h, lo, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    prices = np.column_stack([o, h, lo, c])
    missing = int(np.isnan(prices).any(axis=1).sum())
    non_finite = int((~np.isfinite(prices)).any(axis=1).sum())
    non_positive = int((prices <= 0).any(axis=1).sum())
    incoherent = (h < np.maximum(o, c)) | (lo > np.minimum(o, c)) | (h < lo)
    metrics = {"missing": missing, "non_finite": non_finite, "non_positive": non_positive,
               "ohlc_incoherent": int(incoherent.sum())}
    examples = [{"time": iso(t), "ohlc": [float(x) for x in row]}
                for t, row in zip(df["time_raw"].to_numpy()[incoherent], prices[incoherent])]
    if any(metrics.values()):
        return check("prices", "CRITICAL", "precios ausentes, no finitos, no positivos u OHLC incoherentes",
                     metrics, examples)
    return check("prices", "OK", "OHLC coherentes, positivos y finitos", metrics)


# --- Huecos y sesiones ----------------------------------------------------------

def classify_gaps(times: np.ndarray, tf_seconds: int, sessions: dict[str, Any]) -> pd.DataFrame:
    """Clasifica cada hueco según el calendario del servidor.

    Clases: weekend, daily_break, early_close, holiday, unexplained.
    Un hueco no explicado no se rellena: solo se reporta.
    """
    times = np.asarray(times, dtype=np.int64)
    d = np.diff(times)
    idx = np.where(d > tf_seconds)[0]
    start = times[idx] + tf_seconds          # primera barra ausente
    end = times[idx + 1]                       # siguiente barra existente
    minutes = (end - start) // 60
    open_min = _hhmm_to_min(sessions["daily_open"])
    e_min = (end % 86400) // 60
    at_open = (e_min >= open_min) & (e_min <= open_min + sessions["open_tolerance_min"])
    # Contiene un sábado a mediodía: cierre de fin de semana. El epoch 0 fue jueves,
    # así que weekday = (días + 3) % 7 con lunes = 0.
    s_day = start // 86400
    days_to_sat = (5 - (s_day + 3) % 7) % 7
    sat_noon = (s_day + days_to_sat) * 86400 + 12 * 3600
    weekend = (sat_noon >= start) & (sat_noon < end)
    cls = np.full(len(idx), "unexplained", dtype=object)
    cls[at_open & (minutes > sessions["early_close_max_hours"] * 60)] = "holiday"
    cls[at_open & (minutes <= sessions["early_close_max_hours"] * 60)] = "early_close"
    cls[at_open & (minutes <= sessions["daily_break_max_min"])] = "daily_break"
    cls[weekend] = "weekend"
    return pd.DataFrame({"start": start, "end": end, "minutes": minutes, "kind": cls,
                         "end_at_open": np.asarray(at_open)})


def check_gaps(times: np.ndarray, tf_seconds: int, sessions: dict[str, Any], warn_min: int) -> dict:
    gaps = classify_gaps(times, tf_seconds, sessions)
    counts = gaps["kind"].value_counts().to_dict()
    unexplained = gaps[gaps["kind"] == "unexplained"]
    long_unexp = unexplained[unexplained["minutes"] >= warn_min]
    metrics = {
        "gaps_total": int(len(gaps)),
        "by_kind": {k: int(v) for k, v in counts.items()},
        "unexplained_short": int(len(unexplained) - len(long_unexp)),
        "unexplained_long": int(len(long_unexp)),
        "unexplained_missing_minutes": int(unexplained["minutes"].sum()),
        "weekend_not_reopening_at_daily_open": int((~gaps.loc[gaps["kind"] == "weekend", "end_at_open"]).sum()),
    }
    examples = [{"from": iso(r.start), "to": iso(r.end), "minutes": int(r.minutes)}
                for r in long_unexp.sort_values("minutes", ascending=False).itertuples()]
    severity = "WARN" if len(long_unexp) or metrics["weekend_not_reopening_at_daily_open"] else "OK"
    summary = (f"{len(gaps)} huecos; {len(unexplained)} sin explicar por el calendario "
               f"({len(long_unexp)} de {warn_min} min o más)")
    return check("gaps", severity, summary, metrics, examples)


def weekly_open_times(times: np.ndarray, tf_seconds: int, sessions: dict[str, Any]) -> pd.Series:
    """Hora (HH:MM servidor) de la primera barra tras cada fin de semana."""
    gaps = classify_gaps(times, tf_seconds, sessions)
    ends = pd.to_datetime(gaps.loc[gaps["kind"] == "weekend", "end"], unit="s")
    return ends.dt.strftime("%H:%M")


# --- Saltos de precio -----------------------------------------------------------

def check_returns(df: pd.DataFrame, tf_seconds: int, k: float) -> dict:
    """Retornos cierre a cierre entre barras consecutivas (sin hueco) muy alejados de lo habitual.

    Escala robusta por año: 1.4826 * MAD. Un salto anómalo puede ser real (noticias):
    se reporta como aviso para revisión, no se elimina.
    """
    t = df["time_raw"].to_numpy()
    c = df["close"].to_numpy()
    if len(t) < 3:
        return check("returns", "INFO", "muy pocas barras para evaluar saltos")
    consecutive = np.diff(t) == tf_seconds
    r = np.log(c[1:] / c[:-1])
    years = pd.to_datetime(t[1:], unit="s").year.to_numpy()
    flagged_idx = []
    scales = {}
    for y in np.unique(years):
        m = (years == y) & consecutive
        if m.sum() < 100:
            continue
        ry = r[m]
        scale = 1.4826 * np.median(np.abs(ry - np.median(ry)))
        scales[int(y)] = float(scale)
        if scale == 0:
            continue
        hits = np.where(m & (np.abs(r) > k * scale))[0]
        flagged_idx.extend((i, abs(r[i]) / scale) for i in hits)
    flagged_idx.sort(key=lambda x: -x[1])
    examples = [{"time": iso(t[i + 1]), "log_return": round(float(r[i]), 5), "robust_z": round(z, 1)}
                for i, z in flagged_idx]
    metrics = {"flagged": len(flagged_idx), "k": k, "robust_scale_by_year": scales}
    severity = "WARN" if flagged_idx else "OK"
    return check("returns", severity, f"{len(flagged_idx)} retornos con |r| > {k} escalas robustas", metrics, examples)


def check_spread_field(df: pd.DataFrame) -> dict:
    s = df["spread"].to_numpy()
    if len(s) == 0:
        return check("spread_field", "INFO", "sin barras")
    metrics = {"zero_fraction": round(float((s == 0).mean()), 6),
               "p50": float(np.percentile(s, 50)), "p99": float(np.percentile(s, 99)),
               "p999": float(np.percentile(s, 99.9)), "max": int(s.max()), "negative": int((s < 0).sum())}
    sev = "CRITICAL" if metrics["negative"] else "INFO"
    return check("spread_field", sev,
                 "campo spread de las barras (puntos); no se usa como coste sin calibrar con ticks", metrics)


# --- Archivos -------------------------------------------------------------------

def check_file_overlaps(df_with_file: pd.DataFrame) -> dict:
    """Cada archivo anual debe contener solo su año y ninguna marca puede estar en dos archivos."""
    if df_with_file.empty:
        return check("file_overlaps", "OK", "sin archivos")
    years = pd.to_datetime(df_with_file["time_raw"], unit="s").dt.year.astype(str)
    wrong_year = int((years + ".parquet" != df_with_file["_file"]).sum())
    cross = df_with_file.groupby("time_raw")["_file"].nunique()
    in_two = int((cross > 1).sum())
    metrics = {"rows_in_wrong_year_file": wrong_year, "timestamps_in_several_files": in_two,
               "files": int(df_with_file["_file"].nunique())}
    if wrong_year or in_two:
        return check("file_overlaps", "CRITICAL", "solapamiento entre archivos", metrics)
    return check("file_overlaps", "OK", "archivos anuales sin solapamientos", metrics)


# --- Coherencia entre timeframes --------------------------------------------------

def resample_from_m1(m1: pd.DataFrame, tf_seconds: int) -> pd.DataFrame:
    bucket = m1["time_raw"] - m1["time_raw"] % tf_seconds
    g = m1.groupby(bucket, sort=True)
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "m1_bars": g.size(),
    })
    out.index.name = "time_raw"
    return out.reset_index()


def check_resample(m1: pd.DataFrame, native: pd.DataFrame, tf_seconds: int, tol: float, warn_frac: float,
                   name: str) -> dict:
    """Compara un timeframe nativo con el reconstruido desde M1 en el periodo común."""
    if m1.empty or native.empty:
        return check(f"resample_{name}", "INFO", "sin datos para comparar")
    lo = max(int(m1["time_raw"].min()), int(native["time_raw"].min()))
    hi = min(int(m1["time_raw"].max()), int(native["time_raw"].max()))
    bucket = m1["time_raw"] - m1["time_raw"] % tf_seconds
    rs = resample_from_m1(m1[(bucket >= lo) & (bucket <= hi)], tf_seconds)
    nat = native[(native["time_raw"] >= lo) & (native["time_raw"] <= hi)]
    j = nat.merge(rs, on="time_raw", how="outer", suffixes=("", "_m1"), indicator=True)
    both = j[j["_merge"] == "both"]
    diff = np.zeros(len(both), dtype=bool)
    for c in ("open", "high", "low", "close"):
        diff |= np.abs(both[c].to_numpy() - both[f"{c}_m1"].to_numpy()) > tol
    frac = float(diff.mean()) if len(both) else 0.0
    metrics = {
        "compared": int(len(both)), "mismatched": int(diff.sum()), "mismatch_fraction": round(frac, 6),
        "native_without_m1": int((j["_merge"] == "left_only").sum()),
        "m1_without_native": int((j["_merge"] == "right_only").sum()),
        "period": [iso(lo), iso(hi)],
    }
    examples = [{"time": iso(r["time_raw"]),
                 "native": [r["open"], r["high"], r["low"], r["close"]],
                 "from_m1": [r["open_m1"], r["high_m1"], r["low_m1"], r["close_m1"]]}
                for r in both[diff].head(MAX_EXAMPLES).to_dict("records")]
    severity = "WARN" if frac > warn_frac or metrics["native_without_m1"] or metrics["m1_without_native"] else "OK"
    return check(f"resample_{name}", severity,
                 f"{name} nativo frente a reconstruido desde M1: {frac:.4%} barras distintas", metrics, examples)


# --- Barras frente a ticks ------------------------------------------------------

def ticks_per_minute(ticks: pd.DataFrame, point: float) -> pd.DataFrame:
    """Resume ticks por minuto (bid OHLC y spread en puntos). Se aplica día a día para no
    cargar meses de ticks en memoria."""
    sec = ticks["time_msc"] // 1000
    minute = sec - sec % 60
    g = ticks.groupby(minute)
    spread = (ticks["ask"] - ticks["bid"]).groupby(minute)
    tk = pd.DataFrame({"bid_open": g["bid"].first(), "bid_high": g["bid"].max(), "bid_low": g["bid"].min(),
                       "bid_close": g["bid"].last(), "ticks": g.size(),
                       "spread_min_pts": (spread.min() / point).round(),
                       "spread_mean_pts": spread.mean() / point})
    tk.index.name = "time_raw"
    return tk.reset_index()


def check_bars_vs_ticks(m1: pd.DataFrame, minutes: pd.DataFrame) -> dict:
    """Compara las barras M1 (construidas con bid) con los ticks del mismo minuto."""
    if minutes.empty or m1.empty:
        return check("bars_vs_ticks", "INFO", "sin ticks para comparar")
    lo, hi = int(minutes["time_raw"].min()), int(minutes["time_raw"].max())
    bars = m1[(m1["time_raw"] >= lo) & (m1["time_raw"] <= hi)]
    j = bars.merge(minutes, on="time_raw", how="outer", indicator=True)
    both = j[j["_merge"] == "both"]
    tol = 0.005
    hi_ok = np.abs(both["high"] - both["bid_high"]) <= tol
    lo_ok = np.abs(both["low"] - both["bid_low"]) <= tol
    metrics = {
        "minutes_compared": int(len(both)),
        "high_match_fraction": round(float(hi_ok.mean()), 6),
        "low_match_fraction": round(float(lo_ok.mean()), 6),
        "minutes_with_ticks_no_bar": int((j["_merge"] == "right_only").sum()),
        "bars_without_ticks": int((j["_merge"] == "left_only").sum()),
        "bar_spread_equals_tick_min_spread": round(float((both["spread"] == both["spread_min_pts"]).mean()), 6),
        "tick_spread_mean_pts_p50": round(float(both["spread_mean_pts"].median()), 2),
        "bar_spread_p50": float(both["spread"].median()),
        "period": [iso(lo), iso(hi)],
    }
    severity = "WARN" if min(metrics["high_match_fraction"], metrics["low_match_fraction"]) < 0.99 else "OK"
    return check("bars_vs_ticks", severity, "barras M1 frente a ticks bid del mismo minuto", metrics)


TICK_INTEGRITY_KEYS = ("rows", "unsorted", "bid_or_ask_not_positive_or_nan", "ask_below_bid", "exact_duplicates")


def tick_integrity_metrics(ticks: pd.DataFrame) -> dict[str, int]:
    t = ticks["time_msc"].to_numpy()
    bid, ask = ticks["bid"].to_numpy(), ticks["ask"].to_numpy()
    return {
        "rows": int(len(ticks)),
        "unsorted": int((np.diff(t) < 0).sum()),
        "bid_or_ask_not_positive_or_nan": int(((bid <= 0) | (ask <= 0) | np.isnan(bid) | np.isnan(ask)).sum()),
        "ask_below_bid": int((ask < bid).sum()),
        "exact_duplicates": int(ticks.duplicated().sum()),
    }


def check_tick_metrics(metrics: dict[str, int]) -> dict:
    if not metrics.get("rows"):
        return check("ticks", "INFO", "sin ticks descargados")
    bad = metrics["unsorted"] or metrics["bid_or_ask_not_positive_or_nan"] or metrics["ask_below_bid"]
    return check("ticks", "CRITICAL" if bad else "OK", "integridad de ticks bid/ask", metrics)


def check_ticks(ticks: pd.DataFrame) -> dict:
    if ticks.empty:
        return check("ticks", "INFO", "sin ticks descargados")
    return check_tick_metrics(tick_integrity_metrics(ticks))


# --- Procedencia ----------------------------------------------------------------

VOLATILE_SPEC_FIELDS = {"swap_long", "swap_short"}


def check_provenance(manifest: dict[str, Any], specs: dict[str, dict[str, Any]]) -> dict:
    downloads = manifest.get("downloads", [])
    if not downloads:
        return check("provenance", "CRITICAL", "sin registro de descargas")
    keys = ("server", "company", "symbol", "account_trade_mode")
    sources = {tuple(d.get(k) for k in keys) for d in downloads}
    hashes = list(dict.fromkeys(d["spec_hash"] for d in downloads))
    changes = []
    for a, b in zip(hashes, hashes[1:]):
        sa, sb = specs.get(a, {}), specs.get(b, {})
        changed = sorted(k for k in set(sa) | set(sb) if sa.get(k) != sb.get(k))
        changes.append({"from": a, "to": b, "fields": changed})
    structural = [c for c in changes if set(c["fields"]) - VOLATILE_SPEC_FIELDS]
    metrics = {"downloads": len(downloads), "distinct_sources": len(sources), "spec_versions": len(hashes),
               "conflicts_recorded": int(sum(d.get("overlap_conflicts", 0) for d in downloads)),
               "chunk_clashes": int(sum(d.get("chunk_clashes", 0) for d in downloads))}
    if len(sources) > 1:
        return check("provenance", "CRITICAL", "el conjunto mezcla fuentes", metrics, [list(s) for s in sources])
    if structural or metrics["conflicts_recorded"] or metrics["chunk_clashes"]:
        return check("provenance", "WARN", "cambios de especificación o conflictos de re-descarga", metrics, changes)
    sev = "INFO" if changes else "OK"
    return check("provenance", sev, "una sola fuente" + ("; cambió el swap" if changes else ""), metrics, changes)
