"""
デバッグコマンドシステム
- 管理者専用コマンド（User ID制限付き）
- ユーザー向けロールバックシステム
- エラーログ管理
"""

import discord
from discord.ext import commands
import db
import logging
from datetime import datetime, timedelta
from typing import Optional
import json
import asyncio
import copy

logger = logging.getLogger("rpgbot")

# ==============================
# 管理者ID定義
# ==============================
ADMIN_IDS = [1301416493401243694, 785051117323026463]

# ==============================
# エラーログストレージ
# ==============================
class ErrorLogManager:
    """エラーログを管理するクラス"""
    def __init__(self, max_logs=100):
        self.logs = []
        self.max_logs = max_logs
    
    def add_error(self, error_type: str, message: str, user_id: Optional[int] = None, context: Optional[str] = None):
        """エラーログを追加"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": error_type,
            "message": message,
            "user_id": user_id,
            "context": context
        }
        self.logs.append(log_entry)
        
        # 最大数を超えたら古いものから削除
        if len(self.logs) > self.max_logs:
            self.logs = self.logs[-self.max_logs:]
        
        logger.error(f"[ErrorLog] {error_type}: {message} (User: {user_id}, Context: {context})")
    
    def get_recent_logs(self, limit: int = 10):
        """最近のエラーログを取得"""
        return self.logs[-limit:]
    
    def get_user_logs(self, user_id: int, limit: int = 5):
        """特定ユーザーのエラーログを取得"""
        user_logs = [log for log in self.logs if log.get("user_id") == user_id]
        return user_logs[-limit:]
    
    def clear_logs(self):
        """全ログをクリア"""
        self.logs = []

# グローバルエラーログマネージャー
error_log_manager = ErrorLogManager()

# ==============================
# ユーザースナップショット管理
# ==============================
class SnapshotManager:
    """ユーザーアクションのスナップショットを管理"""
    def __init__(self):
        self.snapshots = {}  # user_id: [snapshot1, snapshot2, ...]
    
    async def create_snapshot(self, user_id: int, action_type: str, player_data: dict):
        """スナップショットを作成（ディープコピーで完全な独立性を確保）"""
        if user_id not in self.snapshots:
            self.snapshots[user_id] = []
        
        # ディープコピーで完全に独立したスナップショットを作成
        # これにより、inventory、milestone_flags、equipped_weaponなどの
        # ネストされた可変オブジェクトも完全にコピーされる
        try:
            # JSON経由でディープコピー（最も安全な方法）
            player_data_copy = json.loads(json.dumps(player_data, default=str)) if player_data else None
        except (TypeError, ValueError):
            # JSON化できない場合はcopy.deepcopyを使用
            player_data_copy = copy.deepcopy(player_data) if player_data else None
        
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "action_type": action_type,
            "data": player_data_copy
        }
        
        self.snapshots[user_id].append(snapshot)
        
        # 最大5個まで保持
        if len(self.snapshots[user_id]) > 5:
            self.snapshots[user_id] = self.snapshots[user_id][-5:]
        
        logger.info(f"Snapshot created (deep copy) for user {user_id}: {action_type}")
    
    def get_last_snapshot(self, user_id: int) -> Optional[dict]:
        """最後のスナップショットを取得"""
        if user_id in self.snapshots and len(self.snapshots[user_id]) > 0:
            return self.snapshots[user_id][-1]
        return None
    
    def remove_last_snapshot(self, user_id: int):
        """最後のスナップショットを削除（ロールバック後）"""
        if user_id in self.snapshots and len(self.snapshots[user_id]) > 0:
            self.snapshots[user_id].pop()

# グローバルスナップショットマネージャー
snapshot_manager = SnapshotManager()

# ==============================
# 管理者チェックデコレーター
# ==============================
def admin_only():
    """管理者専用コマンドチェック"""
    async def predicate(ctx: commands.Context):
        if ctx.author.id not in ADMIN_IDS:
            await ctx.send("⛔ このコマンドは管理者専用です。", delete_after=5)
            return False
        return True
    return commands.check(predicate)

# ==============================
# 管理者専用コマンド
# ==============================

@commands.command(name="admin_stats")
@admin_only()
async def admin_stats(ctx: commands.Context):
    """システム統計を表示"""
    try:
        # プレイヤー数をカウント
        all_players = await db.get_all_players()
        total_players = len(all_players) if all_players else 0
        
        # アクティブプレイヤー（距離>0）
        active_players = len([p for p in all_players if p.get("distance", 0) > 0]) if all_players else 0
        
        # 最も進んでいるプレイヤー
        max_distance_player = max(all_players, key=lambda p: p.get("distance", 0)) if all_players else None
        
        embed = discord.Embed(
            title="📊 システム統計",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="総プレイヤー数", value=f"{total_players}人", inline=True)
        embed.add_field(name="アクティブプレイヤー", value=f"{active_players}人", inline=True)
        embed.add_field(name="エラーログ数", value=f"{len(error_log_manager.logs)}件", inline=True)
        
        if max_distance_player:
            embed.add_field(
                name="最遠到達プレイヤー",
                value=f"{max_distance_player.get('name', 'Unknown')} - {max_distance_player.get('distance', 0)}m",
                inline=False
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        error_log_manager.add_error("ADMIN_STATS", str(e), ctx.author.id, "admin_stats command")
        await ctx.send(f"⚠️ エラーが発生しました: {e}")

@commands.command(name="admin_logs")
@admin_only()
async def admin_logs(ctx: commands.Context, limit: int = 10):
    """最近のエラーログを表示"""
    try:
        logs = error_log_manager.get_recent_logs(min(limit, 25))
        
        if not logs:
            await ctx.send("📝 エラーログはありません。")
            return
        
        embed = discord.Embed(
            title=f"🔍 最近のエラーログ (最大{len(logs)}件)",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        for i, log in enumerate(logs[-10:], 1):  # 最大10件表示
            timestamp = log.get("timestamp", "Unknown")
            error_type = log.get("type", "Unknown")
            message = log.get("message", "No message")[:100]  # 100文字まで
            user_id = log.get("user_id", "N/A")
            
            embed.add_field(
                name=f"{i}. {error_type} ({timestamp[:19]})",
                value=f"User: {user_id}\nMessage: {message}",
                inline=False
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"⚠️ ログの取得に失敗しました: {e}")

@commands.command(name="admin_clear_logs")
@admin_only()
async def admin_clear_logs(ctx: commands.Context):
    """エラーログをクリア"""
    log_count = len(error_log_manager.logs)
    error_log_manager.clear_logs()
    await ctx.send(f"✅ {log_count}件のエラーログをクリアしました。")

@commands.command(name="admin_ban")
@admin_only()
async def admin_ban(ctx: commands.Context, user_id: str):
    """ユーザーをBAN"""
    try:
        await db.ban_player(user_id)
        await ctx.send(f"🔨 ユーザーID `{user_id}` をBANしました。")
        logger.warning(f"Admin {ctx.author.id} banned user {user_id}")
    except Exception as e:
        await ctx.send(f"⚠️ BANに失敗しました: {e}")

@commands.command(name="admin_unban")
@admin_only()
async def admin_unban(ctx: commands.Context, user_id: str):
    """ユーザーのBANを解除"""
    try:
        await db.unban_player(user_id)
        await ctx.send(f"✅ ユーザーID `{user_id}` のBANを解除しました。")
        logger.warning(f"Admin {ctx.author.id} unbanned user {user_id}")
    except Exception as e:
        await ctx.send(f"⚠️ BAN解除に失敗しました: {e}")

@commands.command(name="admin_player")
@admin_only()
async def admin_player(ctx: commands.Context, user_id: str):
    """プレイヤー情報を表示"""
    try:
        player = await db.get_player(user_id)
        
        if not player:
            await ctx.send(f"⚠️ ユーザーID `{user_id}` のデータが見つかりません。")
            return
        
        embed = discord.Embed(
            title=f"👤 プレイヤー情報: {player.get('name', 'Unknown')}",
            color=discord.Color.green()
        )
        
        embed.add_field(name="User ID", value=user_id, inline=True)
        embed.add_field(name="HP", value=f"{player.get('hp', 0)}/{player.get('max_hp', 0)}", inline=True)
        embed.add_field(name="距離", value=f"{player.get('distance', 0)}m", inline=True)
        embed.add_field(name="ゴールド", value=f"{player.get('gold', 0)}G", inline=True)
        embed.add_field(name="死亡回数", value=f"{player.get('death_count', 0)}回", inline=True)
        embed.add_field(name="レベル", value=f"{player.get('level', 1)}", inline=True)
        embed.add_field(name="BAN状態", value="🔨 BAN中" if player.get('is_banned') else "✅ 正常", inline=True)
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"⚠️ プレイヤー情報の取得に失敗しました: {e}")

@commands.command(name="admin_clear_processing")
@admin_only()
async def admin_clear_processing(ctx: commands.Context, user_id: int):
    """ユーザーのprocessingフラグをクリア（Embed固まり対策）"""
    try:
        # user_processing辞書から削除
        if hasattr(ctx.bot, 'user_processing'):
            if user_id in ctx.bot.user_processing:
                ctx.bot.user_processing[user_id] = False
                await ctx.send(f"✅ ユーザーID `{user_id}` のprocessingフラグをクリアしました。")
            else:
                await ctx.send(f"ℹ️ ユーザーID `{user_id}` のprocessingフラグは設定されていません。")
        else:
            await ctx.send("⚠️ user_processing辞書が見つかりません。")
        
        logger.info(f"Admin {ctx.author.id} cleared processing flag for user {user_id}")
        
    except Exception as e:
        await ctx.send(f"⚠️ クリアに失敗しました: {e}")

@commands.command(name="admin_force_reset")
@admin_only()
async def admin_force_reset(ctx: commands.Context, user_id: str):
    """プレイヤーデータを強制リセット"""
    try:
        await db.delete_player(user_id)
        await ctx.send(f"✅ ユーザーID `{user_id}` のデータを削除しました。")
        logger.warning(f"Admin {ctx.author.id} force reset user {user_id}")
    except Exception as e:
        await ctx.send(f"⚠️ リセットに失敗しました: {e}")

# ==============================
# ユーザー向けコマンド
# ==============================

@commands.command(name="rollback")
async def rollback(ctx: commands.Context):
    """最後のアクションを取り消す"""
    user_id = ctx.author.id
    
    try:
        # スナップショットを取得
        snapshot = snapshot_manager.get_last_snapshot(user_id)
        
        if not snapshot:
            embed = discord.Embed(
                title="⚠️ ロールバックできません",
                description="最近のアクション記録が見つかりませんでした。\n\n**!move**、戦闘、装備変更などのアクション後に使用できます。",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return
        
        # スナップショットデータを復元
        snapshot_data = snapshot.get("data")
        if not snapshot_data:
            await ctx.send("⚠️ スナップショットデータが無効です。")
            return
        
        # DBに復元
        await db.restore_player_snapshot(user_id, snapshot_data)
        
        # スナップショットを削除
        snapshot_manager.remove_last_snapshot(user_id)
        
        action_type = snapshot.get("action_type", "不明なアクション")
        timestamp = snapshot.get("timestamp", "")[:19]
        
        embed = discord.Embed(
            title="⏪ ロールバック成功",
            description=f"**{action_type}** を取り消しました。\n\n時刻: {timestamp}\n\nプレイヤーデータが復元されました。",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        
        logger.info(f"User {user_id} rolled back action: {action_type}")
        
    except Exception as e:
        error_log_manager.add_error("ROLLBACK", str(e), user_id, "rollback command")
        await ctx.send(f"⚠️ ロールバックに失敗しました: {e}")

@commands.command(name="debug_status")
async def debug_status(ctx: commands.Context):
    """自分のデバッグ情報を表示"""
    user_id = ctx.author.id
    
    try:
        player = await db.get_player(user_id)
        
        if not player:
            await ctx.send("⚠️ プレイヤーデータが見つかりません。`!start` でゲームを開始してください。")
            return
        
        # processingフラグの状態
        processing_status = "処理中" if ctx.bot.user_processing.get(user_id, False) else "待機中"
        
        # 最後のスナップショット
        snapshot = snapshot_manager.get_last_snapshot(user_id)
        snapshot_info = "なし"
        if snapshot:
            action = snapshot.get("action_type", "不明")
            timestamp = snapshot.get("timestamp", "")[:19]
            snapshot_info = f"{action} ({timestamp})"
        
        # エラーログ
        user_errors = error_log_manager.get_user_logs(user_id, 3)
        error_count = len(user_errors)
        
        embed = discord.Embed(
            title="🔧 デバッグ情報",
            description=f"{ctx.author.mention} の状態",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="処理状態", value=processing_status, inline=True)
        embed.add_field(name="距離", value=f"{player.get('distance', 0)}m", inline=True)
        embed.add_field(name="HP", value=f"{player.get('hp', 0)}/{player.get('max_hp', 0)}", inline=True)
        embed.add_field(name="最後のスナップショット", value=snapshot_info, inline=False)
        embed.add_field(name="最近のエラー数", value=f"{error_count}件", inline=True)
        
        if error_count > 0:
            last_error = user_errors[-1]
            embed.add_field(
                name="最新エラー",
                value=f"{last_error.get('type', 'Unknown')}: {last_error.get('message', 'No message')[:100]}",
                inline=False
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"⚠️ デバッグ情報の取得に失敗しました: {e}")

# ==============================
# コマンド登録ヘルパー
# ==============================

def setup_debug_commands(bot: commands.Bot):
    """デバッグコマンドをBotに登録"""
    bot.add_command(admin_stats)
    bot.add_command(admin_logs)
    bot.add_command(admin_clear_logs)
    bot.add_command(admin_ban)
    bot.add_command(admin_unban)
    bot.add_command(admin_player)
    bot.add_command(admin_clear_processing)
    bot.add_command(admin_force_reset)
    bot.add_command(rollback)
    bot.add_command(debug_status)
    
    logger.info("✅ デバッグコマンドを登録しました")

# ==============================
# エクスポート
# ==============================

__all__ = [
    'setup_debug_commands',
    'error_log_manager',
    'snapshot_manager',
    'ErrorLogManager',
    'SnapshotManager'
]
