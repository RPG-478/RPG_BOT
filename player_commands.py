from __future__ import annotations

import discord
from discord.ext import commands

from bot_utils import check_ban
from db import get_player
from views import ResetConfirmView


def setup_player_commands(bot: commands.Bot):
    user_processing = getattr(bot, "user_processing", {})

    @bot.command(name="reset", aliases=["r"])
    @check_ban()
    async def reset(ctx: commands.Context):
        """2段階確認付きでプレイヤーデータと専用チャンネルを削除する"""
        user = ctx.author
        user_id = str(user.id)

        if user_processing.get(user.id):
            await ctx.send("⚠️ 別の処理が実行中です。完了するまでお待ちください。", delete_after=5)
            return

        player = await get_player(user_id)

        if not player:
            await ctx.send(
                embed=discord.Embed(
                    title="未登録",
                    description="あなたはまだゲームを開始していません。`!start` を使ってゲームを開始してください。",
                    color=discord.Color.orange(),
                )
            )
            return

        embed = discord.Embed(
            title="データを削除しますか？",
            description="リセットするとプレイヤーデータは完全に削除されます。よろしいですか？\n\n※確認は2段階です。",
            color=discord.Color.red(),
        )
        # reset 実行時点のチャンネルIDを渡しておくと、最終確認ボタン押下時の削除が安定する
        view = ResetConfirmView(user.id, ctx.channel.id if getattr(ctx, "channel", None) else None)
        await ctx.send(embed=embed, view=view)
