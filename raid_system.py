"""
レイドボスシステム - 曜日別協力型レイドバトルシステム
500m毎の特殊な敵をレイドボスに置き換え
"""
import discord
from datetime import datetime, timezone, timedelta
import random

# ==========================
# 曜日別レイドボスデータ
# ==========================

RAID_BOSSES = {
    0: {  # 月曜日
        "id": "monday_golem",
        "name": "古代の巨像ゴーレム",
        "description": "古代遺跡から蘇った巨大な石像。全プレイヤーで協力して倒せ！",
        "max_hp": 50000,
        "attack": 80,
        "defense": 40,
        "rewards": {
            "gold": (500, 1000),
            "upgrade_points": 3,
            "items": ["巨獣の皮", "神の鉱石", "石の盾"]
        },
        "emoji": "🗿",
        "color": 0x808080
    },
    1: {  # 火曜日
        "id": "tuesday_dragon",
        "name": "炎竜インフェルノ",
        "description": "業火を纏う古龍。全プレイヤーの力を結集せよ！",
        "max_hp": 60000,
        "attack": 100,
        "defense": 35,
        "rewards": {
            "gold": (600, 1200),
            "upgrade_points": 3,
            "items": ["竜の牙", "竜帝の心臓", "炎の大剣"]
        },
        "emoji": "🐉",
        "color": 0xff4500
    },
    2: {  # 水曜日
        "id": "wednesday_kraken",
        "name": "深海の支配者クラーケン",
        "description": "深海より現れた巨大な海獣。協力して打ち倒せ！",
        "max_hp": 55000,
        "attack": 90,
        "defense": 30,
        "rewards": {
            "gold": (550, 1100),
            "upgrade_points": 3,
            "items": ["海皇の鱗", "深海の鎧", "水神の槍"]
        },
        "emoji": "🦑",
        "color": 0x00bfff
    },
    3: {  # 木曜日
        "id": "thursday_demon",
        "name": "魔界将軍ベリアル",
        "description": "魔界から現れた将軍。全員の力で封印せよ！",
        "max_hp": 65000,
        "attack": 110,
        "defense": 45,
        "rewards": {
            "gold": (700, 1400),
            "upgrade_points": 4,
            "items": ["悪魔の角", "魔界の結晶", "暗黒聖剣"]
        },
        "emoji": "👹",
        "color": 0x8b008b
    },
    4: {  # 金曜日
        "id": "friday_undead",
        "name": "不死王リッチロード",
        "description": "死を超越した不死の王。協力して浄化せよ！",
        "max_hp": 58000,
        "attack": 95,
        "defense": 50,
        "rewards": {
            "gold": (580, 1150),
            "upgrade_points": 3,
            "items": ["闇の宝珠", "不死鳥の羽", "死神の剣"]
        },
        "emoji": "💀",
        "color": 0x4b0082
    },
    5: {  # 土曜日
        "id": "saturday_titan",
        "name": "雷神タイタン",
        "description": "雷を司る巨神。全プレイヤーの勇気を示せ！",
        "max_hp": 70000,
        "attack": 120,
        "defense": 40,
        "rewards": {
            "gold": (750, 1500),
            "upgrade_points": 4,
            "items": ["元素の核", "神の鉱石", "雷神の槍"]
        },
        "emoji": "⚡",
        "color": 0xffd700
    },
    6: {  # 日曜日
        "id": "sunday_phoenix",
        "name": "不死鳥フェニックス",
        "description": "永遠の炎を宿す不死鳥。全員で打ち倒せ！",
        "max_hp": 75000,
        "attack": 105,
        "defense": 38,
        "rewards": {
            "gold": (800, 1600),
            "upgrade_points": 5,
            "items": ["不死鳥の羽", "破壊の核", "幻影の剣"]
        },
        "emoji": "🔥",
        "color": 0xff6347
    }
}

# ==========================
# レイドボス関連関数
# ==========================

def get_current_raid_boss():
    """現在の曜日に基づいてレイドボスを取得"""
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst)
    weekday = now.weekday()
    return RAID_BOSSES[weekday]

def get_raid_boss_by_distance(distance):
    """距離に基づいてレイドボスを取得（500m毎に固定）"""
    return get_current_raid_boss()

def calculate_raid_damage(player_raid_atk, player_raid_def, boss_data, skill_multiplier=1.0):
    """レイドダメージを計算"""
    base_damage = max(1, player_raid_atk - (boss_data["defense"] // 2))
    final_damage = int(base_damage * skill_multiplier)
    return max(1, final_damage)

def calculate_raid_rewards(contribution, total_damage, boss_defeated=False):
    """貢献度に応じた報酬を計算"""
    boss = get_current_raid_boss()
    
    # 基本報酬
    base_gold = random.randint(*boss["rewards"]["gold"])
    base_points = boss["rewards"]["upgrade_points"]
    
    # 貢献度割合に応じて報酬調整（最低10%保証）
    if total_damage > 0:
        contribution_ratio = max(0.1, min(1.0, contribution / total_damage))
    else:
        contribution_ratio = 0.1
    
    # 報酬計算
    gold_reward = int(base_gold * contribution_ratio)
    points_reward = max(1, int(base_points * contribution_ratio))
    
    # 討伐完了ボーナス
    bonus_multiplier = 1.5 if boss_defeated else 1.0
    gold_reward = int(gold_reward * bonus_multiplier)
    points_reward = int(points_reward * bonus_multiplier)
    
    # アイテム報酬（討伐時のみ、貢献度により確率変動）
    item_reward = None
    if boss_defeated and random.random() < contribution_ratio:
        item_reward = random.choice(boss["rewards"]["items"])
    
    return {
        "gold": gold_reward,
        "upgrade_points": points_reward,
        "item": item_reward,
        "contribution_ratio": contribution_ratio
    }

def format_raid_info_embed(boss_data, current_hp, total_damage, top_contributors=None):
    """レイドボス情報のEmbedを作成"""
    hp_percentage = (current_hp / boss_data["max_hp"]) * 100
    hp_bar_length = 20
    filled = int((current_hp / boss_data["max_hp"]) * hp_bar_length)
    hp_bar = "█" * filled + "░" * (hp_bar_length - filled)
    
    embed = discord.Embed(
        title=f"{boss_data['emoji']} {boss_data['name']}",
        description=boss_data['description'],
        color=boss_data['color']
    )
    
    embed.add_field(
        name="📊 ボス体力",
        value=f"{hp_bar}\n**{current_hp:,} / {boss_data['max_hp']:,} HP** ({hp_percentage:.1f}%)",
        inline=False
    )
    
    embed.add_field(
        name="⚔️ 総ダメージ",
        value=f"{total_damage:,}",
        inline=True
    )
    
    embed.add_field(
        name="💎 討伐報酬",
        value=f"🪙 {boss_data['rewards']['gold'][0]}〜{boss_data['rewards']['gold'][1]} ゴールド\n"
              f"⭐ {boss_data['rewards']['upgrade_points']} アップグレードポイント\n"
              f"📦 レアアイテム",
        inline=True
    )
    
    # トップ貢献者
    if top_contributors and len(top_contributors) > 0:
        contributor_text = ""
        for i, contrib in enumerate(top_contributors[:5], 1):
            contributor_text += f"{i}. <@{contrib['user_id']}>: {contrib['total_damage']:,} ダメージ\n"
        embed.add_field(
            name="🏆 トップ貢献者",
            value=contributor_text or "まだ参加者がいません",
            inline=False
        )
    
    embed.set_footer(text="全プレイヤー協力型レイドボス | !moveで挑戦！")
    
    return embed
