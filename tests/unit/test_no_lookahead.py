"""Fuga de información: alineación de timeframes y estabilidad de señales ante cambios futuros.

Datos SINTÉTICOS. La estrategia de prueba no es una estrategia de inversión: solo combina
H1, M15 y M5 para comprobar que el motor no ve velas sin cerrar.
"""

import numpy as np
import pandas as pd
import pytest

from aurum.data.storage import rates_to_frame
from aurum.features.align import asof_closed, last_closed_index
from aurum.strategies.base import DataView, Strategy, generate_signals
from aurum.timeutils import AmbiguousServerTime, server_offset_hours, server_to_utc
from synthetic import MONDAY, make_rates, resample, session_minutes


def frames(seed=0, weeks=1):
    m1 = make_rates(session_minutes(MONDAY, weeks), seed)
    return {"M1": rates_to_frame(m1), "M5": rates_to_frame(resample(m1, 300)),
            "M15": rates_to_frame(resample(m1, 900)), "H1": rates_to_frame(resample(m1, 3600))}


class MultiTF(Strategy):
    name = "prueba_multi_tf"
    signal_timeframe = "M15"

    def decide(self, view):
        h1 = view.closed("H1", 2)
        m15 = view.closed("M15", 1)
        m5 = view.closed("M5", 1)
        if len(h1) < 2 or m15.empty or m5.empty:
            return None
        up = h1["close"].iloc[-1] > h1["close"].iloc[-2]
        confirm = m5["close"].iloc[-1] >= m15["close"].iloc[-1]
        if up and confirm:
            return 1, float(m15["low"].iloc[-1] - 1.0), None, 3600
        if not up and not confirm:
            return -1, float(m15["high"].iloc[-1] + 1.0), None, 3600
        return None


def test_h1_bar_is_used_only_after_it_closes():
    h1 = pd.DataFrame({"time_raw": [MONDAY + 10 * 3600, MONDAY + 11 * 3600], "close": [1.0, 2.0]})
    decisions = MONDAY + np.array([11 * 3600 - 1, 11 * 3600, 11 * 3600 + 900, 12 * 3600 - 900, 12 * 3600])
    out = asof_closed(h1, 3600, decisions, ["close"])
    assert np.isnan(out["close"][0])                  # la H1 de las 10:00 cierra a las 11:00
    assert out["close"].tolist()[1:4] == [1.0, 1.0, 1.0]  # 11:00-11:45: aún no hay H1 de las 11:00
    assert out["close"][4] == 2.0


def test_last_closed_index_boundaries():
    opens = np.array([0, 900, 1800])
    assert last_closed_index(opens, 900, np.array([899, 900, 1799, 1800, 2700])).tolist() == [-1, 0, 0, 1, 2]


def test_dataview_never_returns_open_bars():
    f = frames()
    t = int(f["M15"]["time_raw"].iloc[100]) + 900
    view = DataView(f, t)
    for tf, d in (("M5", 300), ("M15", 900), ("H1", 3600)):
        last = view.closed(tf)
        assert int(last["time_raw"].iloc[-1]) + d <= t
    assert view.info_time <= t


@pytest.mark.parametrize("cut_index", [57, 200, 333])
def test_changing_future_data_does_not_change_past_signals(cut_index):
    base = frames()
    t_cut = int(base["M15"]["time_raw"].iloc[cut_index]) + 900   # cierre de una vela M15
    sigs = generate_signals(MultiTF(), base)
    assert len(sigs) > 10

    changed = {}
    rng = np.random.default_rng(99)
    for tf, df in base.items():
        df = df.copy()
        d = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600}[tf]
        # Todo lo que aún no ha cerrado en t_cut (incluida la H1 en curso) se altera.
        future = df["time_raw"] + d > t_cut
        noise = rng.normal(0, 25, future.sum())
        for col in ("open", "high", "low", "close"):
            df.loc[future, col] = df.loc[future, col] + noise
        changed[tf] = df
    sigs2 = generate_signals(MultiTF(), changed)
    before = [s for s in sigs if s.decision_time <= t_cut]
    before2 = [s for s in sigs2 if s.decision_time <= t_cut]
    assert before == before2
    assert all(s.info_time <= s.decision_time for s in sigs2)


def test_open_h1_bar_change_does_not_affect_signal_inside_it():
    base = frames()
    t = MONDAY + 86400 + 10 * 3600 + 1800                      # martes 10:30, H1 de las 10:00 abierta
    f2 = {k: v.copy() for k, v in base.items()}
    open_h1 = f2["H1"]["time_raw"] == MONDAY + 86400 + 10 * 3600
    f2["H1"].loc[open_h1, "close"] += 500
    v1, v2 = DataView(base, t), DataView(f2, t)
    assert MultiTF().decide(v1) == MultiTF().decide(v2)


# --- Zona horaria (docs/TIMEZONE.md) -----------------------------------------------------

def _raw(s):
    return int(pd.Timestamp(s, tz="UTC").timestamp())


def test_server_to_utc_follows_us_dst():
    # IPC 2022-11-10 a las 08:30 NY (invierno) -> 15:30 servidor -> 13:30 UTC
    assert server_to_utc(_raw("2022-11-10 15:30"))[0] == pd.Timestamp("2022-11-10 13:30", tz="UTC")
    # Empleo 2024-05-03 a las 08:30 NY (verano) -> 15:30 servidor -> 12:30 UTC
    assert server_to_utc(_raw("2024-05-03 15:30"))[0] == pd.Timestamp("2024-05-03 12:30", tz="UTC")
    assert server_offset_hours(np.array([_raw("2026-01-15 12:00"), _raw("2026-07-15 12:00")])).tolist() == [2, 3]


def test_offset_changes_with_us_not_eu_dst():
    # 2026-03-09 (lunes): EE. UU. ya cambió (8 de marzo), Europa no (29 de marzo).
    assert server_offset_hours(_raw("2026-03-09 12:00"))[0] == 3
    assert server_offset_hours(_raw("2026-03-06 12:00"))[0] == 2


def test_ambiguous_server_time_raises():
    # 2026-11-01 01:30 NY ocurre dos veces -> 08:30 del servidor ese domingo.
    with pytest.raises(AmbiguousServerTime):
        server_to_utc(_raw("2026-11-01 08:30"))
