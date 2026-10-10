"""Acceso de solo lectura al terminal MetaTrader 5.

Este módulo usa la sesión ya abierta en el terminal: no recibe ni guarda
credenciales, y no expone ninguna función de envío de órdenes del paquete
MetaTrader5 (tests/unit/test_safety.py lo comprueba).

Las marcas de tiempo que devuelve la API son segundos epoch tal como los
entrega el servidor del bróker. La documentación oficial habla de UTC, pero en
la práctica reflejan la hora del servidor; el desfase se mide en
aurum.environment y se documenta en docs/ENVIRONMENT.md antes de convertir nada.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from collections.abc import Callable
from types import ModuleType
from typing import Any, TypeVar

import numpy as np

log = logging.getLogger(__name__)
T = TypeVar("T")
UTC = dt.timezone.utc

TIMEFRAME_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600}

TERMINAL_FIELDS = (
    "name", "company", "path", "build", "connected",
    "trade_allowed", "tradeapi_disabled", "maxbars",
)
# Campos de cuenta que se pueden registrar. login, name, balance, equity y
# cualquier otro dato identificativo se excluyen a propósito.
ACCOUNT_SAFE_FIELDS = ("server", "company", "currency", "leverage", "margin_mode", "trade_mode")
SYMBOL_SPEC_FIELDS = (
    "name", "description", "path", "currency_base", "currency_profit", "currency_margin",
    "digits", "point", "trade_tick_size", "trade_tick_value", "trade_tick_value_profit",
    "trade_tick_value_loss", "trade_contract_size", "volume_min", "volume_max", "volume_step",
    "volume_limit", "trade_stops_level", "trade_freeze_level", "spread", "spread_float",
    "trade_calc_mode", "trade_mode", "trade_exemode", "filling_mode", "order_mode",
    "expiration_mode", "swap_mode", "swap_long", "swap_short", "swap_rollover3days",
    "margin_initial", "margin_maintenance", "margin_hedged", "custom",
)
# Prefijos de constantes del paquete para traducir enumeraciones a nombres
# sin escribir las tablas a mano.
ENUM_PREFIXES = {
    "trade_calc_mode": "SYMBOL_CALC_MODE_",
    "trade_mode": "SYMBOL_TRADE_MODE_",
    "trade_exemode": "SYMBOL_TRADE_EXECUTION_",
    "swap_mode": "SYMBOL_SWAP_MODE_",
}
ACCOUNT_ENUM_PREFIXES = {
    "trade_mode": "ACCOUNT_TRADE_MODE_",
    "margin_mode": "ACCOUNT_MARGIN_MODE_",
}
# Máscara de bits SYMBOL_FILLING_* de la documentación de MQL5 (el paquete
# Python no exporta estas constantes).
FILLING_FLAGS = {1: "FOK", 2: "IOC", 4: "BOC"}


class MT5Error(RuntimeError):
    """Fallo al hablar con el terminal. Nunca se sustituye por datos inventados."""


def load_mt5() -> ModuleType:
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise MT5Error(
            "No está instalado el paquete MetaTrader5 (solo funciona en Windows con el terminal instalado)"
        ) from exc
    return mt5


def enum_name(mt5: ModuleType, prefix: str, value: int) -> str:
    for attr in dir(mt5):
        if attr.startswith(prefix) and getattr(mt5, attr) == value:
            return attr[len(prefix):]
    return f"UNKNOWN({value})"


def decode_filling(mask: int) -> list[str]:
    return [name for bit, name in FILLING_FLAGS.items() if mask & bit]


def _subset(obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    data = obj._asdict()
    return {k: data[k] for k in fields if k in data}


class MT5Client:
    """Conexión de solo lectura. Usar como gestor de contexto."""

    def __init__(self, mt5: ModuleType | None = None, path: str | None = None, timeout_ms: int = 60000):
        self._mt5 = mt5
        self._path = path
        self._timeout_ms = timeout_ms
        self._connected = False

    @property
    def mt5(self) -> ModuleType:
        if self._mt5 is None:
            self._mt5 = load_mt5()
        return self._mt5

    def _fail(self, what: str) -> MT5Error:
        err = self.mt5.last_error()
        log.error("%s falló: %s", what, err)
        return MT5Error(f"{what} falló: {err}")

    def connect(self) -> None:
        kwargs: dict[str, Any] = {"timeout": self._timeout_ms}
        if self._path:
            kwargs["path"] = self._path
        # Sin login/password: se usa la sesión ya abierta en el terminal.
        if not self.mt5.initialize(**kwargs):
            raise self._fail("initialize")
        self._connected = True

    def close(self) -> None:
        if self._connected:
            self.mt5.shutdown()
            self._connected = False

    def __enter__(self) -> MT5Client:
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def package_version(self) -> str:
        return getattr(self.mt5, "__version__", "unknown")

    def terminal_info(self) -> dict[str, Any]:
        info = self.mt5.terminal_info()
        if info is None:
            raise self._fail("terminal_info")
        out = _subset(info, TERMINAL_FIELDS)
        version = self.mt5.version()
        out["version"] = list(version) if version else None
        return out

    def account_info_safe(self) -> dict[str, Any]:
        info = self.mt5.account_info()
        if info is None:
            raise self._fail("account_info")
        out = _subset(info, ACCOUNT_SAFE_FIELDS)
        for field, prefix in ACCOUNT_ENUM_PREFIXES.items():
            if field in out:
                out[field] = enum_name(self.mt5, prefix, out[field])
        return out

    def symbols(self) -> list[dict[str, Any]]:
        syms = self.mt5.symbols_get()
        if syms is None:
            raise self._fail("symbols_get")
        fields = ("name", "description", "path", "currency_base", "currency_profit", "custom", "visible")
        return [_subset(s, fields) for s in syms]

    def symbol_spec(self, name: str) -> dict[str, Any]:
        info = self.mt5.symbol_info(name)
        if info is None:
            raise self._fail(f"symbol_info({name})")
        if not info.visible and not self.mt5.symbol_select(name, True):
            raise self._fail(f"symbol_select({name})")
        spec = _subset(info, SYMBOL_SPEC_FIELDS)
        for field, prefix in ENUM_PREFIXES.items():
            spec[field] = enum_name(self.mt5, prefix, spec[field])
        spec["filling_mode"] = decode_filling(spec["filling_mode"])
        return spec

    def last_tick(self, name: str) -> dict[str, Any]:
        tick = self.mt5.symbol_info_tick(name)
        if tick is None:
            raise self._fail(f"symbol_info_tick({name})")
        return tick._asdict()

    def margin_for(self, name: str, volume: float, price: float) -> float | None:
        """Margen que calcula el terminal para una compra hipotética. Es un cálculo, no una orden."""
        margin = self.mt5.order_calc_margin(self.mt5.ORDER_TYPE_BUY, name, volume, price)
        if margin is None:
            log.warning("order_calc_margin sin resultado: %s", self.mt5.last_error())
        return margin

    def rates(self, name: str, timeframe: str, start: dt.datetime, end: dt.datetime) -> np.ndarray:
        tf = getattr(self.mt5, f"TIMEFRAME_{timeframe}")
        rates = self.mt5.copy_rates_range(name, tf, start, end)
        if rates is None:
            raise self._fail(f"copy_rates_range({name}, {timeframe})")
        return rates

    def first_tick(self, name: str, since: dt.datetime) -> dict[str, Any] | None:
        ticks = self.mt5.copy_ticks_from(name, since, 1, self.mt5.COPY_TICKS_ALL)
        if ticks is None:
            raise self._fail(f"copy_ticks_from({name})")
        if len(ticks) == 0:
            return None
        return {k: ticks[0][k].item() for k in ticks.dtype.names}

    def ticks(self, name: str, start: dt.datetime, end: dt.datetime) -> np.ndarray:
        ticks = self.mt5.copy_ticks_range(name, start, end, self.mt5.COPY_TICKS_ALL)
        if ticks is None:
            raise self._fail(f"copy_ticks_range({name})")
        return ticks

    def tick_count(self, name: str, start: dt.datetime, end: dt.datetime) -> int:
        return len(self.ticks(name, start, end))

    def retrying(self, fn: Callable[[], T], retries: int = 3, wait_s: float = 2.0) -> T:
        """Ejecuta fn; ante un fallo del terminal reconecta y reintenta con espera creciente.

        Si persiste, propaga el último error. Nunca devuelve datos vacíos en su lugar.
        """
        for attempt in range(1, retries + 1):
            try:
                return fn()
            except MT5Error as exc:
                if attempt == retries:
                    raise
                log.warning("intento %d/%d fallido (%s); reconectando", attempt, retries, exc)
                time.sleep(wait_s * attempt)
                self.close()
                try:
                    self.connect()
                except MT5Error as conn_exc:
                    log.warning("reconexión fallida: %s", conn_exc)
        raise AssertionError("inalcanzable")
