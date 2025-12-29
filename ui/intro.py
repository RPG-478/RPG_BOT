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
from runtime_settings import VIEW_TIMEOUT_LONG

logger = logging.getLogger("rpgbot")
class NameRequestView(discord.ui.View):
    def __init__(self, user_id: int, channel: discord.abc.Messageable):
        super().__init__(timeout=VIEW_TIMEOUT_LONG)
        self.user_id = user_id
        self.channel = channel

    @discord.ui.button(label="名前を入力する", style=discord.ButtonStyle.primary)
    async def request_name(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ あなたはこのチュートリアルを開始できません！", ephemeral=True)
            return
        # 名前入力モーダルを開く
        await interaction.response.send_modal(NameModal(self.user_id, self.channel))

# -------------------------
# 名前入力Modal
# -------------------------
class NameModal(discord.ui.Modal):
    def __init__(self, user_id: int, channel: discord.abc.Messageable):
        super().__init__(title="キャラクター名を入力")
        self.user_id = user_id
        self.channel = channel

        self.name_input = discord.ui.TextInput(
            label="あなたの名前は？",
            placeholder="例: 勇者タロウ",
            max_length=20
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        player_name = self.name_input.value.strip()

        # DB更新（名前登録）
        await update_player(self.user_id, name=player_name)

        # 名前反映メッセージ
        await self.channel.send(
            embed=discord.Embed(
                title="🎉 ようこそ！",
                description=f"{player_name} さん、冒険の準備が整いました！",
                color=discord.Color.gold()
            )
        )

        # 倉庫チェック：アイテムがあれば取り出し選択を表示
        storage_items = await db.get_storage_items(self.user_id, include_taken=False)

        if storage_items:
            embed = discord.Embed(
                title="📦 倉庫にアイテムがあります！",
                description="前回の冒険で持ち帰ったアイテムが倉庫にあります。\n1つ取り出して冒険に持っていけます。",
                color=discord.Color.blue()
            )

            # プルダウンで選択肢を作成
            storage_view = StorageSelectView(self.user_id, self.channel, storage_items)
            await self.channel.send(embed=embed, view=storage_view)
        else:
            # 倉庫が空の場合は通常通りチュートリアル開始
            await self.channel.send(
                embed=discord.Embed(
                    title="第1節 ~冒険の始まり~",
                    description="あなたはこのダンジョンに迷い込んだ者。\n目を覚ますと、見知らぬ洞窟の中だった。\n体にはなにも身につけていない。そしてどこかで誰かの声がする――。\n\n『ようこそ、挑戦者よ。ここは終わりなき迷宮。』\n\n『最初の一歩を踏み出す準備はできているか？』",
                    color=discord.Color.purple()
                )
            )

            # チュートリアル開始
            tutorial_view = TutorialView(self.user_id)
            await self.channel.send(embed=tutorial_view.pages[0], view=tutorial_view)


# -------------------------
# 倉庫アイテム選択View
# -------------------------
