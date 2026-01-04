"""Compatibility facade for game APIs.

Goal:
- Allow new code to depend on rpg.* modules instead of the giant `game.py`.
- Keep existing call sites working without forced rewrites.

Note: This module intentionally re-exports from `game` for now.
"""

from __future__ import annotations

from typing import Any

# Re-export stable APIs from legacy module.
# NOTE: `game.py` will become a thin shim; use legacy_game to avoid circular imports.
import legacy_game as _legacy_game


def get_random_enemy(distance: int) -> dict[str, Any]:
    return _legacy_game.get_random_enemy(distance)


def get_random_enemy_by_region_level(region_level: int) -> dict[str, Any]:
    return _legacy_game.get_random_enemy_by_region_level(region_level)


def calculate_physical_damage(attack: int, defense: int, rand_min: int, rand_max: int, *, model: str | None = None) -> int:
    return _legacy_game.calculate_physical_damage(attack, defense, rand_min, rand_max, model=model)
