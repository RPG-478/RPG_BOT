"""Combat-related domain logic."""

from .damage import calculate_physical_damage, calculate_raw_physical_hit, mitigate_physical_damage

__all__ = [
    "calculate_physical_damage",
    "calculate_raw_physical_hit",
    "mitigate_physical_damage",
]
