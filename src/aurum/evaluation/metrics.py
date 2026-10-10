"""Métricas de la fase E con las definiciones de docs/PREREGISTRO_PHASE_E.md (sección 5)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from statistics import NormalDist

_N = NormalDist()

DAY = 86400
TRADING_DAYS = 252
STRICT = {"pf": (">=", 1.15), "pf_ci90_low": (">", 1.0), "max_dd_pct": ("<", 20.0), "sharpe": (">", 1.0),
          "sortino": (">", 1.0), "calmar": (">", 0.5), "trades": (">=", 300)}
FLEXIBLE = {"expectancy_r": (">", 0.10), "sqn": (">", 1.5), "recovery_factor": (">", 2.0), "ulcer_index": ("<", 10.0)}


def daily_equity(equity: pd.DataFrame, initial: float) -> pd.Series:
    """Equity al cierre de cada día del servidor con barras, precedida del balance inicial."""
    if equity.empty:
        return pd.Series([initial], index=[-1], dtype=float)
    day = equity["time_raw"].to_numpy(np.int64) // DAY
    last = equity.groupby(day)["equity"].last()
    return pd.concat([pd.Series([initial], index=[int(last.index[0]) - 1]), last]).astype(float)


def profit_factor(net: np.ndarray) -> float:
    gains, losses = net[net > 0].sum(), -net[net < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else float("nan")
    return float(gains / losses)


def block_bootstrap_pf(net: np.ndarray, reps: int = 5000, seed: int = 20261010) -> np.ndarray:
    """PF de réplicas por bootstrap circular por bloques (bloque = ceil(n^(1/3)))."""
    n = len(net)
    if n < 2:
        return np.full(reps, np.nan)
    block = math.ceil(n ** (1 / 3))
    n_blocks = math.ceil(n / block)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(reps, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    sample = net[idx.reshape(reps, -1)[:, :n]]
    gains = np.where(sample > 0, sample, 0).sum(axis=1)
    losses = -np.where(sample < 0, sample, 0).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(losses > 0, gains / losses, np.inf)


def drawdown_series(eq: np.ndarray) -> np.ndarray:
    peak = np.maximum.accumulate(eq)
    return (eq - peak) / peak


def compute(trades: pd.DataFrame, eq_daily: pd.Series, days_span: float, bootstrap: bool = True) -> dict[str, Any]:
    """Métricas de un periodo. eq_daily: equity diaria (encadenada si agrega segmentos)."""
    net = trades["net_usd"].to_numpy(float) if len(trades) else np.array([])
    r = trades["r_multiple"].to_numpy(float) if len(trades) else np.array([])
    eq = eq_daily.to_numpy(float)
    rets = eq[1:] / eq[:-1] - 1 if len(eq) > 1 else np.array([])
    dd = drawdown_series(eq)
    max_dd = float(-dd.min()) if len(dd) else 0.0
    peak = np.maximum.accumulate(eq)
    max_dd_usd = float((peak - eq).max()) if len(eq) else 0.0
    years = days_span / 365.25
    total = eq[-1] / eq[0] if len(eq) else 1.0
    cagr = total ** (1 / years) - 1 if years > 0 and total > 0 else float("nan")
    sd = rets.std(ddof=1) if len(rets) > 1 else float("nan")
    downside = math.sqrt(np.mean(np.minimum(rets, 0) ** 2)) if len(rets) else float("nan")
    out: dict[str, Any] = {
        "trades": int(len(net)),
        "net_usd": float(net.sum()),
        "pf": profit_factor(net) if len(net) else float("nan"),
        "win_rate": float((net > 0).mean()) if len(net) else float("nan"),
        "avg_win_usd": float(net[net > 0].mean()) if (net > 0).any() else float("nan"),
        "avg_loss_usd": float(net[net < 0].mean()) if (net < 0).any() else float("nan"),
        "expectancy_r": float(r.mean()) if len(r) else float("nan"),
        "sqn": float(math.sqrt(min(len(r), 100)) * r.mean() / r.std(ddof=1)) if len(r) > 1 and r.std(ddof=1) > 0 else float("nan"),
        "max_dd_pct": max_dd * 100,
        "max_dd_usd": max_dd_usd,
        "sharpe": float(rets.mean() / sd * math.sqrt(TRADING_DAYS)) if len(rets) > 1 and sd > 0 else float("nan"),
        "sortino": float(rets.mean() / downside * math.sqrt(TRADING_DAYS)) if len(rets) and downside > 0 else float("nan"),
        "cagr_pct": cagr * 100,
        "calmar": float(cagr / max_dd) if max_dd > 0 and np.isfinite(cagr) else float("nan"),
        "recovery_factor": float(net.sum() / max_dd_usd) if max_dd_usd > 0 else float("nan"),
        "ulcer_index": float(math.sqrt(np.mean((dd * 100) ** 2))) if len(dd) else float("nan"),
        "total_return_pct": (total - 1) * 100,
        "days": int(len(rets)),
        "commission_usd": float(trades["commission_usd"].sum()) if len(trades) else 0.0,
        "swap_usd": float(trades["swap_usd"].sum()) if len(trades) else 0.0,
        "skew": _moment(rets, 3),
        "kurtosis": _moment(rets, 4),
        "daily_sharpe": float(rets.mean() / sd) if len(rets) > 1 and sd > 0 else float("nan"),
    }
    if bootstrap and len(net) >= 2:
        boot = block_bootstrap_pf(net)
        out["pf_ci90_low"] = float(np.nanpercentile(boot, 5))
        out["pf_ci90_high"] = float(np.nanpercentile(boot, 95))
    else:
        out["pf_ci90_low"] = out["pf_ci90_high"] = float("nan")
    return out


def _moment(x: np.ndarray, k: int) -> float:
    """Asimetría (k=3) o curtosis no centrada en 3 (k=4) poblacionales."""
    if len(x) < 4 or x.std() == 0:
        return float("nan")
    z = (x - x.mean()) / x.std()
    return float(np.mean(z ** k))


def _passes(value: float, op: str, threshold: float) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return {">": value > threshold, ">=": value >= threshold, "<": value < threshold}[op]


def evaluate_thresholds(m: dict[str, Any]) -> dict[str, Any]:
    strict = {k: _passes(m[k], *rule) for k, rule in STRICT.items()}
    flexible = {k: _passes(m[k], *rule) for k, rule in FLEXIBLE.items()}
    return {"strict": strict, "flexible": flexible,
            "strict_failed": [k for k, v in strict.items() if not v],
            "flexible_failed": [k for k, v in flexible.items() if not v]}


def verdict(m: dict[str, Any], dsr: float | None) -> tuple[str, str]:
    """Criterio de la sección 6 del pre-registro, más la regla de DSR de la sección 7."""
    t = evaluate_thresholds(m)
    n_strict, n_flex = len(t["strict_failed"]), len(t["flexible_failed"])
    if n_strict == 0:
        if dsr is not None and np.isfinite(dsr) and dsr < 0.95:
            return "INCONCLUSIVE", f"cumple las estrictas pero DSR {dsr:.3f} < 0,95"
        return "CANDIDATE_FOR_PAPER", "cumple todas las estrictas"
    if n_strict <= 2 and n_flex == 0:
        return "INCONCLUSIVE", f"falla {n_strict} estricta(s) y cumple las flexibles"
    if n_strict > 2:
        return "REJECTED", f"falla {n_strict} estrictas"
    return "REJECTED", f"falla {n_strict} estricta(s) y {n_flex} flexible(s)"


def deflated_sharpe(sr: float, n_obs: int, skew: float, kurt: float, trial_srs: list[float]) -> float:
    """DSR de Bailey y López de Prado (2014) con Sharpe por periodo (no anualizado).

    trial_srs: Sharpe por periodo de las N variantes probadas (incluida esta).
    """
    n = len(trial_srs)
    if n_obs < 3 or not np.isfinite(sr) or n < 1:
        return float("nan")
    var_sr = float(np.var(trial_srs, ddof=1)) if n > 1 else 0.0
    gamma = 0.5772156649015329
    if n > 1:
        z1 = _N.inv_cdf(1 - 1 / n)
        z2 = _N.inv_cdf(1 - 1 / (n * math.e))
        sr0 = math.sqrt(var_sr) * ((1 - gamma) * z1 + gamma * z2)
    else:
        sr0 = 0.0
    denom = math.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr ** 2, 1e-12))
    return float(_N.cdf((sr - sr0) * math.sqrt(n_obs - 1) / denom))
