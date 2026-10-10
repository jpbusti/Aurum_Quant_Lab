"""Fase A: inspección del entorno y del terminal MT5.

Produce un informe JSON con lo que el terminal reporta realmente. Si algo no se
puede consultar, el informe lo dice; nunca se rellena con valores supuestos.
"""

from __future__ import annotations

import datetime as dt
import importlib.metadata
import json
import platform
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from aurum.data.mt5_client import TIMEFRAME_SECONDS, UTC, MT5Client, MT5Error

PACKAGES = ("MetaTrader5", "numpy", "PyYAML", "pandas", "pyarrow", "pytest")
HISTORY_START = dt.datetime(2000, 1, 1, tzinfo=UTC)
# Un mes cuenta como "denso" si la separación mediana entre barras es exactamente
# el timeframe y tiene al menos este número de barras.
DENSE_MIN_BARS = 100


def utc_iso(epoch: int | float | None) -> str | None:
    if epoch is None:
        return None
    return dt.datetime.fromtimestamp(int(epoch), UTC).isoformat()


def package_versions() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = None
    return out


def select_gold_symbol(symbols: list[dict[str, Any]], cfg_symbol: dict[str, Any]) -> dict[str, Any]:
    """Identifica el símbolo de oro sin suponer su nombre.

    Candidatos: símbolos no personalizados con la divisa base y de beneficio de la
    configuración. Solo se selecciona el nombre configurado si está entre los
    candidatos; en otro caso se informa y no se elige nada.
    """
    base, profit = cfg_symbol["currency_base"], cfg_symbol["currency_profit"]
    candidates = sorted(
        s["name"] for s in symbols
        if not s.get("custom") and s.get("currency_base") == base and s.get("currency_profit") == profit
    )
    wanted = cfg_symbol.get("name")
    issues: list[str] = []
    selected = None
    if not candidates:
        issues.append(f"CRITICAL: ningún símbolo con base {base} y beneficio {profit}")
    elif wanted in candidates:
        selected = wanted
        if len(candidates) > 1:
            issues.append(f"WARN: varios candidatos {candidates}; se usa el configurado {wanted}")
    elif wanted:
        issues.append(f"CRITICAL: el símbolo configurado {wanted} no existe; candidatos: {candidates}")
    else:
        issues.append(f"CRITICAL: symbol.name vacío en configs/data.yaml; candidatos: {candidates}")
    return {"selected": selected, "candidates": candidates, "issues": issues}


def check_source(account: dict[str, Any], cfg_source: dict[str, Any]) -> list[str]:
    issues = []
    if account.get("trade_mode") != cfg_source["account_trade_mode"]:
        issues.append(
            f"CRITICAL: la cuenta es {account.get('trade_mode')}, se esperaba {cfg_source['account_trade_mode']}"
        )
    if account.get("server") != cfg_source["server"]:
        issues.append(f"CRITICAL: servidor {account.get('server')!r}, se esperaba {cfg_source['server']!r}")
    return issues


def summarize_bar_times(times: np.ndarray, tf_seconds: int) -> dict[str, Any]:
    """Resume la cobertura de un historial de barras.

    first_dense_month separa el historial utilizable de los registros dispersos
    (por ejemplo, una barra por día etiquetada como M1) que algunos servidores
    devuelven para fechas antiguas.
    """
    times = np.asarray(times, dtype=np.int64)
    if times.size == 0:
        return {"bars": 0, "first": None, "last": None, "bars_per_year": {}, "first_dense_month": None}
    stamps = [dt.datetime.fromtimestamp(int(t), UTC) for t in times]
    per_year = Counter(s.year for s in stamps)
    months: dict[str, list[int]] = {}
    for s, t in zip(stamps, times):
        months.setdefault(f"{s.year:04d}-{s.month:02d}", []).append(int(t))
    first_dense = None
    for month in sorted(months):
        ts = months[month]
        if len(ts) >= DENSE_MIN_BARS and int(np.median(np.diff(ts))) == tf_seconds:
            first_dense = month
            break
    diffs = np.diff(times)
    return {
        "bars": int(times.size),
        "first": utc_iso(times[0]),
        "last": utc_iso(times[-1]),
        "bars_per_year": {str(y): per_year[y] for y in sorted(per_year)},
        "first_dense_month": first_dense,
        "sorted": bool((diffs > 0).all()),
        "duplicates": int((diffs == 0).sum()),
    }


def estimate_server_offset_hours(tick_epoch: int, now_epoch: float, max_age_s: int = 300) -> int | None:
    """Desfase entero (horas) entre las marcas del servidor y el reloj UTC local.

    Solo es fiable con el mercado abierto: exige que, con ese desfase, el último
    tick tenga como mucho max_age_s segundos de antigüedad. Con el mercado
    cerrado devuelve None en lugar de adivinar.
    """
    diff = tick_epoch - now_epoch
    for hours in range(-12, 15):
        age = hours * 3600 - diff
        if -5 <= age <= max_age_s:
            return hours
    return None


def _mt5_section(client: MT5Client, cfg: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
    section: dict[str, Any] = {"available": True, "package_version": client.package_version()}
    issues: list[str] = []
    section["terminal"] = client.terminal_info()
    account = client.account_info_safe()
    section["account"] = account
    issues += check_source(account, cfg["source"])
    if section["terminal"].get("trade_allowed"):
        issues.append("WARN: el botón de trading algorítmico del terminal está activado")

    choice = select_gold_symbol(client.symbols(), cfg["symbol"])
    section["symbol_selection"] = choice
    issues += choice["issues"]
    name = choice["selected"]
    if name is None:
        section["issues"] = issues
        return section

    spec = client.symbol_spec(name)
    section["symbol_spec"] = spec
    tick = client.last_tick(name)
    section["last_tick"] = {
        "time_raw": tick["time"], "time_raw_as_utc": utc_iso(tick["time"]),
        "bid": tick["bid"], "ask": tick["ask"], "spread": round(tick["ask"] - tick["bid"], spec["digits"]),
    }
    offset = estimate_server_offset_hours(tick["time"], now.timestamp())
    section["server_offset_hours"] = offset
    if offset is None:
        issues.append("WARN: desfase horario del servidor no verificable (último tick antiguo, mercado cerrado)")
    section["margin_min_volume"] = {
        "volume": spec["volume_min"], "price": tick["ask"],
        "margin": client.margin_for(name, spec["volume_min"], tick["ask"]),
    }

    end = now + dt.timedelta(days=1)
    history = {}
    for tf in cfg["timeframes"]:
        rates = client.rates(name, tf, HISTORY_START, end)
        times = rates["time"] if len(rates) else np.empty(0, dtype=np.int64)
        summary = summarize_bar_times(times, TIMEFRAME_SECONDS[tf])
        if len(rates):
            last_year = rates[rates["time"] >= rates["time"][-1] - 365 * 86400]
            summary["spread_points_last_365d"] = {
                f"p{q}": float(np.percentile(last_year["spread"], q)) for q in (5, 50, 95, 99)
            }
        history[tf] = summary
        if summary["duplicates"] or not summary["sorted"]:
            issues.append(f"CRITICAL: historial {tf} desordenado o con duplicados")
    section["history"] = history

    first = client.first_tick(name, HISTORY_START)
    ticks: dict[str, Any] = {"first_tick_time_raw_as_utc": utc_iso(first["time"]) if first else None}
    ticks["count_last_24h_before_last_tick"] = client.tick_count(
        name,
        dt.datetime.fromtimestamp(tick["time"] - 86400, UTC),
        dt.datetime.fromtimestamp(tick["time"] + 1, UTC),
    )
    section["ticks"] = ticks
    if first is None:
        issues.append("WARN: el terminal no devuelve ticks para el símbolo")
    section["issues"] = issues
    return section


def build_report(cfg: dict[str, Any], client: MT5Client | None = None, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(UTC)
    report: dict[str, Any] = {
        "generated_at_utc": now.isoformat(),
        "system": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "python_executable": sys.executable,
            "packages": package_versions(),
        },
    }
    client = client or MT5Client(path=cfg["terminal"].get("path"), timeout_ms=cfg["terminal"]["timeout_ms"])
    try:
        with client:
            report["mt5"] = _mt5_section(client, cfg, now)
    except MT5Error as exc:
        report["mt5"] = {"available": False, "error": str(exc), "issues": [f"CRITICAL: {exc}"]}
    issues = report["mt5"]["issues"]
    if not report["mt5"]["available"]:
        report["status"] = "UNAVAILABLE"
    elif any(i.startswith("CRITICAL") for i in issues):
        report["status"] = "CRITICAL"
    elif issues:
        report["status"] = "WARN"
    else:
        report["status"] = "OK"
    return report


def write_report(report: dict[str, Any], out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["generated_at_utc"][:19].replace(":", "").replace("-", "")
    path = out_dir / f"environment_{stamp}Z.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path
