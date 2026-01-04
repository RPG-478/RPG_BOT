from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _data_path() -> Path:
    return Path(__file__).resolve().parent / "enemies.json"


def load_enemy_zones() -> dict[str, Any]:
    """Load enemy zones from JSON.

    This is intended as the new source of truth.
    Caller decides fallback behavior if the file is missing.
    """
    path = _data_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("enemies.json must be an object")
    return data
