from __future__ import annotations

import random
import re


def get_enemy_type(enemy_name):
    """敵の名前からタイプを判定"""
    enemy_name_lower = enemy_name.lower()

    # アンデッド系
    undead_keywords = [
        "ゴースト",
        "スケルトン",
        "ゾンビ",
        "リッチ",
        "デスナイト",
        "デスロード",
        "デスエンペラー",
        "不死",
        "死神",
    ]
    for keyword in undead_keywords:
        if keyword in enemy_name:
            return "undead"

    # ドラゴン系
    dragon_keywords = ["ドラゴン", "竜", "龍", "ワイバーン"]
    for keyword in dragon_keywords:
        if keyword in enemy_name:
            return "dragon"

    # 闇属性
    dark_keywords = ["ダーク", "闇", "シャドウ", "影", "黒騎士"]
    for keyword in dark_keywords:
        if keyword in enemy_name:
            return "dark"

    return "normal"


def apply_ability_effects(damage, ability_text, attacker_hp, target_type="normal"):
    """
    ability効果を適用してダメージと追加効果を計算

    Args:
        damage: 基本ダメージ
        ability_text: ability説明文
        attacker_hp: 攻撃者のHP（HP吸収用）
        target_type: 対象タイプ（"normal", "undead", "dragon"など）

    Returns:
        dict: {
            "damage": 最終ダメージ,
            "lifesteal": HP吸収量,
            "burn": 燃焼ダメージ（追加効果）, 
            "poison": 毒ダメージ（追加効果）, 
            "instant_kill": 即死判定,
            "effect_text": 効果説明テキスト
        }
    """

    result = {
        "damage": damage,
        "lifesteal": 0,
        "burn": 0,
        "poison": 0,
        "instant_kill": False,
        "effect_text": "",
    }

    if not ability_text or ability_text == "なし" or ability_text == "素材":
        return result

    # 炎ダメージ（追加で炎ダメージ+X）
    fire_match = re.search(r"炎ダメージ\+(\d+)", ability_text)
    if fire_match:
        fire_damage = int(fire_match.group(1))
        result["damage"] += fire_damage
        result["effect_text"] += f"🔥炎+{fire_damage} "

    # 燃焼状態（攻撃時X%で敵を燃焼）
    burn_match = re.search(r"攻撃時(\d+)%で(?:敵を)?燃焼.*?ダメージ(\d+)", ability_text)
    if burn_match:
        burn_chance = int(burn_match.group(1))
        burn_damage = int(burn_match.group(2))
        if random.randint(1, 100) <= burn_chance:
            result["burn"] = burn_damage
            result["effect_text"] += "🔥燃焼付与! "

    # 毒付与
    poison_match = re.search(r"毒付与.*?(\d+)%", ability_text)
    if poison_match:
        poison_chance = int(poison_match.group(1))
        if random.randint(1, 100) <= poison_chance:
            result["poison"] = 10
            result["effect_text"] += "☠️毒付与! "

    # HP吸収
    lifesteal_match = re.search(r"HP吸収.*?(\d+)%", ability_text)
    if lifesteal_match:
        lifesteal_percent = int(lifesteal_match.group(1))
        result["lifesteal"] = int(damage * lifesteal_percent / 100)
        result["effect_text"] += f"💉HP吸収{result['lifesteal']} "

    # 即死効果
    instant_kill_match = re.search(r"攻撃時(\d+)%で即死", ability_text)
    if instant_kill_match:
        kill_chance = int(instant_kill_match.group(1))
        if random.randint(1, 100) <= kill_chance:
            result["instant_kill"] = True
            result["effect_text"] += "💀即死発動! "

    # アンデッド特効
    if target_type == "undead" and "アンデッド特効" in ability_text:
        undead_match = re.search(r"アンデッド.*?\+(\d+)%", ability_text)
        if undead_match:
            bonus_percent = int(undead_match.group(1))
            bonus_damage = int(damage * bonus_percent / 100)
            result["damage"] += bonus_damage
            result["effect_text"] += f"⚰️特効+{bonus_damage} "

    # ドラゴン特効
    if target_type == "dragon" and "ドラゴン特効" in ability_text:
        dragon_match = re.search(r"ドラゴン.*?\+(\d+)%", ability_text)
        if dragon_match:
            bonus_percent = int(dragon_match.group(1))
            bonus_damage = int(damage * bonus_percent / 100)
            result["damage"] += bonus_damage
            result["effect_text"] += f"🐉特効+{bonus_damage} "

    # 闇属性特効
    if target_type == "dark" and "闇" in ability_text:
        dark_match = re.search(r"闇.*?\+(\d+)%", ability_text)
        if dark_match:
            bonus_percent = int(dark_match.group(1))
            bonus_damage = int(damage * bonus_percent / 100)
            result["damage"] += bonus_damage
            result["effect_text"] += f"🌑特効+{bonus_damage} "

    # クリティカル率アップ
    if "クリティカル率" in ability_text:
        crit_match = re.search(r"クリティカル率\+(\d+)%", ability_text)
        if crit_match:
            crit_chance = int(crit_match.group(1))
            if random.randint(1, 100) <= crit_chance:
                crit_damage = int(damage * 0.5)
                result["damage"] += crit_damage
                result["effect_text"] += f"💥クリティカル+{crit_damage} "

    # クリティカル時ダメージ3倍
    if "クリティカル時ダメージ3倍" in ability_text:
        if random.randint(1, 100) <= 20:
            triple_damage = int(damage * 2)
            result["damage"] += triple_damage
            result["effect_text"] += f"💥💥クリティカル3倍+{triple_damage} "

    # 凍結効果（攻撃時X%で敵を凍結）
    freeze_match = re.search(r"攻撃時(\d+)%で(?:敵を)?凍結", ability_text)
    if freeze_match:
        freeze_chance = int(freeze_match.group(1))
        if random.randint(1, 100) <= freeze_chance:
            result["freeze"] = True
            result["effect_text"] += "❄️凍結! "

    # 麻痺効果（攻撃時X%で敵を麻痺）
    paralyze_match = re.search(r"攻撃時(\d+)%で(?:敵を)?麻痺", ability_text)
    if paralyze_match:
        paralyze_chance = int(paralyze_match.group(1))
        if random.randint(1, 100) <= paralyze_chance:
            result["paralyze"] = True
            result["effect_text"] += "⚡麻痺! "

    # 分身攻撃（2回攻撃）
    if "分身攻撃" in ability_text and "2回攻撃" in ability_text:
        result["double_attack"] = True
        result["damage"] = int(damage * 2)
        result["effect_text"] += "👥分身攻撃×2! "

    # 3回攻撃
    if "3回攻撃" in ability_text:
        result["triple_attack"] = True
        result["damage"] = int(damage * 3)
        result["effect_text"] += "👥👥3連撃! "

    # 防御力無視
    if "防御無視" in ability_text or "防御力無視" in ability_text:
        if "攻撃時" in ability_text:
            ignore_match = re.search(r"攻撃時(\d+)%で敵の防御力無視", ability_text)
            if ignore_match:
                ignore_chance = int(ignore_match.group(1))
                if random.randint(1, 100) <= ignore_chance:
                    result["defense_ignore"] = True
                    result["effect_text"] += "🔓防御無視! "
        else:
            result["defense_ignore"] = True
            result["effect_text"] += "🔓防御無視! "

    # MP吸収
    mp_drain_match = re.search(r"(?:攻撃時)?敵のMP-(\d+)", ability_text)
    if mp_drain_match:
        mp_drain = int(mp_drain_match.group(1))
        result["mp_drain"] = mp_drain
        result["effect_text"] += f"🔵MP吸収{mp_drain} "

    # MP吸収（パーセント版）
    mp_absorb_match = re.search(r"MP吸収(\d+)%", ability_text)
    if mp_absorb_match:
        mp_percent = int(mp_absorb_match.group(1))
        result["mp_absorb_percent"] = mp_percent
        result["effect_text"] += f"🔵MP吸収{mp_percent}% "

    # アンデッド召喚
    if "アンデッド召喚" in ability_text:
        summon_match = re.search(r"攻撃時(\d+)%でアンデッド召喚.*?HP(\d+)回復", ability_text)
        if summon_match:
            summon_chance = int(summon_match.group(1))
            heal_amount = int(summon_match.group(2))
            if random.randint(1, 100) <= summon_chance:
                result["summon_heal"] = heal_amount
                result["effect_text"] += f"💀召喚HP+{heal_amount} "

    # 竜の咆哮（敵怯み）
    if "竜の咆哮" in ability_text:
        if random.randint(1, 100) <= 30:
            result["enemy_flinch"] = True
            result["effect_text"] += "🐉咆哮(怯み)! "

    # 呪い（攻撃時にHP-1、ダメージ+50%）
    if "呪い" in ability_text and "攻撃時にHP-" in ability_text:
        curse_match = re.search(r"HP-(\d+).*?ダメージ\+(\d+)%", ability_text)
        if curse_match:
            hp_loss = int(curse_match.group(1))
            dmg_bonus = int(curse_match.group(2))
            bonus_damage = int(damage * dmg_bonus / 100)
            result["damage"] += bonus_damage
            result["self_damage"] = hp_loss
            result["effect_text"] += f"😈呪い+{bonus_damage}(自傷-{hp_loss}) "

    # ランダム効果（燃焼・毒・防御無視・分身攻撃のいずれか）
    if "ランダム効果" in ability_text or "毎攻撃ランダム追加効果" in ability_text:
        random_effect = random.choice(["burn", "poison", "defense_ignore", "double_attack"])
        if random_effect == "burn":
            result["burn"] = 15
            result["effect_text"] += "🔥ランダム:燃焼! "
        elif random_effect == "poison":
            result["poison"] = 15
            result["effect_text"] += "☠️ランダム:毒! "
        elif random_effect == "defense_ignore":
            result["defense_ignore"] = True
            result["effect_text"] += "🔓防御無視! "
        elif random_effect == "double_attack":
            if random.randint(1, 100) <= 40:
                result["double_attack"] = True
                result["damage"] = int(damage * 2)
                result["effect_text"] += "👥分身攻撃×2! "

    # ボス特効
    if "ボスに特効" in ability_text or "ボス特効" in ability_text:
        boss_match = re.search(r"ボス(?:に)?特効\+(\d+)%", ability_text)
        if boss_match and target_type == "boss":
            bonus_percent = int(boss_match.group(1))
            bonus_damage = int(damage * bonus_percent / 100)
            result["damage"] += bonus_damage
            result["effect_text"] += f"👑ボス特効+{bonus_damage} "

    # 全ステータス+X%
    if "全ステータス" in ability_text:
        stats_match = re.search(r"全ステータス\+(\d+)%", ability_text)
        if stats_match:
            stats_bonus = int(stats_match.group(1))
            bonus_damage = int(damage * stats_bonus / 100)
            result["damage"] += bonus_damage
            result["effect_text"] += f"✨全ステ+{stats_bonus}% "

    # 攻撃力+X%（デバフ防具）
    if "攻撃力+" in ability_text and "%" in ability_text:
        atk_match = re.search(r"攻撃力\+(\d+)%", ability_text)
        if atk_match:
            atk_bonus = int(atk_match.group(1))
            bonus_damage = int(damage * atk_bonus / 100)
            result["damage"] += bonus_damage
            result["effect_text"] += f"⚔️攻撃+{atk_bonus}% "

    # 初期化されていないフィールドを追加
    if "freeze" not in result:
        result["freeze"] = False
    if "double_attack" not in result:
        result["double_attack"] = False
    if "triple_attack" not in result:
        result["triple_attack"] = False
    if "defense_ignore" not in result:
        result["defense_ignore"] = False
    if "mp_drain" not in result:
        result["mp_drain"] = 0
    if "mp_absorb_percent" not in result:
        result["mp_absorb_percent"] = 0
    if "max_hp_damage" not in result:
        result["max_hp_damage"] = 0
    if "summon_heal" not in result:
        result["summon_heal"] = 0
    if "enemy_flinch" not in result:
        result["enemy_flinch"] = False
    if "self_damage" not in result:
        result["self_damage"] = 0
    if "paralyze" not in result:
        result["paralyze"] = False

    return result
