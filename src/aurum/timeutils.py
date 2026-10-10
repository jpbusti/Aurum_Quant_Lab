"""Conversión de la hora del servidor a UTC (docs/TIMEZONE.md).

Convención confirmada con datos históricos 2018-2026 (docs/TIMEZONE.md): hora del servidor =
hora de Nueva York + 7 h. El desfase respecto a UTC cambia con el horario de
verano de EE. UU. (UTC+3 en verano, UTC+2 en invierno): no es constante.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SERVER_MINUS_NY_HOURS = 7
NY_TZ = "America/New_York"


class AmbiguousServerTime(ValueError):
    """La marca cae en un cambio de hora de Nueva York (domingo de madrugada en NY)."""


def server_to_utc(time_raw: np.ndarray | pd.Series | int) -> pd.DatetimeIndex:
    """Convierte epoch del servidor a instantes UTC. Falla en lugar de adivinar
    si una marca cae en la hora repetida o inexistente de un cambio de hora."""
    raw = np.atleast_1d(np.asarray(time_raw, dtype=np.int64))
    ny_naive = pd.to_datetime(raw - SERVER_MINUS_NY_HOURS * 3600, unit="s")
    try:
        ny = ny_naive.tz_localize(NY_TZ, ambiguous="raise", nonexistent="raise")
    except Exception as exc:  # pytz/zoneinfo lanzan tipos distintos según la versión
        raise AmbiguousServerTime(str(exc)) from exc
    return ny.tz_convert("UTC")


def server_offset_hours(time_raw: np.ndarray | int) -> np.ndarray:
    """Desfase servidor - UTC en horas para cada marca (3 en verano de EE. UU., 2 en invierno)."""
    raw = np.atleast_1d(np.asarray(time_raw, dtype=np.int64))
    utc = server_to_utc(raw).asi8 // 10**9
    return (raw - utc) // 3600
