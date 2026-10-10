"""Tamaño de posición a partir de las especificaciones reales y del riesgo monetario.

Nunca redondea hacia arriba: si el volumen permitido por el riesgo queda por debajo
del mínimo del instrumento, la decisión es no operar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Instrument:
    symbol: str
    point: float
    tick_size: float
    tick_value: float          # USD por tick y lote
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    leverage: float
    swap_long_points: float
    swap_short_points: float
    swap_triple_weekday: int   # 0 = lunes ... 6 = domingo (MT5 usa 0 = domingo)
    digits: int

    @classmethod
    def from_spec(cls, spec: dict[str, Any], leverage: float) -> Instrument:
        if spec.get("trade_calc_mode") not in ("FOREX", "CFD", "CFDLEVERAGE"):
            raise ValueError(f"modo de cálculo no soportado: {spec.get('trade_calc_mode')}")
        if spec.get("currency_profit") != "USD":
            raise ValueError("el motor solo convierte P&L con divisa de beneficio USD")
        mt5_day = int(spec["swap_rollover3days"])          # 0 domingo .. 6 sábado
        return cls(
            symbol=spec["name"], point=spec["point"], tick_size=spec["trade_tick_size"],
            tick_value=spec["trade_tick_value"], contract_size=spec["trade_contract_size"],
            volume_min=spec["volume_min"], volume_max=spec["volume_max"], volume_step=spec["volume_step"],
            leverage=float(leverage), swap_long_points=spec["swap_long"], swap_short_points=spec["swap_short"],
            swap_triple_weekday=(mt5_day - 1) % 7, digits=spec["digits"],
        )

    def value_per_price_unit(self, volume: float) -> float:
        """USD por cada 1.0 de movimiento del precio con `volume` lotes."""
        return self.tick_value / self.tick_size * volume

    def margin(self, volume: float, price: float) -> float:
        """Margen FOREX en USD: volumen x contrato x precio / apalancamiento (coincide con
        order_calc_margin del terminal: 20.98 USD para 0.01 lotes a 4195.36)."""
        return volume * self.contract_size * price / self.leverage

    def floor_volume(self, volume: float) -> float:
        steps = math.floor(volume / self.volume_step + 1e-9)
        return round(min(steps * self.volume_step, self.volume_max), 8)


@dataclass(frozen=True)
class SizingResult:
    volume: float
    risk_usd: float
    allowed_risk_usd: float
    reason: str | None = None      # motivo del bloqueo; None si se puede operar


def size_by_risk(instrument: Instrument, equity: float, risk_fraction: float, entry: float, stop: float,
                 extra_cost_per_lot_usd: float = 0.0) -> SizingResult:
    """Volumen máximo cuyo riesgo (distancia al stop + costes por lote) no supera el permitido."""
    allowed = equity * risk_fraction
    dist = abs(entry - stop)
    if dist <= 0:
        return SizingResult(0.0, 0.0, allowed, "stop en el precio de entrada o al otro lado")
    risk_per_lot = dist * instrument.value_per_price_unit(1.0) + extra_cost_per_lot_usd
    raw = allowed / risk_per_lot
    volume = instrument.floor_volume(raw)
    if volume < instrument.volume_min - 1e-12:
        min_risk = instrument.volume_min * risk_per_lot
        return SizingResult(0.0, min_risk, allowed,
                            f"volumen mínimo {instrument.volume_min} arriesga {min_risk:.2f} USD > permitido {allowed:.2f} USD")
    return SizingResult(volume, volume * risk_per_lot, allowed)
