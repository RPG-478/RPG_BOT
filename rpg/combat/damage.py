from __future__ import annotations

import logging
import random

# Keep behavior compatible with legacy `game.py`.
try:
    import config  # type: ignore
except Exception:  # pragma: no cover
    config = None

logger = logging.getLogger("rpgbot")


def _verbose_debug_enabled() -> bool:
    try:
        return bool(getattr(config, "VERBOSE_DEBUG", False)) if config else False
    except Exception:
        return False


def _get_damage_model() -> str:
    model = getattr(config, "DAMAGE_MODEL", None) if config else None
    model = (model or "legacy").strip().lower()
    return model


def _get_attack_scale() -> float:
    value = getattr(config, "ATTACK_SCALE", 1.0) if config else 1.0
    try:
        return float(value)
    except Exception:
        return 1.0


def _get_defense_scale() -> float:
    value = getattr(config, "DEFENSE_SCALE", 1.0) if config else 1.0
    try:
        return float(value)
    except Exception:
        return 1.0


def _get_poe_armour_factor() -> float:
    value = getattr(config, "POE_ARMOUR_FACTOR", 5.0) if config else 5.0
    try:
        return float(value)
    except Exception:
        return 5.0


def _clamp_non_negative_int(value) -> int:
    try:
        value = int(value)
    except Exception:
        return 0
    return value if value > 0 else 0


def calculate_raw_physical_hit(attack: int, rand_min: int, rand_max: int, *, attack_scale: float | None = None) -> int:
    """防御の影響を入れない生ヒットダメージ（乱数込み）。"""
    if attack_scale is None:
        attack_scale = _get_attack_scale()

    scaled_attack = float(attack) * float(attack_scale)
    roll = random.randint(int(rand_min), int(rand_max))
    raw = scaled_attack + roll
    if _verbose_debug_enabled():
        logger.debug(
            "combat.raw_hit: atk=%s atk_scale=%s rand=[%s,%s] roll=%s raw=%s",
            attack,
            attack_scale,
            rand_min,
            rand_max,
            roll,
            raw,
        )
    return _clamp_non_negative_int(raw)


def mitigate_physical_damage(
    raw_damage: int,
    defense: int,
    *,
    model: str | None = None,
    defense_scale: float | None = None,
    poe_armour_factor: float | None = None,
) -> int:
    """生ダメージ(raw_damage)に対して、防御(defense)で軽減した最終ダメージを返す。"""
    raw_damage = _clamp_non_negative_int(raw_damage)
    if raw_damage <= 0:
        return 0

    if model is None:
        model = _get_damage_model()
    model = (model or "legacy").strip().lower()

    if defense_scale is None:
        defense_scale = _get_defense_scale()

    scaled_def = max(0.0, float(defense) * float(defense_scale))

    if _verbose_debug_enabled():
        logger.debug(
            "combat.mitigate.in: model=%s raw=%s def=%s def_scale=%s scaled_def=%s",
            model,
            raw_damage,
            defense,
            defense_scale,
            scaled_def,
        )

    if model == "legacy":
        out = _clamp_non_negative_int(raw_damage - int(scaled_def))
        if _verbose_debug_enabled():
            logger.debug("combat.mitigate.out: model=legacy out=%s", out)
        return out

    if model == "lol":
        # LoL: post = raw / (1 + armor/100)  (armor>=0 を想定)
        denom = 1.0 + (scaled_def / 100.0)
        if denom <= 0:
            return raw_damage
        out = _clamp_non_negative_int(raw_damage / denom)
        if _verbose_debug_enabled():
            logger.debug("combat.mitigate.out: model=lol denom=%s out=%s", denom, out)
        return out

    if model == "poe":
        # PoE: DR = A / (A + k*D), net = D*(1-DR) = k*D^2 / (A + k*D)
        if poe_armour_factor is None:
            poe_armour_factor = _get_poe_armour_factor()
        k = float(poe_armour_factor)
        denom = scaled_def + (k * float(raw_damage))
        if denom <= 0:
            return raw_damage
        net = (k * float(raw_damage) * float(raw_damage)) / denom
        out = _clamp_non_negative_int(net)
        if _verbose_debug_enabled():
            logger.debug(
                "combat.mitigate.out: model=poe k=%s denom=%s net=%s out=%s",
                k,
                denom,
                net,
                out,
            )
        return out

    # 不明なモデルは安全側で legacy
    return _clamp_non_negative_int(raw_damage - int(scaled_def))


def calculate_physical_damage(attack: int, defense: int, rand_min: int, rand_max: int, *, model: str | None = None) -> int:
    """攻撃ATKと防御DEFから物理ダメージを算出（乱数込み、モデル切替）。"""
    raw = calculate_raw_physical_hit(attack, rand_min, rand_max)
    out = mitigate_physical_damage(raw, defense, model=model)
    if _verbose_debug_enabled():
        logger.debug(
            "combat.damage: model=%s atk=%s def=%s rand=[%s,%s] raw=%s out=%s",
            model or _get_damage_model(),
            attack,
            defense,
            rand_min,
            rand_max,
            raw,
            out,
        )
    return out
