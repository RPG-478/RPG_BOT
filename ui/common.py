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

logger = logging.getLogger("rpgbot")
async def handle_death_with_triggers(ctx, user_id, user_processing, enemy_name=None, enemy_type="normal"):
    """
    死亡処理 + ストーリー/称号トリガーを統合
    全ての戦闘クラスから呼び出される共通処理
    """
    # 死亡処理
    death_result = await db.handle_player_death(
        user_id, 
        killed_by_enemy_name=enemy_name, 
        enemy_type=enemy_type
    )

    # トリガーチェック
    trigger_result = await death_system.check_death_triggers(user_id)

    # ストーリーイベント発動
    if trigger_result["type"] == "story":
        from story import StoryView
        story_view = StoryView(user_id, trigger_result["story_id"], user_processing)
        await story_view.send_story(ctx)

    # 称号獲得
    elif trigger_result["type"] == "title":
        title_data = trigger_result["data"]
        embed = discord.Embed(
            title=f"{get_title_rarity_emoji(trigger_result['title_id'])} 称号獲得！",
            description=f"**{title_data['name']}** を獲得しました！\n\n{title_data['description']}",
            color=get_title_rarity_color(trigger_result['title_id'])
        )
        await ctx.send(embed=embed)

    return death_result

