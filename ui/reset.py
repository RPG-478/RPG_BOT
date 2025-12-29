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
        # DBから削除
        await delete_player(user_id_str)

        # スレッド運用の場合は、保存済み thread_id を優先して削除
        thread_deleted = False
        try:
            player = await db.get_player(self.author_id)
            flags = (player.get("milestone_flags", {}) if player else {}) or {}
            raw_thread_id = flags.get("_adventure_thread_id")
            thread_id = int(raw_thread_id) if raw_thread_id is not None else None

            if thread_id and interaction.guild:
                thread = interaction.guild.get_thread(thread_id)
                if thread is None:
                    try:
                        ch = await interaction.guild.fetch_channel(thread_id)
                        thread = ch if isinstance(ch, discord.Thread) else None
                    except Exception:
                        thread = None

                if thread is not None:
                    await thread.delete()
                    thread_deleted = True
        except Exception:
            thread_deleted = False

        # チャンネル削除処理
        guild = interaction.guild
        user = interaction.user
        channel_name = f"{user.name}-冒険"

        # RPGカテゴリ内の該当チャンネルを検索
        category = discord.utils.get(guild.categories, name="RPG")
        if category:
            channel = discord.utils.get(category.channels, name=channel_name.lower())
            if channel:
                try:
                    await channel.delete()
                    channel_deleted = True
                except:
                    channel_deleted = False
            else:
                channel_deleted = False
        else:
            channel_deleted = False

        # 完了メッセージ
        if thread_deleted:
            description = "プレイヤーデータとスレッドを削除しました。"
        elif channel_deleted:
            description = "プレイヤーデータとチャンネルを削除しました。"
        else:
            description = "プレイヤーデータを削除しました。チャンネル/スレッドが見つからなかったか、削除に失敗しました。\n\n管理者をお呼びください。"

        embed = discord.Embed(
            title="削除完了", 
            description=description, 
            color=discord.Color.green()
        )

        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="いいえ（戻る）", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("これはあなた専用の確認です。", ephemeral=True)
        embed = discord.Embed(title="キャンセルされました。引き続き[イニシエダンジョン]をお楽しみください――", color=discord.Color.dark_gray())
        await interaction.response.edit_message(embed=embed, view=None)



from discord.ui import View, button

