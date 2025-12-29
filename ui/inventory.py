import discord
import db
import random
import asyncio
import game
import logging
from discord.ui import View, button, Select
from db import get_player, update_player, delete_player
import death_system
from titles import get_title_rarity_emoji, get_title_rarity_color
from runtime_settings import (
    DESC_TRIM_LONG,
    DESC_TRIM_SHORT,
    SELECT_MAX_OPTIONS,
    VIEW_TIMEOUT_SHORT,
)

logger = logging.getLogger("rpgbot")
def status_embed(player):
    embed = discord.Embed(title="📊 ステータス", color=discord.Color.blue())
    embed.add_field(name="名前", value=player.get("name", "未設定"))
    embed.add_field(name="HP", value=player.get("hp", 50))
    embed.add_field(name="攻撃力", value=player.get("attack", 5))
    embed.add_field(name="防御力", value=player.get("defense", 2))
    embed.add_field(name="所持金", value=f'{player.get("gold", 0)}G')
    return embed

from collections import Counter

class InventorySelectView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=VIEW_TIMEOUT_SHORT)
        self.player = player
        self.user_id = player.get("user_id") if isinstance(player, dict) else None
        inventory = player.get("inventory", [])

        if not inventory:
            options = [discord.SelectOption(label="アイテムなし", description="インベントリは空です", value="none")]
            select = discord.ui.Select(
                placeholder="アイテムを選んで詳細を表示",
                options=options,
                custom_id="inventory_select"
            )
            select.callback = self.select_callback
            self.add_item(select)
        else:
            # アイテムをカウント（集約）
            item_counts = Counter(inventory)
            
            # アイテムを種類別に分類
            potions = []
            weapons = []
            armors = []
            materials = []
            
            for item_name, count in item_counts.items():
                item_info = game.get_item_info(item_name)
                if item_info:
                    if item_info['type'] == 'potion':
                        potions.append((item_name, count, item_info))
                    elif item_info['type'] == 'weapon':
                        weapons.append((item_name, count, item_info))
                    elif item_info['type'] == 'armor':
                        armors.append((item_name, count, item_info))
                    else:
                        materials.append((item_name, count, item_info))
            
            # ポーションのプルダウン（最大25個）
            if potions:
                potion_options = []
                for i, (item_name, count, info) in enumerate(potions[:SELECT_MAX_OPTIONS]):
                    desc = info.get('description', 'ポーション')[:DESC_TRIM_SHORT]
                    label = f"{item_name} ×{count}" if count > 1 else item_name
                    potion_options.append(discord.SelectOption(
                        label=label,
                        description=desc,
                        value=f"potion_{i}_{item_name}",  # 重複回避
                        emoji="🧪"
                    ))
                
                potion_select = discord.ui.Select(
                    placeholder="🧪 ポーション",
                    options=potion_options,
                    custom_id="potion_select"
                )
                potion_select.callback = self.select_callback
                self.add_item(potion_select)
            
            # 武器のプルダウン（最大25個）
            if weapons:
                weapon_options = []
                for i, (item_name, count, info) in enumerate(weapons[:SELECT_MAX_OPTIONS]):
                    desc = f"攻撃力:{info.get('attack', 0)} | 所持数:{count}"
                    label = f"{item_name} ×{count}" if count > 1 else item_name
                    weapon_options.append(discord.SelectOption(
                        label=label,
                        description=desc[:DESC_TRIM_LONG],
                        value=f"weapon_{i}_{item_name}",
                        emoji="⚔️"
                    ))
                
                weapon_select = discord.ui.Select(
                    placeholder="⚔️ 武器",
                    options=weapon_options,
                    custom_id="weapon_select"
                )
                weapon_select.callback = self.select_callback
                self.add_item(weapon_select)
            
            # 防具のプルダウン（最大25個）
            if armors:
                armor_options = []
                for i, (item_name, count, info) in enumerate(armors[:SELECT_MAX_OPTIONS]):
                    desc = f"防御力:{info.get('defense', 0)} | 所持数:{count}"
                    label = f"{item_name} ×{count}" if count > 1 else item_name
                    armor_options.append(discord.SelectOption(
                        label=label,
                        description=desc[:DESC_TRIM_LONG],
                        value=f"armor_{i}_{item_name}",
                        emoji="🛡️"
                    ))
                
                armor_select = discord.ui.Select(
                    placeholder="🛡️ 防具",
                    options=armor_options,
                    custom_id="armor_select"
                )
                armor_select.callback = self.select_callback
                self.add_item(armor_select)
            
            # 素材のプルダウン（最大25個）
            if materials:
                material_options = []
                for i, (item_name, count, info) in enumerate(materials[:SELECT_MAX_OPTIONS]):
                    desc = f"{info.get('description', '素材')[:DESC_TRIM_SHORT]} | 所持数:{count}"
                    label = f"{item_name} ×{count}" if count > 1 else item_name
                    material_options.append(discord.SelectOption(
                        label=label,
                        description=desc[:DESC_TRIM_LONG],
                        value=f"material_{i}_{item_name}",
                        emoji="📦"
                    ))
                
                material_select = discord.ui.Select(
                    placeholder="📦 素材",
                    options=material_options,
                    custom_id="material_select"
                )
                material_select.callback = self.select_callback
                self.add_item(material_select)

    async def select_callback(self, interaction: discord.Interaction):
        if self.player.get("user_id") and interaction.user.id != int(self.player.get("user_id")):
            return await interaction.response.send_message("これはあなたのインベントリではありません！", ephemeral=True)

        selected_value = interaction.data['values'][0]
        if selected_value == "none":
            return await interaction.response.send_message("アイテムがありません。", ephemeral=True)

        # valueから型、インデックス、アイテム名を分離
        parts = selected_value.split("_", 2)
        if len(parts) < 3:
            return await interaction.response.send_message("不正な選択です。", ephemeral=True)
        
        item_type, idx, item_name = parts
        item_info = game.get_item_info(item_name)

        if not item_info:
            return await interaction.response.send_message("アイテム情報が見つかりません。", ephemeral=True)

        # 所持数を取得
        inventory = self.player.get("inventory", [])
        item_count = inventory.count(item_name)

        # アイテムタイプ別処理
        if item_info['type'] == 'potion':
            # 回復薬使用
            player = await get_player(interaction.user.id)
            if not player:
                return await interaction.response.send_message("プレイヤーデータが見つかりません。", ephemeral=True)

            effect = item_info.get('effect', '')
            
            # MP回復薬の処理
            if 'MP+' in effect or 'MP全回復' in effect:
                current_mp = player.get('mp', 20)
                max_mp = player.get('max_mp', 20)
                
                if current_mp >= max_mp:
                    return await interaction.response.send_message("MPは既に最大です！", ephemeral=True)
                
                if 'MP+30' in effect:
                    mp_heal = 30
                elif 'MP+80' in effect:
                    mp_heal = 80
                elif 'MP+200' in effect:
                    mp_heal = 200
                elif 'MP全回復' in effect:
                    mp_heal = max_mp
                else:
                    mp_heal = 30
                
                new_mp = min(max_mp, current_mp + mp_heal)
                actual_mp_heal = new_mp - current_mp
                
                await update_player(interaction.user.id, mp=new_mp)
                await db.remove_item_from_inventory(interaction.user.id, item_name)
                
                remaining = item_count - 1
                await interaction.response.send_message(
                    f"✨ **{item_name}** を使用した！\nMP +{actual_mp_heal} 回復！（{current_mp} → {new_mp}）\n残り: {remaining}個",
                    ephemeral=True
                )
            # HP回復薬の処理
            else:
                current_hp = player.get('hp', 50)
                max_hp = player.get('max_hp', 50)
                
                if current_hp >= max_hp:
                    return await interaction.response.send_message("HPは既に最大です！", ephemeral=True)

                if 'HP+30' in effect:
                    heal = 30
                elif 'HP+80' in effect:
                    heal = 80
                elif 'HP+200' in effect:
                    heal = 200
                elif 'HP全回復' in effect:
                    heal = max_hp
                else:
                    heal = 30

                new_hp = min(max_hp, current_hp + heal)
                actual_heal = new_hp - current_hp

                await update_player(interaction.user.id, hp=new_hp)
                await db.remove_item_from_inventory(interaction.user.id, item_name)

                remaining = item_count - 1
                await interaction.response.send_message(
                    f"✨ **{item_name}** を使用した！\nHP +{actual_heal} 回復！（{current_hp} → {new_hp}）\n残り: {remaining}個",
                    ephemeral=True
                )

        elif item_info['type'] == 'weapon':
            attack = item_info.get('attack', 0)
            ability = item_info.get('ability', 'なし')
            description = item_info.get('description', '')
            await interaction.response.send_message(
                f"⚔️ **{item_name}** (所持数: {item_count})\n攻撃力: {attack}\n能力: {ability}\n\n{description}\n\n装備するには `!status` コマンドから装備変更してください。",
                ephemeral=True
            )

        elif item_info['type'] == 'armor':
            defense = item_info.get('defense', 0)
            ability = item_info.get('ability', 'なし')
            description = item_info.get('description', '')
            await interaction.response.send_message(
                f"🛡️ **{item_name}** (所持数: {item_count})\n防御力: {defense}\n能力: {ability}\n\n{description}\n\n装備するには `!status` コマンドから装備変更してください。",
                ephemeral=True
            )

        else:
            await interaction.response.send_message(
                f"📦 {item_name} (所持数: {item_count})\n{item_info.get('description', '')}",
                ephemeral=True
            )


from collections import Counter

class EquipmentSelectView(discord.ui.View):
    """装備変更用View"""
    def __init__(self, player):
        super().__init__(timeout=VIEW_TIMEOUT_SHORT)
        self.player = player
        self.user_id = player.get("user_id") if isinstance(player, dict) else None
        inventory = player.get("inventory", [])

        # アイテムをカウント（集約）
        item_counts = Counter(inventory)

        # 武器リストと防具リスト
        weapons = []
        armors = []
        
        for item_name, count in item_counts.items():
            item_info = game.get_item_info(item_name)
            if item_info:
                if item_info['type'] == 'weapon':
                    weapons.append((item_name, count, item_info))
                elif item_info['type'] == 'armor':
                    armors.append((item_name, count, item_info))

        # 武器選択プルダウン1（1〜25個目）
        if weapons:
            weapon_options_1 = []
            for i, (weapon_name, count, item_info) in enumerate(weapons[:SELECT_MAX_OPTIONS]):
                desc = f"攻撃力: {item_info.get('attack', 0)} | 所持数: {count}"
                label = f"{weapon_name} ×{count}" if count > 1 else weapon_name
                weapon_options_1.append(discord.SelectOption(
                    label=label,
                    description=desc[:DESC_TRIM_LONG],
                    value=f"weapon_{i}_{weapon_name}",
                    emoji="⚔️"
                ))
            
            weapon_select_1 = discord.ui.Select(
                placeholder="⚔️ 武器を選択 (1/2)",
                options=weapon_options_1,
                custom_id="weapon_select_1"
            )
            weapon_select_1.callback = self.select_callback
            self.add_item(weapon_select_1)

        # 武器選択プルダウン2（26〜50個目）
        if len(weapons) > SELECT_MAX_OPTIONS:
            weapon_options_2 = []
            for i, (weapon_name, count, item_info) in enumerate(weapons[SELECT_MAX_OPTIONS:SELECT_MAX_OPTIONS*2], start=SELECT_MAX_OPTIONS):
                desc = f"攻撃力: {item_info.get('attack', 0)} | 所持数: {count}"
                label = f"{weapon_name} ×{count}" if count > 1 else weapon_name
                weapon_options_2.append(discord.SelectOption(
                    label=label,
                    description=desc[:DESC_TRIM_LONG],
                    value=f"weapon_{i}_{weapon_name}",
                    emoji="⚔️"
                ))
            
            weapon_select_2 = discord.ui.Select(
                placeholder="⚔️ 武器を選択 (2/2)",
                options=weapon_options_2,
                custom_id="weapon_select_2"
            )
            weapon_select_2.callback = self.select_callback
            self.add_item(weapon_select_2)

        # 防具選択プルダウン1（1〜25個目）
        if armors:
            armor_options_1 = []
            for i, (armor_name, count, item_info) in enumerate(armors[:SELECT_MAX_OPTIONS]):
                desc = f"防御力: {item_info.get('defense', 0)} | 所持数: {count}"
                label = f"{armor_name} ×{count}" if count > 1 else armor_name
                armor_options_1.append(discord.SelectOption(
                    label=label,
                    description=desc[:DESC_TRIM_LONG],
                    value=f"armor_{i}_{armor_name}",
                    emoji="🛡️"
                ))
            
            armor_select_1 = discord.ui.Select(
                placeholder="🛡️ 防具を選択 (1/2)",
                options=armor_options_1,
                custom_id="armor_select_1"
            )
            armor_select_1.callback = self.select_callback
            self.add_item(armor_select_1)

        # 防具選択プルダウン2（26〜50個目）
        if len(armors) > SELECT_MAX_OPTIONS:
            armor_options_2 = []
            for i, (armor_name, count, item_info) in enumerate(armors[SELECT_MAX_OPTIONS:SELECT_MAX_OPTIONS*2], start=SELECT_MAX_OPTIONS):
                desc = f"防御力: {item_info.get('defense', 0)} | 所持数: {count}"
                label = f"{armor_name} ×{count}" if count > 1 else armor_name
                armor_options_2.append(discord.SelectOption(
                    label=label,
                    description=desc[:DESC_TRIM_LONG],
                    value=f"armor_{i}_{armor_name}",
                    emoji="🛡️"
                ))
            
            armor_select_2 = discord.ui.Select(
                placeholder="🛡️ 防具を選択 (2/2)",
                options=armor_options_2,
                custom_id="armor_select_2"
            )
            armor_select_2.callback = self.select_callback
            self.add_item(armor_select_2)

    async def select_callback(self, interaction: discord.Interaction):
        if self.player.get("user_id") and interaction.user.id != int(self.player.get("user_id")):
            return await interaction.response.send_message("これはあなたの装備ではありません！", ephemeral=True)

        selected_value = interaction.data['values'][0]
        parts = selected_value.split("_", 2)
        
        if len(parts) < 3:
            return await interaction.response.send_message("⚠️ 不正な選択です。", ephemeral=True)
        
        equip_type = parts[0]
        item_name = parts[2]

        if equip_type == "weapon":
            await db.equip_weapon(interaction.user.id, item_name)
            await interaction.response.send_message(f"⚔️ **{item_name}** を武器として装備した！", ephemeral=True)
        elif equip_type == "armor":
            await db.equip_armor(interaction.user.id, item_name)
            await interaction.response.send_message(f"🛡️ **{item_name}** を防具として装備した！", ephemeral=True)


