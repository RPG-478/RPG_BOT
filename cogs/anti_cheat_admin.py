from __future__ import annotations

import logging
from discord.ext import commands

logger = logging.getLogger("rpgbot")


async def setup(bot: commands.Bot):
    """admin_anti_cheat.py の管理コマンド登録を extension 化。"""
    import admin_anti_cheat

    admin_anti_cheat.setup_admin_commands(bot)
    logger.info("✅ Loaded extension: cogs.anti_cheat_admin")
