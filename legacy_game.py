import random
import copy
import logging

from rpg.combat import damage as _damage
from rpg.combat.ability_effects import apply_ability_effects, get_enemy_type

# 戦闘計算（ATK/DEF）を views 側の直書きから共通化するためのヘルパー
# ※既存挙動は config.DAMAGE_MODEL = "legacy" をデフォルトに維持
try:
    import config  # config は Supabase 必須のため、実行環境では常に存在する想定
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
    """防御の影響を入れない生ヒットダメージ（乱数込み）。

    NOTE: Implementation lives in rpg.combat.damage (split from game.py).
    """
    return _damage.calculate_raw_physical_hit(attack, rand_min, rand_max, attack_scale=attack_scale)


def mitigate_physical_damage(raw_damage: int, defense: int, *, model: str | None = None, defense_scale: float | None = None, poe_armour_factor: float | None = None) -> int:
    """生ダメージ(raw_damage)に対して、防御(defense)で軽減した最終ダメージを返す。

    NOTE: Implementation lives in rpg.combat.damage (split from game.py).
    """
    return _damage.mitigate_physical_damage(
        raw_damage,
        defense,
        model=model,
        defense_scale=defense_scale,
        poe_armour_factor=poe_armour_factor,
    )


def calculate_physical_damage(attack: int, defense: int, rand_min: int, rand_max: int, *, model: str | None = None) -> int:
    """攻撃ATKと防御DEFから物理ダメージを算出（乱数込み、モデル切替）。

    NOTE: Implementation lives in rpg.combat.damage (split from game.py).
    """
    return _damage.calculate_physical_damage(attack, defense, rand_min, rand_max, model=model)

ITEMS_DATABASE = {}

# Prefer external data files when present (keeps legacy literals as fallback during migration).
try:
    from rpg.data.items import load_items as _load_items

    _items = _load_items()
    if isinstance(_items, dict) and _items:
        ITEMS_DATABASE = _items
except Exception:
    # Keep legacy in-code ITEMS_DATABASE
    pass


ENEMY_ZONES = {}

# Prefer external data files when present (keeps legacy literals as fallback during migration).
try:
    from rpg.data.enemies import load_enemy_zones as _load_enemy_zones

    _zones = _load_enemy_zones()
    if isinstance(_zones, dict) and _zones:
        ENEMY_ZONES = _zones
except Exception:
    # Keep legacy in-code ENEMY_ZONES
    pass


def get_zone_from_distance(distance):
    if distance <= 1000:
        return "0-1000"
    elif distance <= 2000:
        return "1001-2000"
    elif distance <= 3000:
        return "2001-3000"
    elif distance <= 4000:
        return "3001-4000"
    elif distance <= 5000:
        return "4001-5000"
    elif distance <= 6000:
        return "5001-6000"
    elif distance <= 7000:
        return "6001-7000"
    elif distance <= 8000:
        return "7001-8000"
    elif distance <= 9000:
        return "8001-9000"
    elif distance <= 10000:
        return "9001-10000"
    else:
        return "9001-10000"


def get_random_enemy(distance):
    zone = get_zone_from_distance(distance)
    enemies = ENEMY_ZONES[zone]["enemies"]

    weights = [enemy["weight"] for enemy in enemies]
    selected_enemy = random.choices(enemies, weights=weights, k=1)[0]

    return {
        "name": selected_enemy["name"],
        "hp": selected_enemy["hp"],
        "atk": selected_enemy["atk"],
        "def": selected_enemy["def"],
        "drops": selected_enemy["drops"],
        "attribute": selected_enemy.get("attribute", "none")
    }


def _sorted_enemy_zone_keys() -> list[str]:
    """ENEMY_ZONES のキーを距離レンジ昇順に並べる（例: '0-1000', '1001-2000', ...）。"""
    def _start(k: str) -> int:
        try:
            return int(str(k).split("-", 1)[0])
        except Exception:
            return 10**18

    return sorted(list(ENEMY_ZONES.keys()), key=_start)


def get_enemy_zone_key_by_region_level(region_level: int) -> str:
    """地域レベル（1..）から敵ゾーンキーを返す。

    - region_level=1 → 一番低いゾーン（例: 0-1000）
    - region_level=2 → 次のゾーン（例: 1001-2000）
    ...
    """
    try:
        lvl = int(region_level)
    except Exception:
        lvl = 1
    if lvl < 1:
        lvl = 1

    keys = _sorted_enemy_zone_keys()
    if not keys:
        return "0-1000"
    idx = min(lvl - 1, len(keys) - 1)
    return keys[idx]


def get_random_enemy_by_region_level(region_level: int):
    """地域レベルに応じた敵を抽選（絵文字RPG向け）。"""
    zone_key = get_enemy_zone_key_by_region_level(region_level)
    enemies = ENEMY_ZONES.get(zone_key, {}).get("enemies")
    if not isinstance(enemies, list) or not enemies:
        # フォールバック
        return get_random_enemy(0)

    weights = [int(enemy.get("weight", 1) or 1) for enemy in enemies]
    selected_enemy = random.choices(enemies, weights=weights, k=1)[0]
    return {
        "name": selected_enemy.get("name", "敵"),
        "hp": int(selected_enemy.get("hp", 1) or 1),
        "atk": int(selected_enemy.get("atk", 1) or 1),
        "def": int(selected_enemy.get("def", 0) or 0),
        "drops": selected_enemy.get("drops", []),
        "attribute": selected_enemy.get("attribute", "none"),
    }


def get_enemy_drop(enemy_name, distance):
    zone = get_zone_from_distance(distance)
    enemies = ENEMY_ZONES[zone]["enemies"]

    enemy_data = None
    for enemy in enemies:
        if enemy["name"] == enemy_name:
            enemy_data = enemy
            break

    if not enemy_data or not enemy_data.get("drops"):
        return None

    drops = enemy_data["drops"]
    weights = [drop["weight"] for drop in drops]
    selected_drop = random.choices(drops, weights=weights, k=1)[0]

    if selected_drop["item"] == "coins":
        coin_amount = random.randint(selected_drop["amount"][0], selected_drop["amount"][1])
        return {"type": "coins", "amount": coin_amount}
    else:
        return {"type": "item", "name": selected_drop["item"]}


def get_treasure_box_equipment(distance):
    """宝箱から出る装備（武器・鎧・盾）のリストを返す"""
    zone = get_zone_from_distance(distance)
    enemies = ENEMY_ZONES[zone]["enemies"]
    
    # そのゾーンの敵がドロップする装備を収集
    """レアドロップ品: 毒の短剣、魔法の杖、幽霊の布、竜の鱗、死の鎧、血の剣、暗黒の弓、巨人の鎧、カオスブレード、神の盾、深淵の剣"""
    equipment_list = []
    for enemy in enemies:
        drops = enemy.get("drops", [])
        for drop in drops:
            item_name = drop.get("item")
            if item_name and item_name != "none" and item_name != "coins" and item_name != "毒の短剣" and item_name != "魔法の杖" and item_name != "幽霊の布" and item_name != "竜の鱗" and item_name != "死の鎧" and item_name != "血の剣" and item_name != "暗黒の弓" and item_name != "巨人の鎧" and item_name != "カオスブレード" and item_name != "神の盾" and item_name != "深淵の剣":
                item_info = get_item_info(item_name)
                if item_info and item_info.get("type") in ["weapon", "armor", "shield"]:
                    if item_name not in equipment_list:
                        equipment_list.append(item_name)
    
    return equipment_list if equipment_list else ["木の剣"]


def get_treasure_box_weapons(distance):
    """宝箱から出る武器のみのリストを返す（階層に応じた武器のみ）"""
    zone = get_zone_from_distance(distance)
    enemies = ENEMY_ZONES[zone]["enemies"]
    
    # そのゾーンの敵がドロップする武器のみを収集
    weapon_list = []
    for enemy in enemies:
        drops = enemy.get("drops", [])
        for drop in drops:
            item_name = drop.get("item")
            if item_name and item_name != "none" and item_name != "coins":
                item_info = get_item_info(item_name)
                if item_info and item_info.get("type") == "weapon":
                    if item_name not in weapon_list:
                        weapon_list.append(item_name)
    
    return weapon_list if weapon_list else ["木の剣"]


def get_item_info(item_name):
    info = ITEMS_DATABASE.get(item_name, None)
    if not info:
        return None
    # 互換: 盾アイテムは従来 armor 扱いだったため、名前で shield に分類する
    if info.get("type") == "armor" and isinstance(item_name, str) and "盾" in item_name:
        copied = info.copy()
        copied["type"] = "shield"
        return copied
    return info


def get_enemy_gold_drop(enemy_name, distance):
    """敵撃破時の確定ゴールドドロップ（ランダム範囲）を取得"""
    zone = get_zone_from_distance(distance)
    enemies = ENEMY_ZONES[zone]["enemies"]
    
    # 敵データを検索
    for enemy in enemies:
        if enemy["name"] == enemy_name:
            # dropsリストからcoinsの範囲を取得
            drops = enemy.get("drops", [])
            for drop in drops:
                if drop.get("item") == "coins" and "amount" in drop:
                    min_gold = drop["amount"][0]
                    max_gold = drop["amount"][1]
                    return random.randint(min_gold, max_gold)
            # coinsが見つからない場合はデフォルト値
            return random.randint(5, 15)
    
    # 敵が見つからない場合はデフォルト値
    return random.randint(5, 15)


from rpg.data.bosses import BOSS_DATA

SECRET_WEAPONS = [
    {"id": 1, "name": "シークレットソード#1", "attack": 40, "ability": "全能力+50%", "rarity": "伝説"},
    {"id": 2, "name": "シークレットソード#2", "attack": 50, "ability": "即死攻撃10%", "rarity": "伝説"},
    {"id": 3, "name": "シークレットソード#3", "attack": 45, "ability": "HP自動回復+10/ターン", "rarity": "伝説"},
    {"id": 4, "name": "シークレットソード#4", "attack": 40, "ability": "攻撃力+100%", "rarity": "神話"},
    {"id": 5, "name": "シークレットソード#5", "attack": 60, "ability": "防御無視攻撃", "rarity": "伝説"},
    {"id": 6, "name": "シークレットソード#6", "attack": 55, "ability": "全ステータス+80%", "rarity": "神話"},
    {"id": 7, "name": "シークレットソード#7", "attack": 65, "ability": "敵防御力無視", "rarity": "伝説"},
    {"id": 8, "name": "シークレットソード#8", "attack": 45, "ability": "クリティカル率100%", "rarity": "神話"},
    {"id": 9, "name": "シークレットソード#9", "attack": 40, "ability": "HP吸収50%", "rarity": "伝説"},
    {"id": 10, "name": "シークレットソード#10", "attack": 70, "ability": "真・無敵", "rarity": "超越"},
]

SPECIAL_EVENT_SHOP = [
    {"name": "魔力の剣", "type": "weapon", "price": 500, "attack": 25, "ability": "魔力+20%"},
    {"name": "聖なる盾", "type": "armor", "price": 450, "attack": 0, "defense": 18, "ability": "HP自動回復+5"},
    {"name": "破壊の斧", "type": "weapon", "price": 600, "attack": 30, "ability": "防御貫通30%"},
    {"name": "呪いの首輪", "type": "armor", "price": 300, "attack": 0, "defense": -10, "ability": "攻撃力+50%"},
    {"name": "狂戦士の鎧", "type": "armor", "price": 700, "attack": 0, "defense": -20, "ability": "攻撃力+100%"},
]

"""現在の素材27種類"""
from rpg.data.crafting import MATERIAL_PRICES, CRAFTING_RECIPES

# (moved to rpg.data.crafting)

def get_boss(stage):
    boss_template = BOSS_DATA.get(stage)
    if boss_template:
        # ディープコピーで新しいボスデータを返す
        return copy.deepcopy(boss_template)
    return None
    

def should_spawn_boss(distance):
    if distance < 980:
        return False
    remainder = distance % 1000
    # 980-1020の範囲（1000の±20）でボス発生
    return remainder <= 20 or remainder >= 980

def get_boss_stage(distance):
    """ボス戦の正しいステージ番号を取得（範囲ベース）"""
    return round(distance / 1000)

def is_special_event_distance(distance):
    if distance < 480:
        return False
    remainder = distance % 500
    # 480-520の範囲（500の±20）で特殊イベント発生
    in_event_range = remainder <= 20 or remainder >= 480
    # ただしボス範囲は除外
    in_boss_range = should_spawn_boss(distance)
    return in_event_range and not in_boss_range

def get_special_event_stage(distance):
    """特殊イベントの正しいステージ番号を取得（範囲ベース）"""
    return round(distance / 500)

def get_random_secret_weapon():
    if random.random() < 0.001:
        return random.choice(SECRET_WEAPONS)
    return None

def parse_ability_bonuses(ability_text):
    """ability文字列から数値ボーナスを解析"""
    import re
    bonuses = {
        'hp_bonus': 0,
        'attack_percent': 0,
        'defense_percent': 0,
        'damage_reduction': 0,
        'hp_regen': 0,
        'lifesteal_percent': 0
    }

    if not ability_text or ability_text == "なし" or ability_text == "素材":
        return bonuses

    hp_match = re.search(r'HP\+(\d+)', ability_text)
    if hp_match:
        bonuses['hp_bonus'] = int(hp_match.group(1))

    atk_match = re.search(r'攻撃力\+(\d+)%', ability_text)
    if atk_match:
        bonuses['attack_percent'] = int(atk_match.group(1))

    def_match = re.search(r'防御力\+(\d+)%', ability_text)
    if def_match:
        bonuses['defense_percent'] = int(def_match.group(1))

    dmg_red_match = re.search(r'(?:全ダメージ|被ダメージ)-(\d+)%', ability_text)
    if dmg_red_match:
        bonuses['damage_reduction'] = int(dmg_red_match.group(1))

    regen_match = re.search(r'HP(?:自動)?回復\+(\d+)', ability_text)
    if regen_match:
        bonuses['hp_regen'] = int(regen_match.group(1))

    lifesteal_match = re.search(r'HP吸収(?:.*?)?(\d+)%', ability_text)
    if lifesteal_match:
        bonuses['lifesteal_percent'] = int(lifesteal_match.group(1))

    return bonuses

async def calculate_equipment_bonus(user_id):
    """装備中のアイテムから攻撃力・防御力ボーナスと特殊効果を計算"""
    import db
    equipped = await db.get_equipped_items(user_id)

    attack_bonus = 0
    defense_bonus = 0
    total_bonuses = {
        'hp_bonus': 0,
        'attack_percent': 0,
        'defense_percent': 0,
        'damage_reduction': 0,
        'hp_regen': 0,
        'lifesteal_percent': 0
    }

    weapon_ability = ""
    armor_ability = ""
    shield_ability = ""

    if equipped.get('weapon'):
        weapon_info = get_item_info(equipped['weapon'])
        if weapon_info:
            attack_bonus = weapon_info.get('attack', 0)
            weapon_ability = weapon_info.get('ability', '')
            weapon_bonuses = parse_ability_bonuses(weapon_ability)
            for key in total_bonuses:
                total_bonuses[key] += weapon_bonuses[key]

    if equipped.get('armor'):
        armor_info = get_item_info(equipped['armor'])
        if armor_info:
            defense_bonus += armor_info.get('defense', 0)
            armor_ability = armor_info.get('ability', '')
            armor_bonuses = parse_ability_bonuses(armor_ability)
            for key in total_bonuses:
                total_bonuses[key] += armor_bonuses[key]

    if equipped.get('shield'):
        shield_info = get_item_info(equipped['shield'])
        if shield_info:
            defense_bonus += shield_info.get('defense', 0)
            shield_ability = shield_info.get('ability', '')
            shield_bonuses = parse_ability_bonuses(shield_ability)
            for key in total_bonuses:
                total_bonuses[key] += shield_bonuses[key]

    return {
        'attack_bonus': attack_bonus,
        'defense_bonus': defense_bonus,
        'weapon_ability': weapon_ability,
        'armor_ability': armor_ability,
        'shield_ability': shield_ability,
        **total_bonuses
    }


STORY_TRIGGERS = [
    {"distance": 100, "story_id": "voice_1", "exact_match": False},
    {"distance": 777, "story_id": "lucky_777", "exact_match": True},
    {"distance": 250, "story_id": "story_250", "exact_match": False},
    {"distance": 750, "story_id": "story_750", "exact_match": False},
    {"distance": 1250, "story_id": "story_1250", "exact_match": False},
    {"distance": 1750, "story_id": "story_1750", "exact_match": False},
    {"distance": 2250, "story_id": "story_2250", "exact_match": False},
    {"distance": 2750, "story_id": "story_2750", "exact_match": False},
    {"distance": 3250, "story_id": "story_3250", "exact_match": False},
    {"distance": 3750, "story_id": "story_3750", "exact_match": False},
    {"distance": 4250, "story_id": "story_4250", "exact_match": False},
    {"distance": 4750, "story_id": "story_4750", "exact_match": False},
    {"distance": 5250, "story_id": "story_5250", "exact_match": False},
    {"distance": 5750, "story_id": "story_5750", "exact_match": False},
    {"distance": 6250, "story_id": "story_6250", "exact_match": False},
    {"distance": 6750, "story_id": "story_6750", "exact_match": False},
    {"distance": 7250, "story_id": "story_7250", "exact_match": False},
    {"distance": 7750, "story_id": "story_7750", "exact_match": False},
    {"distance": 8250, "story_id": "story_8250", "exact_match": False},
    {"distance": 8750, "story_id": "story_8750", "exact_match": False},
    {"distance": 9250, "story_id": "story_9250", "exact_match": False},
    {"distance": 9750, "story_id": "story_9750", "exact_match": False},
]


def apply_armor_effects(incoming_damage, armor_ability, defender_hp, max_hp, attacker_damage=0, attack_attribute="none"):
    """
    防具のアビリティ効果を適用

    Args:
        incoming_damage: 受けるダメージ
        armor_ability: 防具のアビリティ文字列
        defender_hp: 防御者の現在HP
        max_hp: 防御者の最大HP
        attacker_damage: 攻撃者が与えたダメージ（反撃用）
        attack_attribute: 攻撃の属性 (none, fire, ice, thunder, dark, water, etc.)

    Returns:
        dict: {
            "damage": 最終ダメージ,
            "evaded": 回避したか,
            "counter_damage": 反撃ダメージ,
            "reflect_damage": 反射ダメージ,
            "hp_regen": HP回復量,
            "revived": 蘇生したか,
            "effect_text": 効果説明テキスト
        }
    """
    import re

    result = {
        "damage": incoming_damage,
        "evaded": False,
        "counter_damage": 0,
        "reflect_damage": 0,
        "hp_regen": 0,
        "revived": False,
        "effect_text": ""
    }

    if not armor_ability or armor_ability == "なし" or armor_ability == "素材":
        return result

    # 回避率
    evasion_match = re.search(r'回避率\+(\d+)%', armor_ability)
    if evasion_match:
        evasion_chance = int(evasion_match.group(1))
        if random.randint(1, 100) <= evasion_chance:
            result["evaded"] = True
            result["damage"] = 0
            result["effect_text"] += "💨回避! "
            return result

    # 幻影分身（被攻撃時X%で回避）
    phantom_match = re.search(r'被攻撃時(\d+)%で(?:完全)?回避', armor_ability)
    if phantom_match:
        phantom_chance = int(phantom_match.group(1))
        if random.randint(1, 100) <= phantom_chance:
            result["evaded"] = True
            result["damage"] = 0
            result["effect_text"] += "👻幻影回避! "
            return result

    # ダメージ軽減系
    if "全ダメージ" in armor_ability or "被ダメージ" in armor_ability:
        dmg_red_match = re.search(r'(?:全ダメージ|被ダメージ)-(\d+)%', armor_ability)
        if dmg_red_match:
            reduction = int(dmg_red_match.group(1))
            reduced_amount = int(incoming_damage * reduction / 100)
            result["damage"] -= reduced_amount
            result["effect_text"] += f"🛡️軽減-{reduced_amount} "

    # 物理ダメージ軽減
    if "物理ダメージ" in armor_ability:
        phys_match = re.search(r'物理ダメージ(?:軽減)?-(\d+)%', armor_ability)
        if phys_match:
            reduction = int(phys_match.group(1))
            reduced_amount = int(incoming_damage * reduction / 100)
            result["damage"] -= reduced_amount
            result["effect_text"] += f"🛡️物理軽減-{reduced_amount} "

    # 属性耐性（攻撃属性に応じて適用）
    if attack_attribute == "fire":
        if "炎耐性" in armor_ability or "炎無効" in armor_ability:
            if "無効" in armor_ability:
                result["damage"] = 0
                result["effect_text"] += "🔥炎無効! "
            else:
                fire_res_match = re.search(r'炎耐性\+(\d+)%', armor_ability)
                if fire_res_match:
                    resistance = int(fire_res_match.group(1))
                    reduced = int(incoming_damage * resistance / 100)
                    result["damage"] -= reduced
                    result["effect_text"] += f"🔥炎耐性-{reduced} "

    if attack_attribute == "dark":
        if "闇耐性" in armor_ability:
            dark_res_match = re.search(r'闇耐性\+(\d+)%', armor_ability)
            if dark_res_match:
                resistance = int(dark_res_match.group(1))
                reduced = int(incoming_damage * resistance / 100)
                result["damage"] -= reduced
                result["effect_text"] += f"🌑闇耐性-{reduced} "

    if attack_attribute in ["ice", "water"]:
        if "水・氷耐性" in armor_ability or "水耐性" in armor_ability or "氷耐性" in armor_ability:
            water_match = re.search(r'(?:水・氷耐性|水耐性|氷耐性)(\d+)%', armor_ability)
            if water_match:
                resistance = int(water_match.group(1))
                reduced = int(incoming_damage * resistance / 100)
                result["damage"] -= reduced
                result["effect_text"] += f"❄️水氷耐性-{reduced} "

    # 全属性耐性は常に適用（属性攻撃のみ）
    if attack_attribute != "none" and "全属性耐性" in armor_ability:
        all_res_match = re.search(r'全属性耐性\+(\d+)%', armor_ability)
        if all_res_match:
            resistance = int(all_res_match.group(1))
            reduced = int(incoming_damage * resistance / 100)
            result["damage"] -= reduced
            result["effect_text"] += f"✨全耐性-{reduced} "

    # ダメージ下限を0に
    result["damage"] = max(0, result["damage"])

    # 反撃（被ダメージのX%を返す）
    if "反撃" in armor_ability:
        counter_match = re.search(r'被ダメージの(\d+)%を返す', armor_ability)
        if counter_match:
            counter_percent = int(counter_match.group(1))
            result["counter_damage"] = int(incoming_damage * counter_percent / 100)
            result["effect_text"] += f"⚔️反撃{result['counter_damage']} "

    # 被攻撃時反撃ダメージ
    if "被攻撃時" in armor_ability and "反撃ダメージ" in armor_ability:
        reflect_match = re.search(r'反撃ダメージ(\d+)', armor_ability)
        if reflect_match:
            base_reflect = int(reflect_match.group(1))
            reflect_chance_match = re.search(r'被攻撃時(\d+)%', armor_ability)
            if reflect_chance_match:
                reflect_chance = int(reflect_chance_match.group(1))
                if random.randint(1, 100) <= reflect_chance:
                    result["reflect_damage"] = base_reflect
                    result["effect_text"] += f"⚡反撃{base_reflect} "

    # 反射ダメージ
    if "反射ダメージ" in armor_ability:
        reflect_dmg_match = re.search(r'反射ダメージ(\d+)', armor_ability)
        if reflect_dmg_match:
            result["reflect_damage"] = int(reflect_dmg_match.group(1))
            result["effect_text"] += f"⚡反射{result['reflect_damage']} "

    # HP自動回復
    hp_regen_match = re.search(r'HP(?:自動)?回復\+(\d+)', armor_ability)
    if hp_regen_match:
        result["hp_regen"] = int(hp_regen_match.group(1))
        result["effect_text"] += f"💚回復+{result['hp_regen']} "

    # 瀕死時HP回復
    if "瀕死時" in armor_ability and defender_hp <= max_hp * 0.3:
        critical_heal_match = re.search(r'瀕死時HP\+(\d+)', armor_ability)
        if critical_heal_match:
            critical_heal = int(critical_heal_match.group(1))
            result["hp_regen"] += critical_heal
            result["effect_text"] += f"💚瀕死回復+{critical_heal} "

    # HP30%以下で防御力1.5倍（神の加護）
    if "神の加護" in armor_ability and defender_hp <= max_hp * 0.3:
        if "防御力1.5倍" in armor_ability:
            halved = int(result["damage"] / 1.5)
            result["damage"] = halved
            result["effect_text"] += "✨神の加護(防御1.5倍)! "

    # 精霊加護（致死ダメージ時1回生存）
    if "精霊加護" in armor_ability and result["damage"] >= defender_hp:
        if "致死ダメージ時50%で生存" in armor_ability:
            if random.randint(1, 100) < 50:
                result["damage"] = defender_hp - 1
                result["revived"] = True
                result["effect_text"] += "🌟精霊加護(生存)! "

    # 竜鱗の守護（致死ダメージ無効1回）
    if "竜鱗の守護" in armor_ability and result["damage"] >= defender_hp:
        if "致死ダメージ50%で無効" in armor_ability:
            if random.randint(1, 100) < 50:
                result["damage"] = 0
                result["evaded"] = True
                result["effect_text"] += "🐉竜鱗の守護! "

    return result


async def check_story_trigger(previous_distance, current_distance, user_id):
    """
    ストーリートリガーをチェック

    Args:
        previous_distance: 移動前の距離
        current_distance: 移動後の距離
        user_id: ユーザーID

    Returns:
        トリガーされたストーリーID、またはNone
    """
    import db
    from story import STORY_DATA

    player = await db.get_player(user_id)
    if not player:
        return None

    for trigger in STORY_TRIGGERS:
        trigger_distance = trigger["distance"]
        story_id = trigger["story_id"]
        exact_match = trigger.get("exact_match", False)

        triggered = False
        if exact_match:
            triggered = (current_distance == trigger_distance)
        else:
            triggered = (previous_distance < trigger_distance <= current_distance)

        if triggered:
            story = STORY_DATA.get(story_id)
            if not story:
                continue

            if not await db.get_story_flag(user_id, story_id):
                return story_id

    return None

# スキルデータベース
from rpg.data.skills import SKILLS_DATABASE

def get_skill_info(skill_id):
    """スキル情報を取得"""
    return SKILLS_DATABASE.get(skill_id, None)

def get_exp_from_enemy(enemy_name, distance):
    """敵からのEXP獲得量を取得"""
    zone = get_zone_from_distance(distance)
    enemies = ENEMY_ZONES[zone]["enemies"]

    for enemy in enemies:
        if enemy["name"] == enemy_name:
            return enemy.get("exp", 10)

    return 10

def categorize_drops_by_zone(zones, items_db):
    """
    ENEMY_ZONESのドロップアイテムを、アイテムタイプ別に分類し、階層ごとに集計する。
    """
    drops_by_zone_and_type = {}

    for zone_key, zone_data in zones.items():
        "ゾーンごとに結果を初期化"
        drops_by_zone_and_type[zone_key] = {
            "weapon": set(),
            "armor": set(),
            "potion": set(),
            "material": set(),
            "other": set() # noneやcoinsなど、タイプがないものを格納
        }

        "ENEMIESがリストであることを前提"
        for enemy in zone_data.get("enemies", []): 
            "dropsがリストであることを前提"
            for drop in enemy.get("drops", []):
                item_name = drop.get("item")

                "'none' または 'coins' のような特殊ドロップはスキップまたは'other'に追加"
                if item_name == "none" or item_name == "coins":
                    if item_name == "coins":
                        # 'none'は無視、'coins'は'other'に記録
                        drops_by_zone_and_type[zone_key]["other"].add(item_name)
                    continue

                "ITEMS_DATABASEからアイテムタイプを取得"
                item_info = items_db.get(item_name)

                if item_info:
                    item_type = item_info.get("type")
                    if item_type in drops_by_zone_and_type[zone_key]:
                        "該当するタイプセットにアイテム名を追加"
                        drops_by_zone_and_type[zone_key][item_type].add(item_name)
                    else:
                        "定義されていないタイプは 'other' に追加"
                        drops_by_zone_and_type[zone_key]["other"].add(item_name)
                else:
                    "ITEMS_DATABASEに見つからない場合は 'other' に追加"
                    drops_by_zone_and_type[zone_key]["other"].add(item_name)

        "setをリストに変換して、ソートする"
        for item_type in drops_by_zone_and_type[zone_key]:
            drops_by_zone_and_type[zone_key][item_type] = sorted(list(drops_by_zone_and_type[zone_key][item_type]))

    return drops_by_zone_and_type

"階層ごとにタイプ別ドロップアイテムを格納する新しい変数"
"ENEMY_ZONESとITEMS_DATABASEが定義された後に実行されます。"
DROPS_BY_ZONE_AND_TYPE = categorize_drops_by_zone(ENEMY_ZONES, ITEMS_DATABASE)

"0-1000mのエリアでドロップする武器のリストを取得"
weapon_drops_1 = DROPS_BY_ZONE_AND_TYPE["0-1000"]["weapon"]
"['木の剣', '石の剣', '毒の短剣', '鉄の剣']"

"0-1000mのエリアでドロップする防具のリストを取得"
armor_drops_1 = DROPS_BY_ZONE_AND_TYPE["0-1000"]["armor"]
"['木の盾', '石の盾', '鉄の盾']"

"1001-2000mのエリアでドロップする武器のリストを取得"
weapon_drops_2 = DROPS_BY_ZONE_AND_TYPE["1001-2000"]["weapon"]
"['骨の剣', '呪いの剣', '魔法の杖']"

"1001-2000mのエリアでドロップする防具のリストを取得"
armor_drops_2 = DROPS_BY_ZONE_AND_TYPE["1001-2000"]["armor"]
"['骨の盾', '死者の兜', '不死の鎧','幽霊の布']"

"2001-3000mのエリアでドロップする武器のリストを取得"
weapon_drops_3 = DROPS_BY_ZONE_AND_TYPE["2001-3000"]["weapon"]
"['炎の大剣', 'ドラゴンソード', '黒騎士の剣']"

"2001-3000mのエリアでドロップする防具のリストを取得"
armor_drops_3 = DROPS_BY_ZONE_AND_TYPE["2001-3000"]["armor"]
"['地獄の鎧', '龍の鱗', '黒騎士の盾','黒騎士の鎧']"

"3001-4000mのエリアでドロップする武器のリストを取得"
weapon_drops_4 = DROPS_BY_ZONE_AND_TYPE["3001-4000"]["weapon"]
"['炎獄の剣', '死神の鎌']"

"3001-4000mのエリアでドロップする防具のリストを取得"
armor_drops_4 = DROPS_BY_ZONE_AND_TYPE["3001-4000"]["armor"]
"['魔王の盾', '龍鱗の鎧', '冥界の盾','死の鎧']"

"4001-5000mのエリアでドロップする武器のリストを取得"
weapon_drops_5 = DROPS_BY_ZONE_AND_TYPE["4001-5000"]["weapon"]
"['業火の剣', '血の剣', '死霊の杖']"

"4001-5000mのエリアでドロップする防具のリストを取得"
armor_drops_5 = DROPS_BY_ZONE_AND_TYPE["4001-5000"]["armor"]
"['炎の鎧', '夜の外套', '不死王の兜']"

"5001-6000mのエリアでドロップする武器のリストを取得"
weapon_drops_6 = DROPS_BY_ZONE_AND_TYPE["5001-6000"]["weapon"]
"['影の短剣', '暗黒の弓', '破壊の斧', '虚無の剣']"

"5001-6000mのエリアでドロップする防具のリストを取得"
armor_drops_6 = DROPS_BY_ZONE_AND_TYPE["5001-6000"]["armor"]
"['巨人の鎧', '幻影の鎧']"

"6001-7000mのエリアでドロップする武器のリストを取得"
weapon_drops_7 = DROPS_BY_ZONE_AND_TYPE["6001-7000"]["weapon"]
"['カオスブレード', '炎の剣', '滅びの剣']"

"6001-7000mのエリアでドロップする防具のリストを取得"
armor_drops_7 = DROPS_BY_ZONE_AND_TYPE["6001-7000"]["armor"]
"['混沌の鎧', '再生の鎧', '終焉の盾']"

"7001-8000mのエリアでドロップする武器のリストを取得"
weapon_drops_8 = DROPS_BY_ZONE_AND_TYPE["7001-8000"]["weapon"]
"['深淵の剣', '四元の剣', '天の槌']"

"7001-8000mのエリアでドロップする防具のリストを取得"
armor_drops_8 = DROPS_BY_ZONE_AND_TYPE["7001-8000"]["armor"]
"['虚空の鎧', '精霊の盾', '神の盾']"

"8001-9000mのエリアでドロップする武器のリストを取得"
weapon_drops_9 = DROPS_BY_ZONE_AND_TYPE["8001-9000"]["weapon"]
"['暗黒聖剣', '水神の槍', '獄炎の剣']"

"8001-9000mのエリアでドロップする防具のリストを取得"
armor_drops_9 = DROPS_BY_ZONE_AND_TYPE["8001-9000"]["armor"]
"['堕天の鎧', '深海の鎧', '地獄門の鎧']"

"9001-10000mのエリアでドロップする武器のリストを取得"
weapon_drops_10 = DROPS_BY_ZONE_AND_TYPE["9001-10000"]["weapon"]
"['幻影剣', '竜帝剣', '混沌神剣', '死神大鎌']"

"9001-10000mのエリアでドロップする防具のリストを取得"
armor_drops_10 = DROPS_BY_ZONE_AND_TYPE["9001-10000"]["armor"]
"['幻王の鎧', '竜帝の鎧', '創世の盾', '死帝の鎧']"
