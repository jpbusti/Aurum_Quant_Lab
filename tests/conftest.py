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


@pytest.fixture
def cfg_b(cfg):
    """Configuración de fase B: fuente de prueba + calendario y umbrales reales de configs/data.yaml."""
    from aurum.config import load_data_config

    real = load_data_config()
    return {
        **cfg,
        "timeframes": ["M1", "M15", "H1"],
        "download": {**real["download"], "bars_start": "2024-01-01", "retry_wait_s": 0.0},
        "sessions": real["sessions"],
        "validation": {**real["validation"], "exclusions": []},
    }
