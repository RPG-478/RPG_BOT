from __future__ import annotations

import discord
from discord.ext import commands
from functools import wraps

import db


def is_guild_admin(ctx: commands.Context) -> bool:
    perms = getattr(ctx.author, "guild_permissions", None)
    if not perms:
        return False
    return bool(perms.administrator or perms.manage_guild)


async def try_get_existing_adventure_thread(
    guild: discord.Guild,
    user_id: int,
) -> discord.Thread | None:
    thread_id = await db.get_adventure_thread_id(user_id)
    if not thread_id:
        return None
    thread = guild.get_thread(thread_id)
    if thread is not None:
        return thread
    try:
        ch = await guild.fetch_channel(thread_id)
        if isinstance(ch, discord.Thread):
            return ch
    except Exception:
        return None
    return None


def check_ban():
    """BAN確認デコレーター"""

    def decorator(func):
        @wraps(func)
        async def wrapper(ctx: commands.Context, *args, **kwargs):
            user_id = str(ctx.author.id)

            if await db.is_player_banned(user_id):
                embed = discord.Embed(
                    title="❌ BOT利用禁止",
                    description="あなたはBOT利用禁止処分を受けています。\n\n運営チームにお問い合わせください。",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)
                return

            return await func(ctx, *args, **kwargs)

        return wrapper

    return decorator
