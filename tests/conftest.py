import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

from fake_mt5 import FakeMT5  # noqa: E402


@pytest.fixture
def cfg():
    return {
        "source": {"broker": "Test", "server": "TestServer-Demo", "account_trade_mode": "DEMO"},
        "symbol": {"name": "XAUUSD.t", "currency_base": "XAU", "currency_profit": "USD"},
        "timeframes": ["M1", "M15", "H1"],
        "terminal": {"path": None, "timeout_ms": 1000},
    }


@pytest.fixture
def fake():
    return FakeMT5()
