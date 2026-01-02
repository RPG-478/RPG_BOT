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


async def finalize_view_on_timeout(
    view: discord.ui.View,
    *,
    user_processing: dict | None = None,
    user_id: int | None = None,
    message: discord.Message | None = None,
) -> None:
    """Viewのタイムアウト時に、最低限の後片付けを行う。

    - 子要素（Button/Select）を無効化
    - message が分かるなら view を更新
    - user_processing を解除

    注意: on_timeout は Interaction を持たないため、できる範囲で best-effort に行う。
    """

    # user_id の推測（battle系など）
    inferred_user_id = user_id
    if inferred_user_id is None:
        try:
            inferred_user_id = int(getattr(view, "user_id"))  # type: ignore[arg-type]
        except Exception:
            inferred_user_id = None
    if inferred_user_id is None:
        try:
            ctx = getattr(view, "ctx", None)
            inferred_user_id = int(getattr(getattr(ctx, "author", None), "id", None))
        except Exception:
            inferred_user_id = None

    if user_processing is not None and inferred_user_id is not None:
        if inferred_user_id in user_processing:
            user_processing[inferred_user_id] = False

    # ボタン等の無効化
    try:
        for child in list(getattr(view, "children", [])):
            if hasattr(child, "disabled"):
                child.disabled = True
    except Exception:
        pass

    # message は呼び出し側で渡すのが確実。無ければ view.message を試す。
    msg = message
    if msg is None:
        try:
            m = getattr(view, "message", None)
            msg = m if isinstance(m, discord.Message) else None
        except Exception:
            msg = None

    if msg is not None:
        try:
            await msg.edit(view=view)
        except Exception:
            # 既に削除/権限/古いメッセージなど
            pass

