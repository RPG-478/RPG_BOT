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
from runtime_settings import VIEW_TIMEOUT_MEDIUM

logger = logging.getLogger("rpgbot")
class ResetConfirmView(discord.ui.View):
    def __init__(self, author_id: int, cached_channel_id: int | None = None):
        super().__init__(timeout=VIEW_TIMEOUT_MEDIUM)  # 2分でキャンセル
        self.author_id = author_id
        # ボタン押された時に使うため、呼び出し元で channel_id を渡しておくと安全
        self.cached_channel_id = cached_channel_id

    @discord.ui.button(label="削除する", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 誰でも押せない。実行者以外は弾く
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("これはあなた専用の確認です。", ephemeral=True)

        # 1回目確認OK → 別 View に差し替え（2段階目）
        embed = discord.Embed(
            title="本当に削除しますか？（最終確認）",
            description="ここで該当データとチャンネルを完全に削除します。取り消しは不可能です。 \nよければ「本当に削除する」を押してください。",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=ResetFinalConfirmView(self.author_id, self.cached_channel_id))

    @discord.ui.button(label="いいえ（キャンセル）", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("これはあなた専用の確認です。", ephemeral=True)
        embed = discord.Embed(title="キャンセルされました", description="データの削除は実行されませんでした。引き続き[イニシエダンジョン]をお楽しみください――", color=discord.Color.dark_gray())
        await interaction.response.edit_message(embed=embed, view=None)

# -------------------------
# Reset 用 View（2段階目：最終確認）
# -------------------------
class ResetFinalConfirmView(discord.ui.View):
    def __init__(self, author_id: int, cached_channel_id: int | None = None):
        super().__init__(timeout=VIEW_TIMEOUT_MEDIUM)
        self.author_id = author_id
        self.cached_channel_id = cached_channel_id

    @discord.ui.button(label="本当に削除する", style=discord.ButtonStyle.danger)
    async def final_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("これはあなた専用の確認です。", ephemeral=True)

        user_id_str = str(self.author_id)

        # 削除対象が「今いるスレッド」の場合、削除後に元メッセージが消えて edit_message が 404 になり得る。
        # 先に defer しておき、最終的には followup で完了通知できるようにする。
        try:
            await interaction.response.defer(ephemeral=True)
            deferred = True
        except Exception:
            deferred = False

        logger.debug(
            "reset.final_confirm: user=%s guild=%s channel_id=%s cached_channel_id=%s",
            self.author_id,
            getattr(interaction.guild, "id", None),
            getattr(interaction, "channel_id", None),
            self.cached_channel_id,
        )

        # 先に削除対象情報を回収（DB削除後だと thread_id が取れないため）
        player_before_delete = None
        try:
            player_before_delete = await get_player(user_id_str)
        except Exception:
            player_before_delete = None

        logger.debug(
            "reset: player_before_delete=%s",
            "found" if player_before_delete else "missing",
        )

        flags = (player_before_delete.get("milestone_flags", {}) if player_before_delete else {}) or {}
        raw_thread_id = flags.get("_adventure_thread_id")
        try:
            stored_thread_id = int(raw_thread_id) if raw_thread_id is not None else None
        except (TypeError, ValueError):
            stored_thread_id = None

        logger.debug(
            "reset: stored_thread_id=%s (raw=%s)",
            stored_thread_id,
            raw_thread_id,
        )

        # スレッド/チャンネル削除（可能なら先に消しておく）
        thread_deleted = False
        channel_deleted = False
        missing_permissions = False
        guild = interaction.guild

        # 1) 保存済み thread_id を最優先で削除
        if guild and stored_thread_id:
            try:
                thread = guild.get_thread(stored_thread_id)
                if thread is None:
                    try:
                        ch = await guild.fetch_channel(stored_thread_id)
                        thread = ch if isinstance(ch, discord.Thread) else None
                    except Exception:
                        thread = None

                if thread is not None:
                    await thread.delete(reason="User reset")
                    thread_deleted = True
                    logger.debug("reset: deleted stored thread_id=%s", stored_thread_id)
                else:
                    logger.debug("reset: stored thread_id=%s not found in guild", stored_thread_id)
            except discord.Forbidden as e:
                missing_permissions = True
                logger.warning("reset: failed deleting stored thread_id=%s: %s", stored_thread_id, e)
                thread_deleted = False
            except Exception as e:
                logger.warning("reset: failed deleting stored thread_id=%s: %s", stored_thread_id, e)
                thread_deleted = False

        # 2) cached_channel_id / interaction.channel が冒険スレッドなら削除
        if guild and not thread_deleted:
            candidate_ids: list[int] = []
            seen: set[int] = set()
            if isinstance(self.cached_channel_id, int) and self.cached_channel_id not in seen:
                candidate_ids.append(self.cached_channel_id)
                seen.add(self.cached_channel_id)
            if interaction.channel_id and int(interaction.channel_id) not in seen:
                candidate_ids.append(int(interaction.channel_id))
                seen.add(int(interaction.channel_id))

            logger.debug("reset: candidate thread ids=%s", candidate_ids)

            for cid in candidate_ids:
                try:
                    ch = guild.get_thread(cid)
                    if ch is None:
                        fetched = await guild.fetch_channel(cid)
                        ch = fetched if isinstance(fetched, discord.Thread) else None
                    if ch is not None:
                        await ch.delete(reason="User reset")
                        thread_deleted = True
                        logger.debug("reset: deleted thread via candidate_id=%s", cid)
                        break
                except discord.Forbidden as e:
                    missing_permissions = True
                    logger.debug("reset: candidate delete forbidden id=%s err=%s", cid, e)
                    continue
                except Exception as e:
                    logger.debug("reset: candidate delete failed id=%s err=%s", cid, e)
                    continue

        # 3) 旧方式の冒険チャンネル削除（topic の UserID を使って特定）
        if guild:
            try:
                target = None
                # まず RPG カテゴリ内を探索
                category = discord.utils.get(guild.categories, name="RPG")
                if category:
                    for ch in category.channels:
                        if isinstance(ch, discord.TextChannel) and ch.topic and f"UserID:{self.author_id}" in ch.topic:
                            target = ch
                            break
                # 無ければ全体から探索
                if target is None:
                    for ch in guild.text_channels:
                        if ch.topic and f"UserID:{self.author_id}" in ch.topic:
                            target = ch
                            break

                if target is not None:
                    await target.delete(reason="User reset")
                    channel_deleted = True
                    logger.debug("reset: deleted adventure channel id=%s", target.id)
                else:
                    logger.debug("reset: adventure channel not found by topic UserID:%s", self.author_id)
            except discord.Forbidden as e:
                missing_permissions = True
                logger.warning("reset: adventure channel delete forbidden: %s", e)
                channel_deleted = False
            except Exception as e:
                logger.warning("reset: adventure channel delete failed: %s", e)
                channel_deleted = False

        # DBから削除（最後）
        try:
            await delete_player(user_id_str)
            logger.debug("reset: delete_player done user=%s", self.author_id)
        except Exception as e:
            logger.warning("reset: delete_player failed user=%s err=%s", self.author_id, e)

        # 完了メッセージ
        if thread_deleted:
            description = "プレイヤーデータとスレッドを削除しました。"
        elif channel_deleted:
            description = "プレイヤーデータとチャンネルを削除しました。"
        else:
            if missing_permissions:
                description = (
                    "プレイヤーデータを削除しましたが、チャンネル/スレッド削除が権限不足で失敗しました。\n"
                    "BOTの権限に『スレッドの管理』(推奨: 可能なら『チャンネルの管理』も)を付与してください。"
                )
            else:
                description = "プレイヤーデータを削除しました。チャンネル/スレッドが見つからなかったか、削除に失敗しました。\n\n管理者をお呼びください。"

        embed = discord.Embed(
            title="削除完了", 
            description=description, 
            color=discord.Color.green()
        )

        # 可能なら元メッセージを更新、消えていたらフォローアップで通知
        try:
            if not deferred and not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=None)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.NotFound:
            # スレッド削除などで元メッセージが消えた
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except Exception as e:
                logger.warning("reset: failed to send completion followup: %s", e)

    @discord.ui.button(label="いいえ（戻る）", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("これはあなた専用の確認です。", ephemeral=True)
        embed = discord.Embed(title="キャンセルされました。引き続き[イニシエダンジョン]をお楽しみください――", color=discord.Color.dark_gray())
        await interaction.response.edit_message(embed=embed, view=None)



from discord.ui import View, button

