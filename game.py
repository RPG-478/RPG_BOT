"""Compatibility shim for legacy game module.

This file is intentionally small.

Why:
- The original `game.py` grew very large (data + logic mixed).
- We keep `import game` working for the rest of the bot.

How it works:
- Load ITEMS_DATABASE / ENEMY_ZONES from rpg/data/*.json (single source of truth).
- Import `legacy_game` for the rest of the logic.
- Patch legacy globals so its functions use the loaded data.
- Re-export legacy public symbols.
"""

from __future__ import annotations

from typing import Any

import legacy_game as _legacy


def _load_items() -> dict[str, Any]:
    from rpg.data.items import load_items

    data = load_items()
    if not isinstance(data, dict) or not data:
        raise ValueError("rpg/data/items.json is empty or invalid")
    return data


def _load_enemy_zones() -> dict[str, Any]:
    from rpg.data.enemies import load_enemy_zones

    data = load_enemy_zones()
    if not isinstance(data, dict) or not data:
        raise ValueError("rpg/data/enemies.json is empty or invalid")
    return data


# Single source of truth (data)
ITEMS_DATABASE = _load_items()
ENEMY_ZONES = _load_enemy_zones()

# Patch legacy globals so legacy functions operate on the new data
_legacy.ITEMS_DATABASE = ITEMS_DATABASE
_legacy.ENEMY_ZONES = ENEMY_ZONES


# Re-export legacy public API
for _name in dir(_legacy):
    if _name.startswith("_"):
        continue
    if _name in {"ITEMS_DATABASE", "ENEMY_ZONES"}:
        continue
    globals()[_name] = getattr(_legacy, _name)

__all__ = [
    "ITEMS_DATABASE",
    "ENEMY_ZONES",
] + [n for n in dir(_legacy) if not n.startswith("_") and n not in {"ITEMS_DATABASE", "ENEMY_ZONES"}]
