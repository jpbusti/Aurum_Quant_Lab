"""Interfaz de línea de comandos: python -m aurum.cli <comando>.

Fase A solo implementa check-environment. Los demás comandos llegan con su fase.
"""

from __future__ import annotations

import argparse
import logging
import sys

from aurum.config import PROJECT_ROOT, load_data_config
from aurum.environment import build_report, write_report

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aurum", description="AURUM Quant Lab")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check-environment", help="Inspecciona Python, el terminal MT5 y el símbolo de oro")
    p.add_argument("--config", default=None, help="Ruta a data.yaml (por defecto configs/data.yaml)")
    p.add_argument("--out", default=str(PROJECT_ROOT / "data" / "reports" / "environment"))
    p.set_defaults(func=cmd_check_environment)
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
