from __future__ import annotations

from discord.ext import commands


def attach_bot_state(bot: commands.Bot):
    """cogs間で共有する状態を bot にぶら下げる（無ければ作る）。

    戻り値として (user_processing, user_locks) の参照も返す。
    """

    if not hasattr(bot, "user_processing") or bot.user_processing is None:
        bot.user_processing = {}
    if not hasattr(bot, "user_locks") or bot.user_locks is None:
        bot.user_locks = {}

    return bot.user_processing, bot.user_locks
