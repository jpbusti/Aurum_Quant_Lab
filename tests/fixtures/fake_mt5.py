"""Sustituto SINTÉTICO del paquete MetaTrader5 para pruebas unitarias.

Ningún valor de aquí procede del bróker: son datos de prueba inventados para
verificar la lógica. No usar como referencia de especificaciones reales.
"""

from __future__ import annotations

from collections import namedtuple

import numpy as np

SymbolInfo = namedtuple("SymbolInfo", "name description path currency_base currency_profit custom visible")
TerminalInfo = namedtuple("TerminalInfo", "name company path build connected trade_allowed tradeapi_disabled maxbars")
AccountInfo = namedtuple("AccountInfo", "login name balance server company currency leverage margin_mode trade_mode")
Tick = namedtuple("Tick", "time bid ask last volume time_msc flags volume_real")
Spec = namedtuple(
    "Spec",
    "name description path currency_base currency_profit currency_margin digits point trade_tick_size "
    "trade_tick_value trade_tick_value_profit trade_tick_value_loss trade_contract_size volume_min "
    "volume_max volume_step volume_limit trade_stops_level trade_freeze_level spread spread_float "
    "trade_calc_mode trade_mode trade_exemode filling_mode order_mode expiration_mode swap_mode swap_long "
    "swap_short swap_rollover3days margin_initial margin_maintenance margin_hedged custom visible",
)

RATES_DTYPE = [("time", "<i8"), ("open", "<f8"), ("high", "<f8"), ("low", "<f8"), ("close", "<f8"),
               ("tick_volume", "<u8"), ("spread", "<i4"), ("real_volume", "<u8")]
TICKS_DTYPE = [("time", "<i8"), ("bid", "<f8"), ("ask", "<f8"), ("last", "<f8"), ("volume", "<u8"),
               ("time_msc", "<i8"), ("flags", "<u4"), ("volume_real", "<f8")]


class FakeMT5:
    __version__ = "fake"
    TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_M15, TIMEFRAME_M30, TIMEFRAME_H1 = 1, 5, 15, 30, 16385
    TF_SECONDS = {1: 60, 5: 300, 15: 900, 30: 1800, 16385: 3600}
    COPY_TICKS_ALL = -1
    ORDER_TYPE_BUY = 0
    ACCOUNT_TRADE_MODE_DEMO, ACCOUNT_TRADE_MODE_CONTEST, ACCOUNT_TRADE_MODE_REAL = 0, 1, 2
    ACCOUNT_MARGIN_MODE_RETAIL_NETTING, ACCOUNT_MARGIN_MODE_EXCHANGE, ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 0, 1, 2
    SYMBOL_CALC_MODE_FOREX = 0
    SYMBOL_TRADE_MODE_FULL = 4
    SYMBOL_TRADE_EXECUTION_MARKET = 2
    SYMBOL_SWAP_MODE_POINTS = 1

    def __init__(self, *, init_ok=True, trade_mode=0, server="TestServer-Demo", symbols=None,
                 last_tick_time=1_700_000_000, bars_start=1_699_000_000, bars=500):
        self.init_ok = init_ok
        self.trade_mode = trade_mode
        self.server = server
        self.symbols = symbols if symbols is not None else [
            SymbolInfo("XAUUSD.t", "Gold test", "Metals\\XAUUSD.t", "XAU", "USD", False, True),
            SymbolInfo("XAUEUR.t", "Gold EUR test", "Metals\\XAUEUR.t", "XAU", "EUR", False, False),
        ]
        self.last_tick_time = last_tick_time
        self.bars_start = bars_start
        self.bars = bars
        self.shutdown_called = False

    def initialize(self, **kwargs):
        assert "login" not in kwargs and "password" not in kwargs
        return self.init_ok

    def shutdown(self):
        self.shutdown_called = True

    def last_error(self):
        return (1, "Success") if self.init_ok else (-10003, "IPC initialize failed (fake)")

    def version(self):
        return (500, 1, "fake")

    def terminal_info(self):
        return TerminalInfo("Fake MT5", "Test", "C:\\fake", 1, True, False, False, 1000)

    def account_info(self):
        return AccountInfo(12345678, "Secret Name", 1000.0, self.server, "Test Co", "USD", 100, 2, self.trade_mode)

    def symbols_get(self):
        return self.symbols

    def symbol_info(self, name):
        for s in self.symbols:
            if s.name == name:
                return Spec(name, s.description, s.path, s.currency_base, s.currency_profit, "XAU", 2, 0.01,
                            0.01, 1.0, 1.0, 1.0, 100.0, 0.01, 100.0, 0.01, 0.0, 0, 0, 20, True,
                            0, 4, 2, 2, 127, 15, 1, -10.0, 5.0, 3, 0.0, 0.0, 100.0, False, s.visible)
        return None

    def symbol_select(self, name, enable):
        return True

    def symbol_info_tick(self, name):
        return Tick(self.last_tick_time, 2000.00, 2000.20, 0.0, 0, self.last_tick_time * 1000, 6, 0.0)

    def order_calc_margin(self, action, symbol, volume, price):
        return round(volume * 100 * price / 100, 2)

    def copy_rates_range(self, symbol, timeframe, start, end):
        step = self.TF_SECONDS[timeframe]
        out = np.zeros(self.bars, dtype=RATES_DTYPE)
        out["time"] = self.bars_start + step * np.arange(self.bars)
        out["spread"] = 20
        return out

    def copy_ticks_from(self, symbol, start, count, flags):
        out = np.zeros(1, dtype=TICKS_DTYPE)
        out["time"] = self.last_tick_time - 3600
        return out

    def copy_ticks_range(self, symbol, start, end, flags):
        return np.zeros(42, dtype=TICKS_DTYPE)
