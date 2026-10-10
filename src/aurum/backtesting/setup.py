"""Construcción del motor a partir de los archivos de configuración y del almacén de datos."""

from __future__ import annotations

import datetime as dt
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aurum.backtesting.engine import Backtester
from aurum.backtesting.spread_model import SpreadModel
from aurum.backtesting.types import CostScenario, ExecutionConfig, RiskConfig
from aurum.config import PROJECT_ROOT, load_yaml
from aurum.data.storage import RawStore
from aurum.risk.sizing import Instrument
from aurum.validation.quality import apply_exclusions, require_usable


def load_backtest_configs() -> tuple[dict[str, Any], dict[str, Any]]:
    return load_yaml(PROJECT_ROOT / "configs" / "backtest.yaml"), load_yaml(PROJECT_ROOT / "configs" / "risk.yaml")


def make_tick_provider(store: RawStore):
    """Devuelve los ticks de un minuto leyendo (y guardando en caché) solo su archivo diario."""

    @lru_cache(maxsize=8)
    def day_ticks(day: dt.date) -> pd.DataFrame | None:
        path = store.tick_path(day)
        return pd.read_parquet(path, columns=["time_msc", "bid", "ask"]) if path.exists() else None

    def provider(minute: int) -> pd.DataFrame | None:
        day = dt.datetime.fromtimestamp(minute, dt.timezone.utc).date()
        ticks = day_ticks(day)
        if ticks is None:
            return None
        t = ticks["time_msc"].to_numpy(np.int64)
        a, b = np.searchsorted(t, [minute * 1000, (minute + 60) * 1000])
        return ticks.iloc[a:b]

    return provider


def build_backtester(scenario: str, store: RawStore | None = None,
                     bt_cfg: dict[str, Any] | None = None, risk_cfg: dict[str, Any] | None = None) -> Backtester:
    if bt_cfg is None or risk_cfg is None:
        bt_cfg, risk_cfg = load_backtest_configs()
    spec = json.loads((PROJECT_ROOT / bt_cfg["instrument"]["spec_file"]).read_text(encoding="utf-8"))
    instrument = Instrument.from_spec(spec, bt_cfg["instrument"]["leverage"])
    model = SpreadModel.load(PROJECT_ROOT / bt_cfg["spread_model_file"])
    sc = CostScenario.from_config(scenario, bt_cfg, bt_cfg["commission"]["per_side_per_lot_usd"])
    ex_cfg = bt_cfg["execution"]
    execution = ExecutionConfig(max_entry_delay_s=ex_cfg["max_entry_delay_s"],
                                same_bar_policy=ex_cfg["same_bar_policy"],
                                use_ticks_intrabar=ex_cfg["use_ticks_intrabar"],
                                max_open_positions=ex_cfg["max_open_positions"])
    s, lim = risk_cfg["sizing"], risk_cfg["limits"]
    risk = RiskConfig(initial_balance=risk_cfg["backtest_balance_usd"], sizing_mode=s["mode"],
                      risk_per_trade_fraction=s["risk_per_trade_fraction"], fixed_volume=s["fixed_volume"],
                      daily_loss_fraction=lim["daily_loss_fraction"], max_drawdown_fraction=lim["max_drawdown_fraction"])
    ticks = make_tick_provider(store) if (store is not None and execution.use_ticks_intrabar) else None
    return Backtester(instrument, model, sc, execution, risk, ticks)


def load_m1(store: RawStore, start_raw: int | None = None, end_raw: int | None = None,
            exclusions: list[dict[str, str]] | None = None) -> pd.DataFrame:
    """Barras M1 del almacén en [start_raw, end_raw), leyendo solo los años necesarios y
    quitando los rangos excluidos de configs/data.yaml."""
    frames = []
    for path in store.bar_files("M1"):
        year = int(path.stem)
        if start_raw is not None and year < dt.datetime.fromtimestamp(start_raw, dt.timezone.utc).year:
            continue
        if end_raw is not None and year > dt.datetime.fromtimestamp(end_raw - 1, dt.timezone.utc).year:
            continue
        frames.append(pd.read_parquet(path))
    df = pd.concat(frames, ignore_index=True)
    if start_raw is not None:
        df = df[df["time_raw"] >= start_raw]
    if end_raw is not None:
        df = df[df["time_raw"] < end_raw]
    if exclusions:
        df, _ = apply_exclusions(df, exclusions, duration=60)
    return df.reset_index(drop=True)


def load_validated_m1(store: RawStore, data_cfg: dict[str, Any], start_raw: int | None = None,
                      end_raw: int | None = None) -> pd.DataFrame:
    """Como load_m1, pero exige que el último informe de calidad no bloquee M1."""
    require_usable(PROJECT_ROOT / "data" / "reports" / "quality" / "latest.json", ["M1"])
    return load_m1(store, start_raw, end_raw, data_cfg["validation"]["exclusions"])
