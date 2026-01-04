from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

import db
import game
from bot_state import attach_bot_state
from emoji_rpg.view import EmojiRPGResult, EmojiRPGView
from views import BattleView


def setup_emoji_command(bot: commands.Bot) -> None:
    """TEMP: EmojiRPG テスト用コマンドを登録する。"""

    # main.py と同様に bot に共有状態がぶら下がる前提だが、念のため確保しておく
    attach_bot_state(bot)

    @bot.command(name="emoji")
    async def emoji_test(ctx: commands.Context, map_id: str = "demo_25x25"):
        """絵文字RPG（テスト用）。

        使い方:
        - `!emoji` / `!emoji demo_11x11`
        """

        # 本編プレイヤーがいる前提（ステータス反映するため）
        player = await db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ 本編プレイヤーデータが見つかりません。先に `!start` してください。")
            return

        async def on_finish(result: EmojiRPGResult, interaction: discord.Interaction):
            # 既に interaction.response を使っている可能性があるので message.edit を使う
            embed = view.get_embed()
            outcome_label = {
                "win": "🏁 クリア！",
                "lose": "💀 敗北",
                "timeout": "⌛ タイムアウト",
            }.get(result.outcome, result.outcome)
            embed.set_footer(text=f"結果: {outcome_label} / テスト用: !emoji")
            try:
                await interaction.message.edit(embed=embed, view=view)
            except Exception:
                pass

        async def on_encounter(interaction: discord.Interaction):
            """絵文字RPG中のエンカウント: その場のメッセージを本編BattleViewに差し替え、終了後に復帰する。"""
            try:
                # 最新のプレイヤー状態を取得（本編ステータス反映）
                fresh_player = await db.get_player(interaction.user.id)
                if not fresh_player:
                    try:
                        await interaction.followup.send(
                            "❌ 本編プレイヤーデータが見つかりません（`!start` が必要です）。",
                            ephemeral=True,
                        )
                    except Exception:
                        pass
                    return

                # 本編の敵テーブルを使って敵を抽選（絵文字RPG側の地域レベルでスケール）
                region_level = getattr(view, "region_level", 1)
                enemy = game.get_random_enemy_by_region_level(region_level)

                class _InteractionCtx:
                    def __init__(self, interaction: discord.Interaction):
                        self.author = interaction.user
                        self.channel = interaction.channel

                    async def send(self, *args, **kwargs):
                        if self.channel is None:
                            return None
                        return await self.channel.send(*args, **kwargs)

                ctx_stub = _InteractionCtx(interaction)

                # 戦闘終了後に、元の絵文字RPG Embed/Viewへ戻す
                async def restore_after_battle(outcome: str, enemy_hp: int, enemy_max_hp: int):
                    async def _restore():
                        # BattleView側の最終編集（ボタン無効化等）の後に上書きするため、少しだけ遅延
                        await asyncio.sleep(0.25)
                        try:
                            # 近接ボタン状態を再計算（位置は戦闘で変わらないが、UIだけ整える）
                            try:
                                view._refresh_near_object_and_buttons()  # type: ignore[attr-defined]
                            except Exception:
                                pass
                            embed = view.get_embed()
                            embed.set_footer(text=f"戦闘結果: {outcome} / 続きをどうぞ")
                            await interaction.message.edit(embed=embed, view=view)
                        except Exception:
                            pass

                    asyncio.create_task(_restore())

                user_processing = getattr(bot, "user_processing", {})
                battle_view = await BattleView.create(
                    ctx_stub,
                    fresh_player,
                    enemy,
                    user_processing,
                    post_battle_hook=restore_after_battle,
                )
                battle_view.message = interaction.message
                battle_embed = await battle_view.create_battle_embed()
                await interaction.message.edit(embed=battle_embed, view=battle_view)
            except Exception as e:
                try:
                    await interaction.followup.send(f"⚠️ エンカウント処理に失敗しました: {e}", ephemeral=True)
                except Exception:
                    pass

        try:
            view = EmojiRPGView(
                user_id=ctx.author.id,
                map_id=map_id,
                on_finish=on_finish,
                on_encounter=on_encounter,
                title=f"EmojiRPG ({map_id})",
                timeout=900,
            )
        except Exception as e:
            await ctx.send(f"❌ map_id={map_id!r} の読み込みに失敗しました: {e}")
            return

        await ctx.send(embed=view.get_embed(), view=view)
