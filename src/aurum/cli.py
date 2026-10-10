"""Interfaz de línea de comandos: python -m aurum.cli <comando>.

Comandos disponibles: check-environment (fase A), download-data y validate-data (fase B),
calibrate-costs (fase C).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from aurum.config import PROJECT_ROOT, load_data_config
from aurum.data.ingest import update_bars, update_ticks
from aurum.data.mt5_client import MT5Client, MT5Error
from aurum.data.storage import RawStore, SourceMismatchError
from aurum.environment import build_report, write_report
from aurum.validation.quality import run_quality, write_quality_report

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

EXIT_CODES = {"OK": 0, "WARN": 0, "CRITICAL": 1, "UNAVAILABLE": 2}


def cmd_check_environment(args: argparse.Namespace) -> int:
    cfg = load_data_config(args.config)
    report = build_report(cfg)
    path = write_report(report, args.out)
    mt5 = report["mt5"]
    print(f"Estado: {report['status']}")
    print(f"Python {report['system']['python']} | MetaTrader5 {report['system']['packages']['MetaTrader5']}")
    if mt5["available"]:
        acct, term = mt5["account"], mt5["terminal"]
        print(f"Terminal build {term['build']} | servidor {acct['server']} | cuenta {acct['trade_mode']}")
        print(f"Símbolo: {mt5['symbol_selection']['selected']} (candidatos {mt5['symbol_selection']['candidates']})")
        for tf, h in mt5.get("history", {}).items():
            print(f"  {tf}: {h['bars']} barras, denso desde {h['first_dense_month']}, última {h['last']}")
        if "ticks" in mt5:
            print(f"  Ticks desde: {mt5['ticks']['first_tick_time_raw_as_utc']}")
    for issue in mt5["issues"]:
        print(f"- {issue}")
    print(f"Informe: {path}")
    return EXIT_CODES[report["status"]]


def _store(cfg: dict) -> RawStore:
    return RawStore(RAW_DIR, cfg["source"]["server"], cfg["symbol"]["name"])


def cmd_download_data(args: argparse.Namespace) -> int:
    cfg = load_data_config(args.config)
    timeframes = args.timeframes or cfg["timeframes"]
    store = _store(cfg)
    client = MT5Client(path=cfg["terminal"].get("path"), timeout_ms=cfg["terminal"]["timeout_ms"])
    try:
        with client:
            if not args.no_bars:
                for tf in timeframes:
                    rec = update_bars(client, store, cfg, tf)
                    print(f"{tf}: {rec['new_rows']} barras nuevas, {rec['overlap_conflicts']} conflictos, "
                          f"{rec['dropped_unclosed']} sin cerrar descartadas")
            if args.ticks_days:
                rec = update_ticks(client, store, cfg, args.ticks_days)
                for d in rec["days"]:
                    print(f"ticks {d['day']}: {d.get('rows', 0)} filas"
                          + (f" ({d['skipped']})" if "skipped" in d else "")
                          + ("" if d.get("complete", True) else " (día posiblemente incompleto)"))
    except (MT5Error, SourceMismatchError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(f"Datos en {store.base}")
    return 0


def cmd_validate_data(args: argparse.Namespace) -> int:
    cfg = load_data_config(args.config)
    report = run_quality(_store(cfg), cfg)
    path = write_quality_report(report, args.out)
    for tf, s in report["timeframes"].items():
        print(f"{tf}: {s['status']} | {s['rows']} barras | {s['first']} -> {s['last']}")
        for c in s["checks"]:
            if c["severity"] in ("WARN", "CRITICAL"):
                print(f"   {c['severity']} {c['name']}: {c['summary']}")
    for c in report["cross_checks"] + report["ticks"]["checks"]:
        print(f"{c['severity']} {c['name']}: {c['summary']}")
    print(f"Estado global: {report['status']} | bloqueados: {report['blocked'] or 'ninguno'}")
    print(f"Informe: {path}")
    return 1 if report["blocked"] else 0


def cmd_calibrate_costs(args: argparse.Namespace) -> int:
    import pandas as pd

    from aurum.backtesting.setup import load_backtest_configs, load_m1
    from aurum.backtesting.spread_model import calibrate, evaluate_candidates, join_minutes_with_bars, write_model
    from aurum.data.tick_minutes import build_tick_minutes, save_tick_minutes

    cfg = load_data_config(args.config)
    store = _store(cfg)
    bt_cfg, _ = load_backtest_configs()
    point = json.loads((PROJECT_ROOT / bt_cfg["instrument"]["spec_file"]).read_text(encoding="utf-8"))["point"]
    minutes, hist, meta = build_tick_minutes(store, point)
    out_dir = save_tick_minutes(PROCESSED_DIR / cfg["source"]["server"] / cfg["symbol"]["name"], minutes, hist, meta)
    m1 = load_m1(store, int(minutes["time_raw"].min()), int(minutes["time_raw"].max()) + 60,
                 cfg["validation"]["exclusions"])
    joined = join_minutes_with_bars(minutes, m1)
    split = int(pd.Timestamp(args.split, tz="UTC").timestamp())
    evaluation = evaluate_candidates(joined, split)
    scenarios = {name: sc["spread_excess"] for name, sc in bt_cfg["scenarios"].items()}
    model = calibrate(joined, {**meta["source"], "ticks": meta["ticks"], "days": meta["days"],
                               "excluded_inconsistent_minutes": int(len(minutes) - len(joined))},
                      scenarios, evaluation)
    path = write_model(model, PROJECT_ROOT / bt_cfg["spread_model_file"])
    print(f"Ticks: {meta['ticks']} en {meta['days']} días -> {meta['minutes']} minutos ({out_dir})")
    print(f"Minutos usados: {len(joined)} (excluidos por ticks incompletos: {len(minutes) - len(joined)})")
    for name, ev in evaluation["candidates"].items():
        print(f"  {name}: MAE {ev['mae_points']} pts, sesgo {ev['bias_points']:+} pts")
    print(f"Modelo: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aurum", description="AURUM Quant Lab")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check-environment", help="Inspecciona Python, el terminal MT5 y el símbolo de oro")
    p.add_argument("--config", default=None, help="Ruta a data.yaml (por defecto configs/data.yaml)")
    p.add_argument("--out", default=str(PROJECT_ROOT / "data" / "reports" / "environment"))
    p.set_defaults(func=cmd_check_environment)

    p = sub.add_parser("download-data", help="Descarga incremental de barras (y ticks) desde MT5 a Parquet")
    p.add_argument("--config", default=None)
    p.add_argument("--timeframes", nargs="*", help="Subconjunto de timeframes (por defecto los de data.yaml)")
    p.add_argument("--ticks-days", type=int, default=0, help="Descargar ticks de los N últimos días laborables")
    p.add_argument("--no-bars", action="store_true", help="Solo ticks")
    p.set_defaults(func=cmd_download_data)

    p = sub.add_parser("calibrate-costs", help="Calibra el modelo de spread con los ticks descargados")
    p.add_argument("--config", default=None)
    p.add_argument("--split", default="2026-08-01", help="Inicio del periodo de evaluación del modelo")
    p.set_defaults(func=cmd_calibrate_costs)

    p = sub.add_parser("validate-data", help="Valida la integridad de los datos descargados")
    p.add_argument("--config", default=None)
    p.add_argument("--out", default=str(PROJECT_ROOT / "data" / "reports" / "quality"))
    p.set_defaults(func=cmd_validate_data)
    return parser


def main(argv: list[str] | None = None) -> int:
    # La consola de Windows usa cp1252 por defecto y rompe los acentos.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
