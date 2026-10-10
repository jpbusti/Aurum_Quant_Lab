"""Horas de sesión expresadas en hora de Nueva York.

Con la convención de docs/TIMEZONE.md (servidor = Nueva York + 7 h, pendiente de
confirmación en vivo), la hora de Nueva York se obtiene restando 7 h a la marca del
servidor, sin zonas horarias y sin ambigüedad durante las sesiones. Si la convención
cambiara, solo hay que cambiar SERVER_MINUS_NY_HOURS en aurum.timeutils.
"""

from __future__ import annotations

import numpy as np

from aurum.timeutils import SERVER_MINUS_NY_HOURS

_SHIFT = SERVER_MINUS_NY_HOURS * 3600


def ny_minute_of_day(time_raw: int | np.ndarray) -> int | np.ndarray:
    """Minuto del día en Nueva York (0-1439) de una marca del servidor."""
    return ((np.asarray(time_raw, dtype=np.int64) - _SHIFT) % 86400) // 60


def ny_day(time_raw: int | np.ndarray) -> int | np.ndarray:
    """Día de calendario de Nueva York como número de días desde el epoch."""
    return (np.asarray(time_raw, dtype=np.int64) - _SHIFT) // 86400


def server_time_at_ny(day: int, hh: int, mm: int) -> int:
    """Marca del servidor correspondiente a hh:mm de Nueva York del día `day` (ny_day)."""
    return int(day) * 86400 + (hh * 60 + mm) * 60 + _SHIFT


def hhmm(text: str) -> tuple[int, int]:
    h, m = text.split(":")
    return int(h), int(m)
