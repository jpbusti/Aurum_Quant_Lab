"""Registro de estrategias con sus parámetros fijados. configs/research.yaml debe coincidir
(lo comprueba tests/unit/test_strategies.py)."""

from __future__ import annotations

from dataclasses import asdict

from aurum.strategies.base import Strategy
from aurum.strategies.candidates import (
    AtrTrendBreakout,
    IntradayMomentumNY,
    OpeningRangeBreakoutNY,
)
from aurum.strategies.references import NoTrade, RandomEntry, SmaCross

STRATEGIES: dict[str, type[Strategy]] = {
    cls.name: cls
    for cls in (NoTrade, RandomEntry, SmaCross, OpeningRangeBreakoutNY, IntradayMomentumNY, AtrTrendBreakout)
}


def build(name: str) -> Strategy:
    return STRATEGIES[name]()


def default_params(name: str) -> dict:
    strategy = build(name)
    return asdict(strategy.p) if hasattr(strategy, "p") else {}
