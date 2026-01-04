from __future__ import annotations

import discord
from discord.ext import commands

import db
from bot_utils import check_ban


class HelpPaginationView(discord.ui.View):
    def __init__(self, author_id: int, pages: list[discord.Embed]):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.pages = pages
        self.index = 0
        self.message: discord.Message | None = None
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.back_button.disabled = self.index <= 0
        self.next_button.disabled = self.index >= (len(self.pages) - 1)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        user = getattr(interaction, "user", None)
        if user is None:
            return False
        if user.id != self.author_id:
            try:
                await interaction.response.send_message(
                    "このヘルプはコマンド実行者のみ操作できます。",
                    ephemeral=True,
                )
            except Exception:
                pass
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(label="BACK", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index > 0:
            self.index -= 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="NEXT", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index < len(self.pages) - 1:
            self.index += 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)


def setup_help_command(bot: commands.Bot) -> None:
    @bot.command(name="help")
    @check_ban()
    async def help_command(ctx: commands.Context):
        # チュートリアル進行: help を開いた
        try:
            await db.set_story_flag_key(ctx.author.id, "tutorial.used_help", True)
        except Exception:
            pass

        pages: list[discord.Embed] = []

        embed1 = discord.Embed(
            title="📘 ヘルプ（基本コマンド） 1/2",
            description="よく使うコマンドをまとめたよ。困ったらここを見てね。",
            color=discord.Color.blurple(),
        )
        embed1.add_field(name="移動", value="`!move` / `!m`\nダンジョンを進む", inline=False)
        embed1.add_field(name="インベントリ", value="`!inventory` / `!inv`\n持ち物を見る", inline=False)
        embed1.add_field(name="ステータス", value="`!status` / `!s`\nHP/MP/装備などを見る", inline=False)
        embed1.add_field(name="ヘルプ", value="`!help`\nこのヘルプを表示", inline=False)
        pages.append(embed1)

        embed2 = discord.Embed(
            title="🧵 ヘルプ（冒険スレッド関連） 2/2",
            description="冒険の開始/終了や、スレッド運用に関わるコマンドだよ。",
            color=discord.Color.teal(),
        )
        embed2.add_field(name="冒険を開始", value="`!start`\n冒険を始める（スレッド運用ならスレッドが作成される）", inline=False)
        embed2.add_field(name="冒険スレッドを閉じる", value="`!close`\nデータは保持して、冒険スレッドだけ削除", inline=False)
        embed2.add_field(name="リセット", value="`!reset` / `!r`\nプレイヤーデータを削除（確認あり）", inline=False)
        embed2.add_field(name="スレッド運用設定（管理者）", value="`!set` / `!set off`\n`!start` の作成先をスレッドにする/解除", inline=False)
        pages.append(embed2)

        view = HelpPaginationView(ctx.author.id, pages)
        msg = await ctx.send(embed=pages[0], view=view)
        view.message = msg
