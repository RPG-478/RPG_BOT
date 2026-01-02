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
from runtime_settings import SELECT_MAX_OPTIONS, VIEW_TIMEOUT_LONG
from story import StoryView

logger = logging.getLogger("rpgbot")
class StorageSelectView(discord.ui.View):
    def __init__(self, user_id: int, channel: discord.TextChannel, storage_items: list):
        # 倉庫は選択に時間がかかることがあるため、View側のタイムアウトを無効化。
        super().__init__(timeout=None)
        self.user_id = user_id
        self.channel = channel
        self.storage_items = storage_items

        # プルダウンメニューを作成
        options = []
        for item_data in storage_items[:SELECT_MAX_OPTIONS]:  # 最大25個
            item_name = item_data.get("item_name", "不明なアイテム")
            item_type = item_data.get("item_type", "material")
            storage_id = item_data.get("id")

            # 絵文字を選択
            emoji_map = {
                "weapon": "⚔️",
                "armor": "🛡️",
                "potion": "🧪",
                "material": "📦"
            }
            emoji = emoji_map.get(item_type, "📦")

            # アイテム情報取得
            item_info = game.get_item_info(item_name)
            description = item_info.get("description", "")[:50] if item_info else ""

            options.append(discord.SelectOption(
                label=item_name,
                description=f"{item_type.upper()} - {description}",
                value=str(storage_id),
                emoji=emoji
            ))

        # "取り出さない"オプションも追加
        options.append(discord.SelectOption(
            label="取り出さない",
            description="倉庫からアイテムを取り出さずに冒険を開始",
            value="skip",
            emoji="❌"
        ))

        select = discord.ui.Select(
            placeholder="倉庫から取り出すアイテムを選択...",
            options=options,
            custom_id="storage_retrieve_select"
        )
        select.callback = self.retrieve_item
        self.add_item(select)

    async def retrieve_item(self, interaction: discord.Interaction):
        """選択されたアイテムを倉庫から取り出してインベントリに追加"""
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("これはあなたの選択ではありません！", ephemeral=True)

        selected_value = interaction.data['values'][0]

        if selected_value == "skip":
            # 取り出さない場合も、まずは相方ストーリー（みはり）を開始
            embed = discord.Embed(
                title="📦 倉庫をスキップ",
                description="倉庫からアイテムを取り出さずに冒険を開始します。",
                color=discord.Color.grey()
            )
            await interaction.response.edit_message(embed=embed, view=None)

            view = StoryView(self.user_id, "start_mihari", user_processing={})
            await view.send_story(interaction)
            return

        # アイテムを取り出す
        storage_id = int(selected_value)
        item_data = await db.get_storage_item_by_id(storage_id)

        if not item_data:
            await interaction.response.send_message("⚠️ アイテムが見つかりません。", ephemeral=True)
            return

        item_name = item_data.get("item_name")

        # 倉庫から取り出し（is_taken = True に設定）
        success = await db.take_from_storage(self.user_id, storage_id)

        if success:
            # インベントリに追加
            await db.add_item_to_inventory(self.user_id, item_name)

            embed = discord.Embed(
                title="✅ アイテムを取り出しました 第1節 ~冒険の始まり~",
                description=f"**{item_name}** を倉庫から取り出し、インベントリに追加しました！\n\nあなたはこのダンジョンを踏破しに来た者。\n目を覚ますと、見知らぬ洞窟の中だった。\n手には何故かアイテム、そしてどこかで誰かの声がする――。\n\n『ようこそ、挑戦者よ。ここは終わりなき迷宮。』\n\n『最初の一歩を踏み出す準備はできているか？』",
                color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=embed, view=None)

            view = StoryView(self.user_id, "start_mihari", user_processing={})
            await view.send_story(interaction)
        else:
            await interaction.response.send_message("⚠️ アイテムの取り出しに失敗しました。", ephemeral=True)

# -------------------------
# 世界線説明View
# -------------------------
