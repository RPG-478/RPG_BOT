from __future__ import annotations

import discord
from discord.ext import commands

import db
import death_system
from bot_utils import check_ban
from db import get_player


def setup_death_commands(bot: commands.Bot) -> None:
    @bot.command(name="death_stats", aliases=["ds"])
    @check_ban()
    async def death_stats(ctx: commands.Context):
        """死亡統計を表示"""
        user = ctx.author
        player = await get_player(user.id)

        if not player:
            await ctx.send("!start で冒険を始めてみてね。")
            return

        total_deaths = await db.get_death_count(user.id)
        top_killers = await db.get_top_death_killers(user.id)

        if total_deaths <= 0:
            embed = discord.Embed(
                title="💀 死亡統計",
                description="まだ一度も死亡していません。\n\n慎重な冒険者ですね！",
                color=discord.Color.green(),
            )
            await ctx.send(embed=embed)
            return

        # トップ5の敵を表示
        killer_list = ""
        for i, (enemy_name, count) in enumerate(top_killers[:5], 1):
            killer_list += f"{i}. **{enemy_name}** - {count}回\n"

        if not killer_list:
            killer_list = "データがありません"

        embed = discord.Embed(
            title=f"💀 {player.get('name', 'あなた')}の死亡統計",
            description=f"総死亡回数: **{total_deaths}回**\n\n## よく殺された敵 TOP5\n{killer_list}",
            color=discord.Color.red(),
        )

        # ストーリー進行状況
        story_progress = await death_system.get_death_story_progress(user.id)
        embed.add_field(
            name="📖 死亡ストーリー進行",
            value=f"{story_progress['unlocked']}/{story_progress['total']} ({story_progress['percentage']:.1f}%)",
            inline=True,
        )

        embed.set_footer(text="!death_history で詳細な履歴を確認できます")

        await ctx.send(embed=embed)

    @bot.command(name="death_history", aliases=["dh"])
    @check_ban()
    async def death_history(ctx: commands.Context, limit: int = 10):
        """最近の死亡履歴を表示"""
        user = ctx.author
        player = await get_player(user.id)

        if not player:
            await ctx.send("!start で冒険を始めてみてね。")
            return

        if limit < 1 or limit > 50:
            await ctx.send("⚠️ 表示件数は1〜50の範囲で指定してください。")
            return

        recent_deaths = await db.get_recent_deaths(user.id, limit)

        if not recent_deaths:
            embed = discord.Embed(
                title="💀 死亡履歴",
                description="まだ一度も死亡していません。",
                color=discord.Color.green(),
            )
            await ctx.send(embed=embed)
            return

        # 履歴をフォーマット
        history_text = ""
        for i, death in enumerate(recent_deaths, 1):
            enemy_name = death.get("enemy_name", "不明")
            distance = death.get("distance", 0)
            floor = death.get("floor", 0)
            enemy_type_icon = "👑" if death.get("enemy_type") == "boss" else "⚔️"

            history_text += f"{i}. {enemy_type_icon} **{enemy_name}** ({distance}m / {floor}階層)\n"

        embed = discord.Embed(
            title=f"💀 最近の死亡履歴 (直近{len(recent_deaths)}件)",
            description=history_text,
            color=discord.Color.dark_red(),
        )

        embed.set_footer(text="!death_stats で統計を確認できます")

        await ctx.send(embed=embed)
