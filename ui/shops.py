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
from runtime_settings import DESC_TRIM_LONG, SELECT_MAX_OPTIONS, VIEW_TIMEOUT_SHORT

logger = logging.getLogger("rpgbot")
class BlacksmithView(discord.ui.View):
    """鍛冶屋View - 素材を使って装備を合成"""
    def __init__(self, user_id: int, user_processing: dict, materials: dict):
        super().__init__(timeout=VIEW_TIMEOUT_SHORT)
        self.user_id = user_id
        self.user_processing = user_processing
        self.materials = materials

        self.available_recipes = []
        for recipe_name, recipe in game.CRAFTING_RECIPES.items():
            can_craft = True
            for material, required_count in recipe["materials"].items():
                if self.materials.get(material, 0) < required_count:
                    can_craft = False
                    break
            if can_craft:
                self.available_recipes.append(recipe_name)

        if self.available_recipes:
            options = []
            for recipe_name in self.available_recipes[:SELECT_MAX_OPTIONS]:
                recipe = game.CRAFTING_RECIPES[recipe_name]
                materials_str = ", ".join([f"{mat}x{count}" for mat, count in recipe["materials"].items()])
                desc = f"{materials_str}"
                options.append(discord.SelectOption(
                    label=recipe_name,
                    description=desc[:DESC_TRIM_LONG],
                    value=recipe_name
                ))

            select = discord.ui.Select(
                placeholder="合成したいアイテムを選択",
                options=options
            )
            select.callback = self.craft_callback
            self.add_item(select)
        
        # 「戻る」ボタンを常に追加
        close_button = discord.ui.Button(
            label="戻る",
            style=discord.ButtonStyle.secondary,
            emoji="🚪"
        )
        close_button.callback = self.close_callback
        self.add_item(close_button)

    def get_embed(self):
        embed = discord.Embed(
            title="🔨 鍛冶屋",
            description="「素材を使って強力な装備を作ることができるぞ。俺ちゃん天才！」\n\n所持素材:",
            color=discord.Color.blue()
        )

        if self.materials:
            for material, count in self.materials.items():
                embed.add_field(name=material, value=f"x{count}", inline=True)
        else:
            embed.add_field(name="素材なし", value="素材を集めてきてください", inline=False)

        if self.available_recipes:
            embed.add_field(name="\n合成可能なレシピ", value="下のメニューから選択してください", inline=False)
        else:
            embed.add_field(
                name="\n⚠️ 合成可能なレシピなし", 
                value="現在の素材では合成できるアイテムがありません。\nもっと素材を集めてから来てください。\n\n「戻る」ボタンで特殊イベント選択に戻れます。", 
                inline=False
            )

        return embed

    async def craft_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("これはあなたの鍛冶屋ではありません！", ephemeral=True)

        recipe_name = interaction.data['values'][0]
        recipe = game.CRAFTING_RECIPES.get(recipe_name)
        
        if not recipe:
            return await interaction.response.send_message("⚠️ レシピ情報が見つかりません。", ephemeral=True)

        player = await get_player(interaction.user.id)
        if not player:
            return await interaction.response.send_message("⚠️ プレイヤーデータが見つかりません。", ephemeral=True)

        # 素材を消費
        for material, required_count in recipe["materials"].items():
            for _ in range(required_count):
                await db.remove_item_from_inventory(interaction.user.id, material)

        # アイテムを追加
        await db.add_item_to_inventory(interaction.user.id, recipe_name)

        # アイテムデータベースに登録（存在しない場合）
        if recipe_name not in game.ITEMS_DATABASE:
            game.ITEMS_DATABASE[recipe_name] = {
                "type": recipe["result_type"],
                "attack": recipe.get("attack", 0),
                "defense": recipe.get("defense", 0),
                "ability": recipe["ability"],
                "description": recipe["description"]
            }

        materials_used = ", ".join([f"{mat}x{count}" for mat, count in recipe["materials"].items()])

        embed = discord.Embed(
            title="✨ 合成成功！",
            description=f"**{recipe_name}** を作成した！\n『ほらよ。ちゃんと作ってやったぜ』\n\n使用素材: {materials_used}",
            color=discord.Color.gold()
        )

        if recipe["result_type"] == "weapon":
            embed.add_field(name="攻撃力", value=str(recipe.get("attack", 0)), inline=True)
        elif recipe["result_type"] == "armor":
            embed.add_field(name="防御力", value=str(recipe.get("defense", 0)), inline=True)

        embed.add_field(name="能力", value=recipe["ability"], inline=False)
        embed.add_field(name="説明", value=recipe["description"], inline=False)

        await interaction.response.edit_message(embed=embed, view=None)

        if self.user_id in self.user_processing:
            self.user_processing[self.user_id] = False

    async def close_callback(self, interaction: discord.Interaction):
        """戻るボタン"""
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("これはあなたの鍛冶屋ではありません！", ephemeral=True)

        embed = discord.Embed(
            title="🏛️ 特殊イベント",
            description="鍛冶屋を後にした。\n\n他の選択肢を選んでください。",
            color=discord.Color.blue()
        )

        await interaction.response.edit_message(embed=embed, view=None)

        if self.user_id in self.user_processing:
            self.user_processing[self.user_id] = False

    async def on_timeout(self):
        """タイムアウト時にuser_processingをクリア"""
        if self.user_id in self.user_processing:
            self.user_processing[self.user_id] = False

class MaterialMerchantView(discord.ui.View):
    """素材商人View - 素材を売却"""
    def __init__(self, user_id: int, user_processing: dict, materials: dict):
        super().__init__(timeout=VIEW_TIMEOUT_SHORT)
        self.user_id = user_id
        self.user_processing = user_processing
        self.materials = materials

        options = []
        for material, count in materials.items():
            price = game.MATERIAL_PRICES.get(material, 10)
            total_price = price * count
            options.append(discord.SelectOption(
                label=f"{material} (x{count})",
                description=f"単価: {price}G × {count}個 = {total_price}G",
                value=material
            ))

        select = discord.ui.Select(
            placeholder="売却する素材を選択",
            options=options
        )
        select.callback = self.sell_callback
        self.add_item(select)

        sell_all_button = discord.ui.Button(label="全て売却", style=discord.ButtonStyle.success, emoji="💰")
        sell_all_button.callback = self.sell_all_callback
        self.add_item(sell_all_button)

    def get_embed(self):
        embed = discord.Embed(
            title="💰 素材商人",
            description="「素材を買い取るぞ。良い値で引き取ろう――」\n\n所持素材と買取価格:",
            color=discord.Color.green()
        )

        total_value = 0
        for material, count in self.materials.items():
            price = game.MATERIAL_PRICES.get(material, 10)
            total_price = price * count
            total_value += total_price
            embed.add_field(
                name=f"{material} (x{count})",
                value=f"{price}G × {count} = {total_price}G",
                inline=False
            )

        embed.add_field(name="\n💎 全素材の合計価値", value=f"**{total_value}G**", inline=False)
        embed.set_footer(text="下のメニューから売却する素材を選択してください")

        return embed

    async def sell_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("これはあなたの商人ではありません！", ephemeral=True)

        material = interaction.data['values'][0]
        count = self.materials[material]
        price = game.MATERIAL_PRICES.get(material, 10)
        total_price = price * count

        for _ in range(count):
            await db.remove_item_from_inventory(interaction.user.id, material)

        await db.add_gold(interaction.user.id, total_price)

        embed = discord.Embed(
            title="✅ 売却完了！",
            description=f"**{material}** を {count}個売却した！\n\n💰 {total_price}ゴールドを獲得！",
            color=discord.Color.gold()
        )

        await interaction.response.edit_message(embed=embed, view=None)

        if self.user_id in self.user_processing:
            self.user_processing[self.user_id] = False

    async def sell_all_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("これはあなたの商人ではありません！", ephemeral=True)

        total_gold = 0
        sold_items = []

        for material, count in self.materials.items():
            price = game.MATERIAL_PRICES.get(material, 10)
            total_price = price * count
            total_gold += total_price

            for _ in range(count):
                await db.remove_item_from_inventory(interaction.user.id, material)

            sold_items.append(f"{material} x{count} = {total_price}G")

        await db.add_gold(interaction.user.id, total_gold)

        sold_text = "\n".join(sold_items)

        embed = discord.Embed(
            title="✅ 一括売却完了！",
            description=f"全ての素材を売却した！\n\n{sold_text}\n\n💰 合計 {total_gold}ゴールドを獲得！",
            color=discord.Color.gold()
        )

        await interaction.response.edit_message(embed=embed, view=None)

        if self.user_id in self.user_processing:
            self.user_processing[self.user_id] = False

# 死亡処理 + トリガーチェック 共通ヘルパー
