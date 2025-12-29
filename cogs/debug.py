from __future__ import annotations

import logging
from discord.ext import commands

logger = logging.getLogger("rpgbot")


async def setup(bot: commands.Bot):
    """debug_commands.py の登録処理を extension 化。

    既存の setup_debug_commands(bot) を呼び出してコマンド登録するだけなので、
    挙動を変えずに main.py を軽くできる。
    """
    from debug_commands import setup_debug_commands, error_log_manager, snapshot_manager

    # main.py 側で bot.user_processing を共有dictとして設定している前提。
    if not hasattr(bot, "user_processing"):
        bot.user_processing = {}

    bot.error_log_manager = error_log_manager
    bot.snapshot_manager = snapshot_manager

    setup_debug_commands(bot)
    logger.info("✅ Loaded extension: cogs.debug")
