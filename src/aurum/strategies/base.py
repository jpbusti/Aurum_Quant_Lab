"""Interfaz común de estrategias y ejecución sin acceso a velas futuras.

En cada instante de decisión T (cierre de una vela del timeframe de señal) la
estrategia recibe un DataView que solo contiene barras CERRADAS en T de cada
timeframe. No hay forma de pedirle al DataView una barra posterior.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

from aurum.backtesting.types import Signal
from aurum.data.mt5_client import TIMEFRAME_SECONDS
from aurum.features.align import last_closed_index


class DataView:
    def __init__(self, frames: dict[str, pd.DataFrame], decision_time: int):
        self._frames = frames
        self.decision_time = int(decision_time)
        self.info_time = -1    # cierre de la barra más reciente consultada

    def closed(self, timeframe: str, last_n: int | None = None) -> pd.DataFrame:
        """Barras de `timeframe` cerradas en el instante de decisión (las últimas `last_n`)."""
        df = self._frames[timeframe]
        tf_s = TIMEFRAME_SECONDS[timeframe]
        idx = int(last_closed_index(df["time_raw"].to_numpy(np.int64), tf_s, np.array([self.decision_time]))[0])
        if idx < 0:
            return df.iloc[0:0]
        start = 0 if last_n is None else max(0, idx + 1 - last_n)
        out = df.iloc[start: idx + 1]
        self.info_time = max(self.info_time, int(out["time_raw"].iloc[-1]) + tf_s)
        return out


class Strategy(ABC):
    """Una estrategia decide en el cierre de cada vela de `signal_timeframe`."""

    name: str = "base"
    signal_timeframe: str = "M15"

    @abstractmethod
    def decide(self, view: DataView) -> tuple[int, float, float | None, int | None] | None:
        """Devuelve (lado, stop, objetivo, max_hold_s) o None. Sin efectos externos."""


def generate_signals(strategy: Strategy, frames: dict[str, pd.DataFrame]) -> list[Signal]:
    tf_s = TIMEFRAME_SECONDS[strategy.signal_timeframe]
    decision_times = frames[strategy.signal_timeframe]["time_raw"].to_numpy(np.int64) + tf_s
    signals = []
    for t in decision_times:
        view = DataView(frames, int(t))
        out = strategy.decide(view)
        if out is None:
            continue
        side, stop, tp, max_hold = out
        signals.append(Signal(decision_time=int(t), side=side, stop=stop, take_profit=tp,
                              max_hold_s=max_hold, info_time=view.info_time, tag=strategy.name))
    return signals
