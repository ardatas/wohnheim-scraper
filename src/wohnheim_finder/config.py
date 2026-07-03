from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping in {p}")
    return data


def load_applicant(path: str | Path) -> dict[str, Any]:
    data = load_yaml(path)
    data.setdefault("applicant", {})
    data.setdefault("truthful_reasons", [])
    data.setdefault("attachments", [])
    data.setdefault("tone", {})
    return data

