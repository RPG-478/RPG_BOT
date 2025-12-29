from __future__ import annotations

from discord.ext import commands

import adventure_commands


async def setup(bot: commands.Bot):
    # 既存の bot.command ベース実装を extension としてロードできるようにするラッパ
    adventure_commands.setup_adventure_commands(bot)
