"""Almacén Parquet de datos crudos de MT5 con manifiesto de procedencia.

Estructura (una sola fuente por directorio):

    data/raw/<servidor>/<símbolo>/bars/<TF>/<año>.parquet
    data/raw/<servidor>/<símbolo>/bars/<TF>/manifest.json
    data/raw/<servidor>/<símbolo>/ticks/<AAAA-MM-DD>.parquet
    data/raw/<servidor>/<símbolo>/ticks/manifest.json
    data/raw/<servidor>/<símbolo>/specs/<hash>.json

`time_raw` (barras) y `time_msc` (ticks) se guardan exactamente como los entrega la
API: epoch en hora del servidor del bróker. No se convierte a UTC aquí.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

UTC = dt.timezone.utc

BAR_COLUMNS = {
    "time_raw": "int64", "open": "float64", "high": "float64", "low": "float64", "close": "float64",
    "tick_volume": "int64", "spread": "int32", "real_volume": "int64",
}
TICK_COLUMNS = {
    "time_msc": "int64", "bid": "float64", "ask": "float64", "last": "float64",
    "volume": "int64", "flags": "int64", "volume_real": "float64",
}
MARKET_STATE_FIELDS = {"spread"}
TIME_CONVENTION ="epoch del servidor del broker tal como lo entrega la API de MT5 (sin convertir a UTC)"


class SourceMismatchError(RuntimeError):
    """Se intentó escribir datos de otra fuente en un conjunto existente."""


def rates_to_frame(rates: np.ndarray) -> pd.DataFrame:
    """Convierte el array estructurado de copy_rates_* a las columnas del almacén."""
    if rates is None or len(rates) == 0:
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in BAR_COLUMNS.items()})
    df = pd.DataFrame(rates)
    df = df.rename(columns={"time": "time_raw"})
    return df[list(BAR_COLUMNS)].astype(BAR_COLUMNS)


def ticks_to_frame(ticks: np.ndarray) -> pd.DataFrame:
    if ticks is None or len(ticks) == 0:
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in TICK_COLUMNS.items()})
    df = pd.DataFrame(ticks)
    return df[list(TICK_COLUMNS)].astype(TICK_COLUMNS)


def spec_hash(spec: dict[str, Any]) -> str:
    payload = json.dumps(spec, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _year_of(epoch: int) -> int:
    return dt.datetime.fromtimestamp(int(epoch), UTC).year


class Manifest:
    """Registro JSON de procedencia: fuente fija y una entrada por descarga."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"source": None, "downloads": []}
        )

    @property
    def source(self) -> dict[str, Any] | None:
        return self.data["source"]

    def ensure_source(self, source: dict[str, Any]) -> None:
        if self.source is None:
            self.data["source"] = source
            return
        for key in ("server", "symbol", "timeframe", "kind"):
            if self.source.get(key) != source.get(key):
                raise SourceMismatchError(
                    f"{self.path.parent}: {key}={source.get(key)!r} no coincide con {self.source.get(key)!r}"
                )

    def append(self, record: dict[str, Any]) -> None:
        self.data["downloads"].append(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(self.path)


class RawStore:
    def __init__(self, root: str | Path, server: str, symbol: str):
        self.base = Path(root) / server / symbol
        self.server = server
        self.symbol = symbol

    # --- especificaciones ---------------------------------------------------
    def save_spec(self, spec: dict[str, Any]) -> str:
        """Guarda una instantánea de especificaciones. El spread actual se excluye: cambia a cada tick."""
        spec = {k: v for k, v in spec.items() if k not in MARKET_STATE_FIELDS}
        h = spec_hash(spec)
        path = self.base / "specs" / f"{h}.json"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(spec, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return h

    def load_specs(self) -> dict[str, dict[str, Any]]:
        d = self.base / "specs"
        paths = d.glob("*.json") if d.exists() else []
        return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in paths}

    # --- barras ---------------------------------------------------------------
    def bars_dir(self, timeframe: str) -> Path:
        return self.base / "bars" / timeframe

    def bars_manifest(self, timeframe: str) -> Manifest:
        return Manifest(self.bars_dir(timeframe) / "manifest.json")

    def bar_files(self, timeframe: str) -> list[Path]:
        d = self.bars_dir(timeframe)
        return sorted(d.glob("[0-9][0-9][0-9][0-9].parquet")) if d.exists() else []

    def read_bars(self, timeframe: str, with_file: bool = False) -> pd.DataFrame:
        frames = []
        for path in self.bar_files(timeframe):
            df = pd.read_parquet(path)
            if with_file:
                df["_file"] = path.name
            frames.append(df)
        if not frames:
            return rates_to_frame(None)
        return pd.concat(frames, ignore_index=True)

    def last_bar_time(self, timeframe: str) -> int | None:
        files = self.bar_files(timeframe)
        if not files:
            return None
        df = pd.read_parquet(files[-1], columns=["time_raw"])
        return int(df["time_raw"].max()) if len(df) else None

    def append_bars(self, timeframe: str, new: pd.DataFrame, source: dict[str, Any]) -> None:
        """Añade barras nuevas (estrictamente posteriores a las guardadas) a su archivo anual."""
        if new.empty:
            return
        last = self.last_bar_time(timeframe)
        if last is not None and int(new["time_raw"].min()) <= last:
            raise ValueError("append_bars solo acepta barras posteriores a la última guardada")
        years = new["time_raw"].map(_year_of)
        for year, part in new.groupby(years):
            path = self.bars_dir(timeframe) / f"{year}.parquet"
            if path.exists():
                part = pd.concat([pd.read_parquet(path), part], ignore_index=True)
            self._write(path, part.reset_index(drop=True), {**source, "time_convention": TIME_CONVENTION})

    # --- ticks ----------------------------------------------------------------
    def ticks_dir(self) -> Path:
        return self.base / "ticks"

    def ticks_manifest(self) -> Manifest:
        return Manifest(self.ticks_dir() / "manifest.json")

    def tick_path(self, day: dt.date) -> Path:
        return self.ticks_dir() / f"{day.isoformat()}.parquet"

    def write_ticks(self, day: dt.date, ticks: pd.DataFrame, source: dict[str, Any]) -> None:
        self._write(self.tick_path(day), ticks, {**source, "time_convention": TIME_CONVENTION})

    def tick_days(self) -> list[dt.date]:
        d = self.ticks_dir()
        return sorted(dt.date.fromisoformat(p.stem) for p in d.glob("*.parquet")) if d.exists() else []

    def read_ticks(self, start: dt.date | None = None, end: dt.date | None = None) -> pd.DataFrame:
        d = self.ticks_dir()
        paths = sorted(d.glob("*.parquet")) if d.exists() else []
        frames = []
        for p in paths:
            day = dt.date.fromisoformat(p.stem)
            if (start and day < start) or (end and day > end):
                continue
            frames.append(pd.read_parquet(p))
        return pd.concat(frames, ignore_index=True) if frames else ticks_to_frame(None)

    @staticmethod
    def _write(path: Path, df: pd.DataFrame, metadata: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df, preserve_index=False)
        meta = dict(table.schema.metadata or {})
        meta[b"aurum"] = json.dumps(metadata, default=str).encode()
        tmp = path.with_suffix(".tmp")
        pq.write_table(table.replace_schema_metadata(meta), tmp)
        tmp.replace(path)
