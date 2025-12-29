from __future__ import annotations

from discord.ext import commands

import player_commands


async def setup(bot: commands.Bot):
    player_commands.setup_player_commands(bot)
