"""Alineación entre timeframes sin fuga de información.

Reglas (hora del servidor; todas las barras se identifican por su hora de apertura):
- Una barra de duración d abierta en t está CERRADA y disponible en t + d.
- Una decisión tomada en el instante T solo puede usar barras con t + d <= T.
- Las señales de M15 se toman al cierre de la vela M15 (T = apertura + 900 s); la
  barra H1 en curso a esa hora NO se usa hasta que cierre.
- Las sesiones y huecos no se rellenan: si la última barra H1 cerrada es de antes de
  un fin de semana, esa es la información disponible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class LookaheadError(RuntimeError):
    """Se intentó usar información posterior al instante de decisión."""


def close_times(open_times: np.ndarray, tf_seconds: int) -> np.ndarray:
    return np.asarray(open_times, dtype=np.int64) + tf_seconds


def last_closed_index(open_times: np.ndarray, tf_seconds: int, decision_times: np.ndarray) -> np.ndarray:
    """Para cada instante de decisión, índice de la última barra cerrada (-1 si ninguna)."""
    closes = close_times(open_times, tf_seconds)
    return np.searchsorted(closes, np.asarray(decision_times, dtype=np.int64), side="right") - 1


def asof_closed(higher: pd.DataFrame, tf_seconds: int, decision_times: np.ndarray,
                columns: list[str]) -> pd.DataFrame:
    """Valores de la última barra cerrada del timeframe superior en cada instante de decisión.

    Filas sin barra cerrada previa quedan como NaN. Incluye `source_time_raw` (apertura de
    la barra usada) para poder auditar la alineación.
    """
    times = higher["time_raw"].to_numpy(np.int64)
    if np.any(np.diff(times) <= 0):
        raise ValueError("el timeframe superior debe estar ordenado y sin duplicados")
    idx = last_closed_index(times, tf_seconds, decision_times)
    out = pd.DataFrame(index=range(len(idx)))
    valid = idx >= 0
    for c in columns:
        vals = np.full(len(idx), np.nan)
        vals[valid] = higher[c].to_numpy(float)[idx[valid]]
        out[c] = vals
    src = np.full(len(idx), -1, dtype=np.int64)
    src[valid] = times[idx[valid]]
    out["source_time_raw"] = src
    if np.any(src[valid] + tf_seconds > np.asarray(decision_times)[valid]):
        raise LookaheadError("alineación usaría una barra sin cerrar")
    return out
