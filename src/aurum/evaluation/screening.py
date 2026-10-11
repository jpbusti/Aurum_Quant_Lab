"""Screening masivo de la fase F (docs/PREREGISTRO_PHASE_F.md).

Separa las dos capas que la auditoría post-fase E distinguió:

- Capa de señal: ¿hay señal y qué haría la regla? Volumen fijo de 0,01 lotes, sin
  depender del balance (solo el margen de 0,01 lotes).
- Capa de capital: ¿se puede ejecutar con el balance y el riesgo por operación? Tamaño por
  riesgo; las señales cuyo volumen mínimo arriesga demasiado se rechazan y se cuentan.

Cada ejecución devuelve solo métricas agregadas y la serie de retornos diarios (para PSR,
DSR y PBO), sin el detalle de operaciones, para poder correr cientos de variantes.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from aurum.backtesting.engine import Backtester
from aurum.backtesting.types import Signal
from aurum.evaluation import metrics as M
from aurum.validation import statistical_corrections as SC

LAYERS = ("signal", "capital")


def layer_backtester(bt: Backtester, layer: str) -> Backtester:
    """Copia del motor configurada para una capa (sin límites diario ni de drawdown)."""
    out = copy.copy(bt)
    out.risk = copy.copy(bt.risk)
    out.risk.daily_loss_fraction = None
    out.risk.max_drawdown_fraction = None
    if layer == "signal":
        out.risk.sizing_mode, out.risk.fixed_volume = "fixed", 0.01
    elif layer == "capital":
        out.risk.sizing_mode = "risk"
    else:
        raise ValueError(layer)
    return out


def window(signals: Sequence[Signal], start: int, end: int) -> list[Signal]:
    """Señales decididas en [start, end) cuyo cierre por tiempo máximo cae antes de end."""
    return [s for s in signals if start <= s.decision_time and s.decision_time + (s.max_hold_s or 0) <= end]


def run_variant(bt: Backtester, m1: pd.DataFrame, signals: Sequence[Signal], start: int, end: int,
                bootstrap: bool = True) -> tuple[dict[str, Any], pd.Series]:
    """Métricas agregadas y retornos diarios (índice = día del servidor) de una variante."""
    t = m1["time_raw"].to_numpy(np.int64)
    a, b = np.searchsorted(t, [start, end])
    sigs = window(signals, start, end)
    r = bt.run(m1.iloc[a:b], sigs)
    daily = M.daily_equity(r.equity, bt.risk.initial_balance)
    eq = daily.to_numpy(float)
    rets = pd.Series(eq[1:] / eq[:-1] - 1, index=daily.index[1:])
    span = (min(end, int(t[b - 1]) + 60) - start) / 86400
    m = M.compute(r.trades, daily, span, bootstrap=bootstrap)
    sr, skew, kurt, n = SC.moments(rets.to_numpy())
    m.update({
        "signals": len(sigs),
        "rejected": int(len(r.rejections)),
        "rejected_by_size": int((r.rejections["reason"].str.contains("volumen|riesgo", case=False)).sum())
        if len(r.rejections) else 0,
        "rejected_position_open": int((r.rejections["reason"] == "posición abierta").sum()) if len(r.rejections) else 0,
        "psr": SC.psr(sr, 0.0, n, skew, kurt),
        "p_value": SC.sharpe_pvalue(rets.to_numpy()),
        "same_bar_by_policy": int(r.stats.get("same_bar_by_policy", 0)),
        "gap_exits": int(r.stats.get("gap_exits", 0)),
    })
    return m, rets


def export(rows: list[dict[str, Any]], returns: dict[str, pd.Series], path_csv, path_parquet) -> None:
    """Formato estándar: una fila por variante (CSV) y una matriz días x variantes (Parquet)."""
    pd.DataFrame(rows).to_csv(path_csv, index=False)
    mat = pd.DataFrame(returns)
    mat.index.name = "server_day"
    mat.columns = [str(c) for c in mat.columns]
    mat.to_parquet(path_parquet)
