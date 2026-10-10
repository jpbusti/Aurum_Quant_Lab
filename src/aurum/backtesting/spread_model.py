"""Modelo de spread calibrado con ticks reales.

Modelo elegido (docs/COST_MODEL.md):

    spread_estimado(minuto) = spread_min_barra(minuto) + exceso(hora del servidor, escenario)

- spread_min_barra es el campo `spread` de la barra M1: el spread mínimo del minuto,
  disponible en todo el historial (2017-2026). Recoge cómo cambia el nivel del spread
  con el tiempo (por ejemplo, la ampliación de 2020).
- exceso = spread medio ponderado por tiempo del minuto menos ese mínimo. Se calibra con
  los ticks (abril-octubre de 2026) por hora del servidor. Base = media del exceso,
  adverso = percentil 90, estrés = percentil 99.

Los cuantiles de cada escenario se fijan en configs/backtest.yaml antes de probar
ninguna estrategia y no se ajustan con resultados de estrategias.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

HOURS = list(range(24))
STATS = {"mean": None, "p50": 0.50, "p75": 0.75, "p90": 0.90, "p95": 0.95, "p99": 0.99}


def _describe(s: pd.Series) -> dict[str, float]:
    out = {"n": int(s.size)}
    for name, q in STATS.items():
        out[name] = round(float(s.mean() if q is None else s.quantile(q)), 3)
    return out


def join_minutes_with_bars(minutes: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    """Une el resumen de ticks con el spread mínimo de cada barra M1 del mismo minuto.

    Se descartan los minutos cuyo máximo o mínimo bid de ticks no coincide con la barra
    (ticks incompletos, como el 2026-06-29 15:41): ahí el resumen no representa el minuto.
    """
    j = minutes.merge(m1[["time_raw", "spread", "high", "low"]], on="time_raw", how="inner")
    consistent = (np.abs(j["high"] - j["bid_high"]) <= 0.005) & (np.abs(j["low"] - j["bid_low"]) <= 0.005)
    j = j[consistent].copy()
    j["hour"] = (j["time_raw"] % 86400) // 3600
    j["excess"] = j["spread_mean_time"] - j["spread"]
    return j


def evaluate_candidates(joined: pd.DataFrame, split_raw: int) -> dict[str, Any]:
    """Compara modelos de spread prediciendo el spread medio por tiempo de cada minuto
    del periodo posterior a split_raw con parámetros del periodo anterior."""
    tr, te = joined[joined["time_raw"] < split_raw], joined[joined["time_raw"] >= split_raw]
    y = te["spread_mean_time"].to_numpy()
    hour_mean = tr.groupby("hour")["spread_mean_time"].mean()
    hour_excess = tr.groupby("hour")["excess"].mean()
    preds = {
        "fijo_media_global": np.full(len(te), tr["spread_mean_time"].mean()),
        # Horas sin datos de calibración usan el valor global, como el modelo en producción.
        "media_por_hora": te["hour"].map(hour_mean).fillna(tr["spread_mean_time"].mean()).to_numpy(),
        "minimo_barra_mas_exceso_por_hora": (te["spread"] + te["hour"].map(hour_excess)
                                             .fillna(tr["excess"].mean())).to_numpy(),
    }
    out = {"train_minutes": int(len(tr)), "test_minutes": int(len(te)),
           "split_raw": int(split_raw), "candidates": {}}
    for name, p in preds.items():
        err = p - y
        out["candidates"][name] = {"mae_points": round(float(np.nanmean(np.abs(err))), 3),
                                   "bias_points": round(float(np.nanmean(err)), 3)}
    return out


def calibrate(joined: pd.DataFrame, source: dict[str, Any], scenarios: dict[str, str],
              evaluation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Tabla por hora del servidor: estadísticas del spread medio por tiempo y del exceso."""
    by_hour: dict[int, Any] = {}
    for h, g in joined.groupby("hour"):
        by_hour[int(h)] = {"spread_mean_time": _describe(g["spread_mean_time"]),
                           "bar_min_spread": _describe(g["spread"].astype(float)),
                           "excess": _describe(g["excess"])}
    overall_excess = _describe(joined["excess"])
    return {
        "model": "spread = spread_min_barra_M1 + exceso(hora_servidor, escenario)",
        "unit": "puntos (0.01 USD en XAUUSD)",
        "time_convention": "hora del servidor (NY + 7 h, docs/TIMEZONE.md)",
        "calibrated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": source,
        "sample": {"minutes": int(len(joined)),
                   "first": pd.to_datetime(joined["time_raw"].min(), unit="s").isoformat(),
                   "last": pd.to_datetime(joined["time_raw"].max(), unit="s").isoformat()},
        "scenario_excess_stat": scenarios,
        "overall": {"spread_mean_time": _describe(joined["spread_mean_time"]), "excess": overall_excess},
        "fallback_excess": overall_excess,
        "by_hour": by_hour,
        "evaluation": evaluation,
    }


def write_model(model: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    header = ("# Generado por `python -m aurum.cli calibrate-costs`. No editar a mano:\n"
              "# volver a calibrar si cambian los ticks o el método (docs/COST_MODEL.md).\n")
    path.write_text(header + yaml.safe_dump(model, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


class SpreadModel:
    """Búsqueda vectorizada del spread estimado por minuto. `stat` es el estadístico del
    exceso que usa cada escenario (mean, p50, p75, p90, p95, p99)."""

    def __init__(self, model: dict[str, Any]):
        self.model = model
        fallback = model["fallback_excess"]
        self._excess = {}
        for stat in STATS:
            if stat not in fallback:
                continue
            table = np.full(24, fallback[stat], dtype=float)
            for h, row in model["by_hour"].items():
                table[int(h)] = row["excess"][stat]
            self._excess[stat] = table

    @classmethod
    def load(cls, path: str | Path) -> SpreadModel:
        return cls(yaml.safe_load(Path(path).read_text(encoding="utf-8")))

    def excess(self, time_raw: np.ndarray, stat: str) -> np.ndarray:
        hours = (np.asarray(time_raw, dtype=np.int64) % 86400) // 3600
        return self._excess[stat][hours]

    def spread_points(self, time_raw: np.ndarray, bar_min_spread: np.ndarray, stat: str) -> np.ndarray:
        return np.asarray(bar_min_spread, dtype=float) + self.excess(time_raw, stat)
