from __future__ import annotations

import logging
import discord
from discord.ext import commands

import db
from db import get_player
from views import NameRequestView

from runtime_settings import NOTIFY_CHANNEL_ID
from bot_utils import check_ban, is_guild_admin, try_get_existing_adventure_thread

logger = logging.getLogger("rpgbot")


def _get_bot_member(guild: discord.Guild, bot: commands.Bot) -> discord.Member | None:
    me = getattr(guild, "me", None)
    if isinstance(me, discord.Member):
        return me
    try:
        return guild.get_member(bot.user.id) if bot.user else None
    except Exception:
        return None


def _missing_thread_mode_permissions(guild: discord.Guild, channel: discord.TextChannel, bot: commands.Bot) -> tuple[list[str], list[str]]:
    """スレッド運用に必要/推奨の権限不足を返す。

    returns: (required_missing, recommended_missing)
    """

    bot_member = _get_bot_member(guild, bot)
    if bot_member is None:
        # 取得できない場合は診断不能として required に寄せる
        return (["BOTメンバー情報の取得"], [])

    perms = channel.permissions_for(bot_member)

    required: list[tuple[str, bool]] = [
        ("チャンネルを表示 (View Channel)", perms.view_channel),
        ("メッセージを送信 (Send Messages)", perms.send_messages),
        ("プライベートスレッドを作成 (Create Private Threads)", perms.create_private_threads),
        ("スレッドでメッセージを送信 (Send Messages in Threads)", perms.send_messages_in_threads),
        ("スレッドを管理 (Manage Threads)", perms.manage_threads),
    ]

    recommended: list[tuple[str, bool]] = [
        ("メッセージ履歴を読む (Read Message History)", perms.read_message_history),
        ("チャンネルを管理 (Manage Channels)", perms.manage_channels),
    ]

    required_missing = [name for name, ok in required if not ok]
    recommended_missing = [name for name, ok in recommended if not ok]
    return required_missing, recommended_missing


def setup_adventure_commands(bot: commands.Bot):
    user_processing = getattr(bot, "user_processing", {})

    @bot.command(name="set")
    @check_ban()
    async def set_guild_settings(ctx: commands.Context, mode: str | None = None):
        """サーバー設定（管理者のみ）: `!start` の作成先をスレッドにする/解除する

        - `!set` : 実行チャンネルを親として保存
        - `!set off` : 解除
        """

        if ctx.guild is None:
            await ctx.send("❌ DMでは使用できません")
            return

        if not is_guild_admin(ctx):
            await ctx.send("❌ このコマンドはサーバー管理者（管理/サーバー管理）専用です")
            return

        if mode and mode.strip().lower() in {"off", "disable", "0", "false"}:
            ok = await db.clear_guild_settings(ctx.guild.id)
            if ok:
                await ctx.send("✅ スレッド運用を解除しました。今後の `!start` は従来通りチャンネル作成になります。")
            else:
                await ctx.send("⚠️ 解除に失敗しました。Supabase側の `guild_settings` を確認してください。")
            return

        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("❌ `!set` は通常のテキストチャンネルで実行してください")
            return

        required_missing, recommended_missing = _missing_thread_mode_permissions(ctx.guild, ctx.channel, bot)
        if required_missing:
            lines = [
                "⚠️ このチャンネルでスレッド運用に必要なBOT権限が不足しています。",
                "管理者がBOTロールに以下を付与してから、もう一度 `!set` を実行してください。",
                "",
            ]
            lines += [f"- {name}" for name in required_missing]
            if recommended_missing:
                lines += ["", "（推奨）"]
                lines += [f"- {name}" for name in recommended_missing]
            await ctx.send("\n".join(lines))
            return

        ok = await db.set_guild_adventure_parent_channel(ctx.guild.id, ctx.channel.id)
        if ok:
            msg = (
                "✅ 設定しました。今後 `!start` はこのチャンネル配下に"
                "『プライベートスレッド（3日で自動アーカイブ）』を作成します。"
            )
            if recommended_missing:
                msg += "\n\n（推奨）BOT権限が一部不足しています:\n" + "\n".join(
                    [f"- {name}" for name in recommended_missing]
                )
            await ctx.send(msg)
        else:
            await ctx.send(
                "⚠️ 設定の保存に失敗しました。Supabaseに `guild_settings` テーブルが無い可能性があります。\n"
                "`create_guild_settings.sql` をSupabaseに適用してから再度お試しください。"
            )

    @bot.command(name="close")
    @check_ban()
    async def close_adventure_thread(ctx: commands.Context):
        """データは保持したまま、冒険スレッドだけ削除する（スレッド運用時）"""

        if ctx.guild is None:
            await ctx.send("❌ DMでは使用できません")
            return

        user = ctx.author

        if user_processing.get(user.id):
            await ctx.send("⚠️ 別の処理が実行中です。完了するまでお待ちください。", delete_after=5)
            return

        user_processing[user.id] = True
        try:
            player = await get_player(user.id)
            if not player:
                await ctx.send("!start で冒険を始めてね。")
                return

            thread = await try_get_existing_adventure_thread(ctx.guild, user.id)
            if thread is None:
                await ctx.send("⚠️ 削除できる冒険スレッドが見つかりませんでした。")
                await db.clear_adventure_thread(user.id)
                return

            try:
                await thread.delete(reason="User requested adventure thread deletion")
            except discord.Forbidden:
                await ctx.send("⚠️ スレッド削除権限がありません。BOTに `スレッドの管理` を付与してください。")
                return
            except Exception as e:
                await ctx.send(f"⚠️ スレッド削除に失敗しました: {e}")
                return

            await db.clear_adventure_thread(user.id)
            await ctx.send("✅ 冒険スレッドを削除しました。データは保持されています。必要なら `!start` で復活できます。")
        finally:
            user_processing[user.id] = False

    @bot.command(name="start")
    @check_ban()
    async def start(ctx: commands.Context):
        user = ctx.author
        user_id = str(user.id)

        if user_processing.get(user.id):
            await ctx.send("⚠️ 別の処理が実行中です。完了するまでお待ちください。", delete_after=5)
            return

        user_processing[user.id] = True
        try:
            if ctx.guild is None:
                await ctx.send("❌ DMでは開始できません。サーバー内で実行してください。")
                return

            existing_thread = await try_get_existing_adventure_thread(ctx.guild, user.id)
            if existing_thread is not None:
                try:
                    if existing_thread.archived:
                        await existing_thread.edit(archived=False)
                except Exception:
                    pass
                await ctx.send(f"⚠️ すでに冒険場所があります: {existing_thread.mention}", delete_after=15)
                return

            settings = await db.get_guild_settings(ctx.guild.id)
            parent_channel_id = None
            if isinstance(settings, dict):
                raw = settings.get("adventure_parent_channel_id") or settings.get("adventure_parent_channel")
                if raw:
                    try:
                        parent_channel_id = int(raw)
                    except (TypeError, ValueError):
                        parent_channel_id = None

            logger.debug(
                "start: guild=%s channel=%s parent_channel_id=%s",
                getattr(ctx.guild, "id", None),
                getattr(ctx.channel, "id", None),
                parent_channel_id,
            )

            # スレッド運用が有効な場合は、`!set` した親チャンネル以外からの `!start` を禁止
            if parent_channel_id and ctx.channel and ctx.channel.id != parent_channel_id:
                logger.debug(
                    "start rejected: wrong channel guild=%s user=%s channel=%s expected_parent=%s",
                    ctx.guild.id,
                    user.id,
                    ctx.channel.id,
                    parent_channel_id,
                )
                parent = ctx.guild.get_channel(parent_channel_id)
                if isinstance(parent, discord.TextChannel):
                    await ctx.send(f"❌ `!start` は {parent.mention} で実行してください。", delete_after=15)
                else:
                    await ctx.send("❌ `!start` の実行チャンネルが不正です。管理者に `!set` をやり直してもらってください。", delete_after=15)
                return

            player = await get_player(user_id)

            if player and player.get("name") and parent_channel_id:
                parent = ctx.guild.get_channel(parent_channel_id)
                if isinstance(parent, discord.TextChannel):
                    try:
                        try:
                            thread = await parent.create_thread(
                                name=f"{user.name}-冒険",
                                type=discord.ChannelType.private_thread,
                                auto_archive_duration=4320,
                                reason="RPG_BOT adventure thread revive",
                            )
                        except discord.HTTPException:
                            thread = await parent.create_thread(
                                name=f"{user.name}-冒険",
                                type=discord.ChannelType.private_thread,
                                auto_archive_duration=1440,
                                reason="RPG_BOT adventure thread revive (fallback)",
                            )
                        try:
                            await thread.add_user(user)
                        except Exception:
                            pass

                        await db.set_adventure_thread(user.id, thread.id, ctx.guild.id)
                        await ctx.send(f"✅ 冒険スレッドを復活しました！ {thread.mention}", delete_after=10)
                        await thread.send(f"{user.mention} さん、冒険を再開します。\nまずは `!move` で進んでみよう！")
                        return
                    except Exception as e:
                        await ctx.send(f"⚠️ スレッド復活に失敗しました: {e}\n（従来処理を続行します）")

            if player and player.get("name"):
                await ctx.send("⚠️ あなたはすでにゲームを開始しています！", delete_after=10)
                return

            if not player:
                await db.create_player(user.id)

            if parent_channel_id:
                parent = ctx.guild.get_channel(parent_channel_id)
                if not isinstance(parent, discord.TextChannel):
                    await ctx.send("⚠️ `!set` の設定チャンネルが見つからない/不正です。管理者に連絡してください。")
                else:
                    try:
                        try:
                            thread = await parent.create_thread(
                                name=f"{user.name}-冒険",
                                type=discord.ChannelType.private_thread,
                                auto_archive_duration=4320,
                                reason="RPG_BOT adventure thread",
                            )
                        except discord.HTTPException:
                            thread = await parent.create_thread(
                                name=f"{user.name}-冒険",
                                type=discord.ChannelType.private_thread,
                                auto_archive_duration=1440,
                                reason="RPG_BOT adventure thread (fallback)",
                            )

                        try:
                            await thread.add_user(user)
                        except Exception:
                            pass

                        await db.set_adventure_thread(user.id, thread.id, ctx.guild.id)

                        await ctx.send(f"✅ 冒険スレッドを作成しました！ {thread.mention}", delete_after=10)
                        await thread.send(f"{user.mention} さん！ようこそ 🎉\nここはあなた専用の冒険スレッドです。")

                        embed = discord.Embed(
                            title="📝 名前を入力しよう！",
                            description="これからの冒険で使うキャラクター名を決めてね！",
                            color=discord.Color.blue(),
                        )
                        view = NameRequestView(user.id, thread)
                        await thread.send(embed=embed, view=view)

                        try:
                            notify_channel = bot.get_channel(NOTIFY_CHANNEL_ID) if NOTIFY_CHANNEL_ID else None
                            if notify_channel:
                                await notify_channel.send(f"🎮 {user.mention} が新しい冒険を開始しました！")
                        except Exception as e:
                            logger.warning("通知送信エラー: %s", e, exc_info=True)

                        return
                    except discord.Forbidden:
                        await ctx.send(
                            "⚠️ スレッド作成に必要な権限が不足しています。\n"
                            "BOTに `スレッドの作成/管理`・`プライベートスレッドの作成` 等を付与してください。\n"
                            "（一旦、旧方式でチャンネル作成を試みます）"
                        )
                    except Exception as e:
                        await ctx.send(f"⚠️ スレッド作成に失敗しました: {e}\n（旧方式でチャンネル作成を試みます）")

            guild = ctx.guild
            category = discord.utils.get(guild.categories, name="RPG")
            if not category:
                category = await guild.create_category("RPG")

            existing_channel = None
            for ch in category.channels:
                if ch.topic and str(user.id) in ch.topic:
                    existing_channel = ch
                    break

            if existing_channel:
                await ctx.send(f"⚠️ すでにチャンネルが存在します: {existing_channel.mention}", delete_after=10)
                user_processing[user.id] = False
                return

            channel_name = f"{user.name}-冒険"

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            }

            channel = await guild.create_text_channel(
                channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"UserID:{user.id}",
            )

            await ctx.send(f"✅ 冒険チャンネルを作成しました！ {channel.mention}", delete_after=10)
            await channel.send(f"{user.mention} さん！ようこそ 🎉\nここはあなた専用の冒険チャンネルです。")

            embed = discord.Embed(
                title="📝 名前を入力しよう！",
                description="これからの冒険で使うキャラクター名を決めてね！",
                color=discord.Color.blue(),
            )
            view = NameRequestView(user.id, channel)
            await channel.send(embed=embed, view=view)

            try:
                notify_channel = bot.get_channel(NOTIFY_CHANNEL_ID) if NOTIFY_CHANNEL_ID else None
                if notify_channel:
                    await notify_channel.send(f"🎮 {user.mention} が新しい冒険を開始しました！")
            except Exception as e:
                logger.warning("通知送信エラー: %s", e, exc_info=True)
        except Exception as e:
            logger.exception("!startコマンドエラー: %s", e)
            await ctx.send(f"⚠️ エラーが発生しました: {e}", delete_after=10)
        finally:
            user_processing[user.id] = False
