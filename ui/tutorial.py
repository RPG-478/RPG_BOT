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
from runtime_settings import VIEW_TIMEOUT_TUTORIAL

logger = logging.getLogger("rpgbot")
class TutorialView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=VIEW_TIMEOUT_TUTORIAL)
        self.user_id = user_id
        self.page = 0
        self.pages = [
            discord.Embed(
                title="なぜ……ここに？(1/5)",
                description="ここは『イニシエダンジョン』──100階層まで続く階層を持つのが特徴の謎のダンジョンだ。\n人工的に作られたかのように100m区切りで1階層となっているようだ……",
                color=discord.Color.purple()
            ),
            discord.Embed(
                title="なぜ……ここに？ (2/5)",
                description="多くの冒険者が挑み、帰らぬ者も数知れない…なぜこんな場所にいるんだ？",
                color=discord.Color.purple()
            ),
            discord.Embed(
                title="⚔ 基本操作 (3/5)",
                description="・`!move` で進む\n・敵に遭遇すると戦闘が始まる\n・勝利すると装備やお金が手に入る\n\nその他コマンドはサポートサーバーをご確認ください",
                color=discord.Color.green()
            ),
            discord.Embed(
                title="📘 冒険チャンネル (4/5)",
                description="ここはあなた専用の冒険チャンネルです。他のプレイヤーは謎の力によって立ち入れません。",
                color=discord.Color.blue()
            ),
            discord.Embed(
                title="✅ チュートリアル完了 (5/5)",
                description="考えてても仕方がない\n準備は整った！ まずは `!move` で進んでみよう！",
                color=discord.Color.gold()
            )
        ]

    async def update_page(self, interaction: discord.Interaction):
        embed = self.pages[self.page]
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⬅ BACK", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        await self.update_page(interaction)

    @discord.ui.button(label="NEXT ➡", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < len(self.pages) - 1:
            self.page += 1
            await self.update_page(interaction)
        else:
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="🎉 チュートリアル終了！",
                    description="君の冒険がいよいよ始まる！ `!move` で歩みを進めよう。",
                    color=discord.Color.green()
                ),
                view=None
            )
            # チュートリアル完了（名前が設定されていることで完了とみなす）
            pass

#!resetコマンド時
# -------------------------
# Reset 用 View（1段階目）
# -------------------------
