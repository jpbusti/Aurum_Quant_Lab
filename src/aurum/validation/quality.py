"""Informe de calidad de datos y bloqueo de experimentos.

Un timeframe con alguna comprobación CRITICAL queda bloqueado. require_usable()
es la puerta que deben cruzar las fases siguientes antes de usar datos.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pandas as pd

from aurum.data.mt5_client import TIMEFRAME_SECONDS, UTC
from aurum.data.storage import TICK_COLUMNS, RawStore
from aurum.validation import checks as C


class DataBlockedError(RuntimeError):
    """Los datos pedidos tienen fallos críticos sin resolver."""


def _worst(items: list[dict[str, Any]]) -> str:
    return max((c["severity"] for c in items), key=C.SEVERITY_ORDER.__getitem__, default="OK")


def apply_exclusions(df: pd.DataFrame, exclusions: list[dict[str, str]], time_col: str = "time_raw",
                     scale: int = 1, duration: int = 0) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Quita rangos excluidos de forma justificada (hora del servidor, ISO). Cada uno exige motivo.

    Se elimina toda barra cuyo intervalo [t, t + duration) toque el rango, de modo que
    una exclusión afecta por igual a M1 y a la barra H1 que la contiene.
    """
    applied = []
    for ex in exclusions:
        if not ex.get("reason"):
            raise ValueError(f"exclusión sin motivo: {ex}")
        a = int(pd.Timestamp(ex["from"], tz="UTC").timestamp()) * scale
        b = int(pd.Timestamp(ex["to"], tz="UTC").timestamp()) * scale
        end_of_row = df[time_col] + duration * scale if duration else df[time_col] + 1
        mask = (end_of_row > a) & (df[time_col] < b)
        applied.append({**ex, "rows_removed": int(mask.sum())})
        df = df[~mask]
    return df.reset_index(drop=True), applied


def validate_bars(store: RawStore, cfg: dict[str, Any], timeframe: str, now: dt.datetime) -> tuple[dict, pd.DataFrame]:
    v, sessions = cfg["validation"], cfg["sessions"]
    tf_s = TIMEFRAME_SECONDS[timeframe]
    raw = store.read_bars(timeframe, with_file=True)
    results = [C.check_file_overlaps(raw)]
    df, exclusions = apply_exclusions(raw.drop(columns="_file"), v["exclusions"], duration=tf_s)
    manifest = store.bars_manifest(timeframe).data
    results.append(C.check_provenance(manifest, store.load_specs()))
    results.append(C.check_schema(df))
    if df.empty:
        results.append(C.check("data", "CRITICAL", "no hay barras descargadas"))
    else:
        times = df["time_raw"].to_numpy()
        results += [
            C.check_timestamps(times, tf_s, int(now.timestamp())),
            C.check_prices(df),
            C.check_gaps(times, tf_s, sessions, v["unexplained_gap_warn_min"]),
            C.check_returns(df, tf_s, v["return_mad_k"]),
            C.check_spread_field(df),
        ]
        opens = C.weekly_open_times(times, tf_s, sessions).value_counts().head(5).to_dict()
        results.append(C.check("weekly_open", "INFO", "hora de la primera barra de cada semana (servidor)",
                               {"most_common": opens}))
    section = {
        "timeframe": timeframe,
        "rows": int(len(df)),
        "first": C.iso(df["time_raw"].min()) if len(df) else None,
        "last": C.iso(df["time_raw"].max()) if len(df) else None,
        "exclusions": exclusions,
        "checks": results,
    }
    section["status"] = _worst(results)
    section["blocked"] = section["status"] == "CRITICAL"
    return section, df


def run_quality(store: RawStore, cfg: dict[str, Any], now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(UTC)
    v = cfg["validation"]
    report: dict[str, Any] = {
        "generated_at_utc": now.isoformat(),
        "server": store.server, "symbol": store.symbol,
        "time_convention": "hora del servidor (time_raw), sin convertir a UTC",
        "timeframes": {}, "cross_checks": [],
    }
    frames = {}
    for tf in cfg["timeframes"]:
        section, df = validate_bars(store, cfg, tf, now)
        report["timeframes"][tf] = section
        frames[tf] = df

    m1 = frames.get("M1")
    if m1 is not None and not m1.empty:
        for tf in cfg["timeframes"]:
            if tf != "M1" and not frames[tf].empty:
                report["cross_checks"].append(C.check_resample(
                    m1, frames[tf], TIMEFRAME_SECONDS[tf], v["resample_tolerance"], v["resample_mismatch_warn"], tf))

    # Ticks día a día: meses de ticks no caben con holgura en memoria.
    point = next(iter(store.load_specs().values()), {}).get("point", 0.01)
    totals = dict.fromkeys(C.TICK_INTEGRITY_KEYS, 0)
    minutes, prev_last = [], None
    for day in store.tick_days():
        ticks = store.read_ticks(day, day)
        ticks, _ = apply_exclusions(ticks, v["exclusions"], "time_msc", 1000)
        if ticks.empty:
            continue
        for k, val in C.tick_integrity_metrics(ticks[list(TICK_COLUMNS)]).items():
            totals[k] += val
        if prev_last is not None and int(ticks["time_msc"].iloc[0]) < prev_last:
            totals["unsorted"] += 1
        prev_last = int(ticks["time_msc"].iloc[-1])
        minutes.append(C.ticks_per_minute(ticks, point))
    tick_checks = [C.check_tick_metrics(totals)]
    if store.ticks_manifest().data.get("downloads"):
        tick_checks.append(C.check_provenance(store.ticks_manifest().data, store.load_specs()))
    if m1 is not None and minutes:
        tick_checks.append(C.check_bars_vs_ticks(m1, pd.concat(minutes, ignore_index=True)))
    report["ticks"] = {"checks": tick_checks, "status": _worst(tick_checks),
                       "blocked": _worst(tick_checks) == "CRITICAL"}

    statuses = [s["status"] for s in report["timeframes"].values()] + [report["ticks"]["status"]]
    statuses += [c["severity"] for c in report["cross_checks"]]
    report["status"] = max(statuses, key=C.SEVERITY_ORDER.__getitem__)
    report["blocked"] = sorted([tf for tf, s in report["timeframes"].items() if s["blocked"]]
                               + (["ticks"] if report["ticks"]["blocked"] else []))
    return report


def write_quality_report(report: dict[str, Any], out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["generated_at_utc"][:19].replace(":", "").replace("-", "")
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    path = out_dir / f"quality_{stamp}Z.json"
    path.write_text(text, encoding="utf-8")
    (out_dir / "latest.json").write_text(text, encoding="utf-8")
    return path


def require_usable(report_or_path: dict[str, Any] | str | Path, timeframes: list[str]) -> None:
    """Puerta de las fases C en adelante: falla si algún timeframe pedido está bloqueado o sin validar."""
    if isinstance(report_or_path, (str, Path)):
        report = json.loads(Path(report_or_path).read_text(encoding="utf-8"))
    else:
        report = report_or_path
    missing = [tf for tf in timeframes if tf not in report["timeframes"]]
    blocked = [tf for tf in timeframes if tf in report["blocked"]]
    if missing or blocked:
        raise DataBlockedError(f"datos no utilizables: bloqueados {blocked}, sin validar {missing}")
