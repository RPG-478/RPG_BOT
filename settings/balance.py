"""Balance settings.

ゲームバランスに影響する確率・報酬レンジなどを集約します。
現段階では「ハードコードを定数参照へ置換」するだけで挙動は変えません。
"""

from __future__ import annotations

# 宝箱関連
TREASURE_RARE_CHANCE: float = 0.001

TREASURE_COIN_MIN: int = 30
TREASURE_COIN_MAX: int = 60

# 戦闘/リワード関連
FLEE_CHANCE_PERCENT: int = 20

# 報酬ゴールドレンジ
REWARD_GOLD_BOSS_MIN: int = 10000
REWARD_GOLD_BOSS_MAX: int = 20000

REWARD_GOLD_NORMAL_MIN: int = 500
REWARD_GOLD_NORMAL_MAX: int = 1000

# ダメージ軽減レンジ（例: 盾/装備/スキルなどで使われている）
DAMAGE_REDUCTION_HIGH_MIN: int = 40
DAMAGE_REDUCTION_HIGH_MAX: int = 70

DAMAGE_REDUCTION_MID_MIN: int = 30
DAMAGE_REDUCTION_MID_MAX: int = 60

DAMAGE_REDUCTION_LOW_MIN: int = 10
DAMAGE_REDUCTION_LOW_MAX: int = 50
