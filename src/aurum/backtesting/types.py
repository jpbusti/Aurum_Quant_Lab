"""Tipos compartidos entre estrategias y motor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Signal:
    """Intención de abrir una posición. La estrategia no ejecuta nada.

    decision_time: epoch del servidor en que la señal se conoce (cierre de la vela de señal).
    info_time:     marca más reciente de los datos usados para decidir; debe ser <= decision_time.
    stop / take_profit: precios absolutos. Un largo se cierra al bid y un corto al ask (como MT5).
    max_hold_s:    cierre por tiempo, opcional.
    """

    decision_time: int
    side: int
    stop: float
    info_time: int
    take_profit: float | None = None
    max_hold_s: int | None = None
    tag: str = ""

    def __post_init__(self) -> None:
        if self.side not in (1, -1):
            raise ValueError("side debe ser 1 (compra) o -1 (venta)")


@dataclass
class CostScenario:
    name: str
    spread_excess: str
    spread_multiplier: float = 1.0
    slippage_points: float = 0.0
    commission_per_side_per_lot: float = 0.0
    commission_multiplier: float = 1.0
    swap_multiplier: float = 1.0

    @classmethod
    def from_config(cls, name: str, cfg: dict[str, Any], commission_per_side_per_lot: float) -> CostScenario:
        s = cfg["scenarios"][name]
        return cls(name=name, spread_excess=s["spread_excess"], spread_multiplier=s["spread_multiplier"],
                   slippage_points=s["slippage_points"], commission_per_side_per_lot=commission_per_side_per_lot,
                   commission_multiplier=s["commission_multiplier"], swap_multiplier=s["swap_multiplier"])

    def commission_side(self, volume: float) -> float:
        """Comisión de UN lado (apertura o cierre) para `volume` lotes, en USD."""
        return self.commission_per_side_per_lot * self.commission_multiplier * volume


@dataclass
class ExecutionConfig:
    max_entry_delay_s: int = 120
    same_bar_policy: str = "stop_first"
    use_ticks_intrabar: bool = True
    max_open_positions: int = 1


@dataclass
class RiskConfig:
    initial_balance: float = 10_000.0
    sizing_mode: str = "risk"
    risk_per_trade_fraction: float = 0.005
    fixed_volume: float = 0.01
    daily_loss_fraction: float | None = 0.02
    max_drawdown_fraction: float | None = 0.10


@dataclass
class BacktestResult:
    trades: Any
    equity: Any
    rejections: Any
    stats: dict[str, Any] = field(default_factory=dict)
