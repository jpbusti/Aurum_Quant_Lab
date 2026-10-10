"""Carga de configuraciones versionadas en configs/."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "configs"


def load_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: se esperaba un mapeo YAML en la raíz")
    return data


def load_data_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg = load_yaml(path or CONFIG_DIR / "data.yaml")
    for key in ("source", "symbol", "timeframes", "terminal"):
        if key not in cfg:
            raise ValueError(f"data.yaml: falta la sección {key!r}")
    # La ruta del terminal puede venir del entorno; nunca credenciales.
    env_path = os.environ.get("AURUM_MT5_PATH") or None
    if env_path and not cfg["terminal"].get("path"):
        cfg["terminal"]["path"] = env_path
    return cfg
