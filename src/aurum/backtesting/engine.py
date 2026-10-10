"""Motor de backtesting cronológico sobre barras M1 bid.

Supuestos (docs/BACKTEST_ENGINE.md):
- Precios de las barras = bid. ask = bid + spread estimado del minuto (SpreadModel).
- Una señal conocida en T se ejecuta a la apertura de la primera barra con hora >= T,
  nunca antes. Sin barra en max_entry_delay_s, la señal se rechaza.
- Compra al ask y cierre al bid; venta al bid y cierre al ask. Stops y objetivos se
  comparan con el lado de cierre, como en MT5.
- Stops y órdenes a mercado sufren slippage en contra; los objetivos (límite) no.
- Hueco en la apertura más allá del stop: se cierra a la apertura (peor que el stop).
- Stop y objetivo en la misma barra: se resuelve con ticks si cubren el minuto por
  completo; si no, gana el stop (supuesto conservador). Se cuentan ambos casos.
- Comisión por lado: al abrir y al cerrar. Swap en cada cambio de día del servidor con
  posición abierta (de lunes a viernes; triple el día configurado por el bróker).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import pandas as pd

from aurum.backtesting.spread_model import SpreadModel
from aurum.backtesting.types import BacktestResult, CostScenario, ExecutionConfig, RiskConfig, Signal
from aurum.risk.sizing import Instrument, size_by_risk

DAY = 86400
TickProvider = Callable[[int], pd.DataFrame | None]   # minuto (time_raw) -> ticks time_msc, bid, ask


class DataIntegrityError(ValueError):
    """Barras desordenadas, duplicadas o con precios inválidos."""


def check_bars(bars: pd.DataFrame) -> None:
    t = bars["time_raw"].to_numpy(np.int64)
    if len(t) == 0:
        raise DataIntegrityError("no hay barras")
    if np.any(np.diff(t) <= 0):
        raise DataIntegrityError("barras desordenadas o duplicadas")
    px = bars[["open", "high", "low", "close"]].to_numpy(float)
    if not np.isfinite(px).all() or (px <= 0).any():
        raise DataIntegrityError("precios no finitos o no positivos")
    o, h, lo, c = px.T
    if np.any((h < np.maximum(o, c)) | (lo > np.minimum(o, c))):
        raise DataIntegrityError("OHLC incoherente")


def _weekday(day_index: int) -> int:
    return (day_index + 3) % 7   # el epoch 0 fue jueves; lunes = 0


class Backtester:
    def __init__(self, instrument: Instrument, spread_model: SpreadModel, scenario: CostScenario,
                 execution: ExecutionConfig | None = None, risk: RiskConfig | None = None,
                 tick_provider: TickProvider | None = None):
        self.ins = instrument
        self.spread_model = spread_model
        self.sc = scenario
        self.ex = execution or ExecutionConfig()
        self.risk = risk or RiskConfig()
        self.ticks = tick_provider

    # --- auxiliares ------------------------------------------------------------
    def _swap_usd(self, side: int, volume: float, prev_day: int, cur_day: int) -> float:
        nights = 0
        for d in range(prev_day, cur_day):
            wd = _weekday(d)
            if wd < 5:
                nights += 3 if wd == self.ins.swap_triple_weekday else 1
        points = self.ins.swap_long_points if side == 1 else self.ins.swap_short_points
        return nights * points * self.ins.point * self.ins.value_per_price_unit(volume) * self.sc.swap_multiplier

    def _resolve_with_ticks(self, minute: int, side: int, sl: float, tp: float, bar_h: float,
                            bar_l: float) -> str | None:
        """'sl', 'tp', 'none' según el orden real de los ticks, o None si no son fiables."""
        if not (self.ex.use_ticks_intrabar and self.ticks):
            return None
        ticks = self.ticks(minute)
        if ticks is None or ticks.empty:
            return None
        bid, ask = ticks["bid"].to_numpy(), ticks["ask"].to_numpy()
        # Solo si los ticks reproducen el máximo y mínimo de la barra (minuto completo).
        if abs(bid.max() - bar_h) > 0.005 or abs(bid.min() - bar_l) > 0.005:
            return None
        px = bid if side == 1 else ask
        hit_sl = px <= sl if side == 1 else px >= sl
        hit_tp = px >= tp if side == 1 else px <= tp
        i_sl = np.argmax(hit_sl) if hit_sl.any() else len(px)
        i_tp = np.argmax(hit_tp) if hit_tp.any() else len(px)
        if i_sl == i_tp == len(px):
            return "none"
        return "sl" if i_sl <= i_tp else "tp"

    # --- simulación --------------------------------------------------------------
    def run(self, bars: pd.DataFrame, signals: Sequence[Signal]) -> BacktestResult:
        check_bars(bars)
        ins, sc, ex, rk = self.ins, self.sc, self.ex, self.risk
        times = bars["time_raw"].to_numpy(np.int64)
        o, h, lo, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        spread_pts = self.spread_model.spread_points(times, bars["spread"].to_numpy(float), sc.spread_excess)
        spread = spread_pts * sc.spread_multiplier * ins.point
        slip = sc.slippage_points * ins.point
        n = len(times)
        equity = np.empty(n)

        sigs = sorted(signals, key=lambda s: s.decision_time)
        trades: list[dict[str, Any]] = []
        rejections: list[dict[str, Any]] = []
        stats = {"same_bar_ambiguous": 0, "same_bar_resolved_by_ticks": 0, "same_bar_by_policy": 0,
                 "gap_exits": 0}
        balance = rk.initial_balance
        peak = balance
        halted = False

        def day_start_equity(j: int) -> float:
            # Equity al cierre de la primera barra del día del servidor (o el balance actual
            # si la señal llega en esa primera barra).
            first = int(np.searchsorted(times, (times[j] // DAY) * DAY, side="left"))
            return float(equity[first]) if first < j else balance

        def reject(s: Signal, reason: str) -> None:
            rejections.append({"decision_time": s.decision_time, "side": s.side, "tag": s.tag, "reason": reason})

        k, p = 0, 0
        while k < n:
            # ---------- sin posición: buscar la siguiente señal ejecutable ----------
            if p >= len(sigs):
                equity[k:] = balance
                break
            s = sigs[p]
            p += 1
            if s.info_time > s.decision_time:
                reject(s, "usa información posterior a la decisión (fuga)")
                continue
            j = int(np.searchsorted(times, s.decision_time, side="left"))
            equity[k:j] = balance
            k = max(k, j)
            if j >= n:
                reject(s, "sin barras posteriores a la señal")
                continue
            if times[j] - s.decision_time > ex.max_entry_delay_s:
                reject(s, "sin precio válido dentro del retraso máximo")
                continue
            if halted:
                reject(s, "drawdown máximo alcanzado: entradas detenidas")
                continue
            start_eq = day_start_equity(j)
            if rk.daily_loss_fraction is not None and balance - start_eq <= -rk.daily_loss_fraction * start_eq:
                reject(s, "límite de pérdida diaria alcanzado")
                continue

            side = s.side
            bid_o = o[j]
            ask_o = bid_o + spread[j]
            entry = ask_o + slip if side == 1 else bid_o - slip
            ref_close = bid_o if side == 1 else ask_o      # precio de cierre en ese instante
            tp = s.take_profit
            if (side == 1 and (s.stop >= ref_close or (tp is not None and tp <= ref_close))) or \
               (side == -1 and (s.stop <= ref_close or (tp is not None and tp >= ref_close))):
                reject(s, "stop u objetivo en el lado equivocado del precio al ejecutar")
                continue
            stop_fill = s.stop - slip if side == 1 else s.stop + slip
            round_trip_comm_per_lot = 2 * sc.commission_side(1.0)
            if rk.sizing_mode == "risk":
                sz = size_by_risk(ins, balance, rk.risk_per_trade_fraction, entry, stop_fill,
                                  round_trip_comm_per_lot)
                if sz.reason:
                    reject(s, sz.reason)
                    continue
                volume = sz.volume
            else:
                volume = ins.floor_volume(rk.fixed_volume)
                if volume < ins.volume_min - 1e-12:
                    reject(s, "volumen fijo por debajo del mínimo")
                    continue
            if ins.margin(volume, ask_o) > balance:
                reject(s, "margen insuficiente")
                continue

            # ---------- posición abierta ----------
            comm_in = sc.commission_side(volume)
            balance -= comm_in
            vpp = ins.value_per_price_unit(volume)
            initial_risk = abs(entry - stop_fill) * vpp + 2 * comm_in
            swap_total = 0.0
            exit_price = exit_reason = None
            last_day = int(times[j] // DAY)
            k = j
            while k < n:
                day = int(times[k] // DAY)
                if day != last_day:
                    sw = self._swap_usd(side, volume, last_day, day)
                    balance += sw
                    swap_total += sw
                    last_day = day
                bo, bh, bl = o[k], h[k], lo[k]
                spr = spread[k]
                close_o, close_h, close_l = (bo, bh, bl) if side == 1 else (bo + spr, bh + spr, bl + spr)
                if k > j:
                    if s.max_hold_s is not None and times[k] - times[j] >= s.max_hold_s:
                        exit_price, exit_reason = close_o - side * slip, "tiempo"
                    elif (side == 1 and close_o <= s.stop) or (side == -1 and close_o >= s.stop):
                        exit_price, exit_reason = close_o - side * slip, "stop (hueco)"
                        stats["gap_exits"] += 1
                    elif tp is not None and ((side == 1 and close_o >= tp) or (side == -1 and close_o <= tp)):
                        exit_price, exit_reason = tp, "objetivo (hueco)"
                if exit_price is None:
                    hit_sl = close_l <= s.stop if side == 1 else close_h >= s.stop
                    hit_tp = tp is not None and (close_h >= tp if side == 1 else close_l <= tp)
                    outcome = None
                    if hit_sl and hit_tp:
                        stats["same_bar_ambiguous"] += 1
                        outcome = self._resolve_with_ticks(int(times[k]), side, s.stop, tp, bh, bl)
                        if outcome is None:
                            stats["same_bar_by_policy"] += 1
                            outcome = "sl"
                        else:
                            stats["same_bar_resolved_by_ticks"] += 1
                    elif hit_sl:
                        outcome = "sl"
                    elif hit_tp:
                        outcome = "tp"
                    if outcome == "sl":
                        exit_price, exit_reason = stop_fill, "stop"
                    elif outcome == "tp":
                        exit_price, exit_reason = tp, "objetivo"
                if exit_price is not None:
                    break
                close_px = c[k] if side == 1 else c[k] + spr
                equity[k] = balance + side * (close_px - entry) * vpp
                k += 1
            if exit_price is None:
                k = n - 1
                close_px = c[k] if side == 1 else c[k] + spread[k]
                exit_price, exit_reason = close_px - side * slip, "fin de datos"
            gross = side * (exit_price - entry) * vpp
            comm_out = sc.commission_side(volume)
            balance += gross - comm_out
            equity[k] = balance
            net = gross - comm_in - comm_out + swap_total
            trades.append({
                "entry_time": int(times[j]), "exit_time": int(times[k]), "side": side, "volume": volume,
                "entry_price": entry, "exit_price": exit_price, "stop": s.stop, "take_profit": tp,
                "spread_entry_points": spread[j] / ins.point, "gross_usd": gross,
                "commission_usd": comm_in + comm_out, "swap_usd": swap_total, "net_usd": net,
                "r_multiple": net / initial_risk if initial_risk else np.nan,
                "exit_reason": exit_reason, "tag": s.tag, "decision_time": s.decision_time,
            })
            peak = max(peak, balance)
            if rk.max_drawdown_fraction is not None and balance <= peak * (1 - rk.max_drawdown_fraction):
                halted = True
            # señales que llegaron con la posición abierta
            while p < len(sigs) and sigs[p].decision_time <= times[k]:
                reject(sigs[p], "posición abierta")
                p += 1
            k += 1

        eq = pd.DataFrame({"time_raw": times, "equity": equity})
        result = BacktestResult(pd.DataFrame(trades), eq, pd.DataFrame(rejections), stats)
        result.stats.update({
            "initial_balance": rk.initial_balance, "final_balance": balance, "trades": len(trades),
            "rejected_signals": len(rejections), "scenario": sc.name, "halted_by_drawdown": halted,
        })
        return result


def ledger_matches_equity(result: BacktestResult, tol: float = 1e-6) -> bool:
    """El balance final debe ser el inicial más la suma neta de las operaciones, y el último
    punto de la curva de equity debe coincidir con él (sin posición abierta al final)."""
    net = float(result.trades["net_usd"].sum()) if len(result.trades) else 0.0
    final = result.stats["final_balance"]
    return (abs(result.stats["initial_balance"] + net - final) <= tol
            and abs(float(result.equity["equity"].iloc[-1]) - final) <= tol)
