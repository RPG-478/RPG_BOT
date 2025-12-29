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
from runtime_settings import (
    NOTIFY_CHANNEL_ID,
    SELECT_MAX_OPTIONS,
    VIEW_TIMEOUT_LONG,
    VIEW_TIMEOUT_SHORT,
)

logger = logging.getLogger("rpgbot")
class SpecialEventView(View):
    def __init__(self, user_id: int, user_processing: dict, distance: int):
        super().__init__(timeout=VIEW_TIMEOUT_SHORT)
        self.user_id = user_id
        self.user_processing = user_processing
        self.distance = distance

    @button(label="🔨 鍛冶屋", style=discord.ButtonStyle.primary)
    async def blacksmith_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これはあなたのイベントではありません！", ephemeral=True)
            return

        await interaction.response.defer()

        player = await get_player(interaction.user.id)
        if not player:
            embed = discord.Embed(
                title="⚠️ エラー",
                description="プレイヤーデータが見つかりません。",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed, view=None)
            return

        inventory = player.get("inventory", [])
        materials = {}
        for item in inventory:
            if item in game.MATERIAL_PRICES:
                materials[item] = materials.get(item, 0) + 1

        if not materials:
            embed = discord.Embed(
                title="🔨 鍛冶屋",
                description="「おっと、素材が何もないようだな。素材を集めてきてくれ」\n\n他の選択肢を選んでください。",
                color=discord.Color.orange()
            )
            for child in self.children:
                if child.label == "🔨 鍛冶屋":
                    child.disabled = True
            await interaction.edit_original_response(embed=embed, view=self)
            return

        from ui.shops import BlacksmithView
        view = BlacksmithView(self.user_id, self.user_processing, materials)
        await interaction.edit_original_response(content=None, embed=view.get_embed(), view=view)

    @button(label="💰 素材商人", style=discord.ButtonStyle.success)
    async def material_merchant_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これはあなたのイベントではありません！", ephemeral=True)
            return

        await interaction.response.defer()

        player = await get_player(interaction.user.id)
        if not player:
            embed = discord.Embed(
                title="⚠️ エラー",
                description="プレイヤーデータが見つかりません。",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed, view=None)
            return

        inventory = player.get("inventory", [])
        materials = {}
        for item in inventory:
            if item in game.MATERIAL_PRICES:
                materials[item] = materials.get(item, 0) + 1

        if not materials:
            embed = discord.Embed(
                title="💰 素材商人",
                description="「素材が何もないのか？もったいない…」\n\n他の選択肢を選んでください。",
                color=discord.Color.orange()
            )
            for child in self.children:
                if child.label == "💰 素材商人":
                    child.disabled = True
            await interaction.edit_original_response(embed=embed, view=self)
            return

        from ui.shops import MaterialMerchantView
        view = MaterialMerchantView(self.user_id, self.user_processing, materials)
        await interaction.edit_original_response(content=None, embed=view.get_embed(), view=view)

    @button(label="📖 ストーリー", style=discord.ButtonStyle.secondary)
    async def story_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これはあなたのイベントではありません！", ephemeral=True)
            return

        await interaction.response.defer()

        stories = [
            {
                "title": "古の碑文",
                "description": "壁に刻まれた文字を発見した。\n\n「深淵を覗く者は、深淵にも覗かれている」\n\n…不吉な予感がする。注意して進もう。",
                "reward": "wisdom_bonus"
            },
            {
                "title": "謎の声",
                "description": "???「よう。お前も勇敢だな。とっとと逃げた方がいいぜ。逃げられない？どうにか頑張ってくれ」\n\n誰かの声が聞こえた気がした。\n誰なんだこの無責任すぎるやつは……",
                "reward": "courage_bonus"
            },
            {
                "title": "休息の泉",
                "description": "不思議な泉を発見した。\n水を飲むと体力が回復した！\n\n現在のHP[100]",
                "reward": "hp_restore"
            }
        ]

        story = random.choice(stories)

        embed = discord.Embed(
            title=f"📖 {story['title']}",
            description=story['description'],
            color=discord.Color.purple()
        )

        if story['reward'] == "hp_restore":
            player = await get_player(interaction.user.id)
            if player:
                max_hp = player.get("max_hp", 50)
                await update_player(interaction.user.id, hp=max_hp)
                embed.add_field(name="✨ 効果", value="HPが全回復した！", inline=False)

        await interaction.edit_original_response(embed=embed, view=None)

        if self.user_id in self.user_processing:
            self.user_processing[self.user_id] = False

    async def on_timeout(self):
        """タイムアウト時にuser_processingをクリア"""
        if self.user_id in self.user_processing:
            self.user_processing[self.user_id] = False


# ==============================
# ラスボスクリア時のアイテム持ち帰りView
# ==============================
from collections import Counter

class FinalBossClearView(discord.ui.View):
    def __init__(self, user_id: int, ctx, user_processing: dict, boss_stage: int):
        super().__init__(timeout=VIEW_TIMEOUT_LONG)
        self.user_id = user_id
        self.ctx = ctx
        self.user_processing = user_processing
        self.boss_stage = boss_stage

    @classmethod
    async def create(cls, user_id: int, ctx, user_processing: dict, boss_stage: int):
        """Async factory method to create and initialize FinalBossClearView"""
        instance = cls(user_id, ctx, user_processing, boss_stage)
        await instance._async_init()
        return instance

    async def _async_init(self):
        """Async initialization logic"""
        # クリア処理を実行
        clear_result = await db.handle_boss_clear(self.user_id)

        # インベントリからアイテム選択プルダウンを作成
        player = await db.get_player(self.user_id)
        inventory = player.get("inventory", []) if player else []

        if inventory:
            # アイテムをカウント（集約）
            item_counts = Counter(inventory)
            
            # アイテムを選択肢に変換（最大25個）
            options = []
            for i, (item_name, count) in enumerate(list(item_counts.items())[:SELECT_MAX_OPTIONS]):
                item_info = game.get_item_info(item_name)
                item_type = item_info.get("type", "material") if item_info else "material"

                # 絵文字を選択
                emoji_map = {
                    "weapon": "⚔️",
                    "armor": "🛡️",
                    "potion": "🧪",
                    "material": "📦"
                }
                emoji = emoji_map.get(item_type, "📦")

                # ラベルに個数表示
                label = f"{item_name} ×{count}" if count > 1 else item_name
                desc = f"{item_type.upper()} - {item_info.get('description', '')[:50]}" if item_info else item_type.upper()

                options.append(discord.SelectOption(
                    label=label,
                    description=desc,
                    value=f"{i}_{item_name}",  # インデックスを付けて重複回避
                    emoji=emoji
                ))

            # プルダウンを作成
            select = discord.ui.Select(
                placeholder="倉庫に持ち帰るアイテムを1つ選択...",
                options=options,
                custom_id="storage_select"
            )
            select.callback = self.store_item
            self.add_item(select)

    async def store_item(self, interaction: discord.Interaction):
        """選択されたアイテムを倉庫に保管"""
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("これはあなたの選択ではありません！", ephemeral=True)

        selected_value = interaction.data['values'][0]
        
        # valueから型とアイテム名を分離
        parts = selected_value.split("_", 1)
        if len(parts) < 2:
            return await interaction.response.send_message("不正な選択です。", ephemeral=True)
        
        idx, selected_item = parts

        # アイテム情報取得
        item_info = game.get_item_info(selected_item)
        item_type = item_info.get("type", "material") if item_info else "material"

        # 倉庫に保存
        success = await db.add_to_storage(interaction.user.id, selected_item, item_type)

        if success:
            embed = discord.Embed(
                title="📦 アイテムを倉庫に保管しました",
                description=f"**{selected_item}** を倉庫に保管しました。\n次回 `!start` 時に倉庫から取り出せます。\n\n**!reset** でデータをリセットして新しい冒険を始めましょう！",
                color=discord.Color.green()
            )
            embed.add_field(
                name="⚠️ 重要",
                value="このダンジョンは踏破済です。`!reset` を実行するまで `!move` などのコマンドは使用できません。",
                inline=False
            )
        else:
            embed = discord.Embed(
                title="⚠️ エラー",
                description="倉庫への保管に失敗しました。サポートサーバーにお問い合わせください。\n**!resetを行わないでください**",
                color=discord.Color.red()
            )

        await interaction.response.edit_message(embed=embed, view=None)

        # 通知チャンネルへ送信
        try:
            notification_channel = self.ctx.bot.get_channel(NOTIFY_CHANNEL_ID) if NOTIFY_CHANNEL_ID else None
            if notification_channel:
                notify_embed = discord.Embed(
                    title="🎉 ラスボス討伐成功！",
                    description=f"**{interaction.user.name}** がラスボスを討伐し、**{selected_item}** を倉庫に保管した！",
                    color=discord.Color.gold()
                )
                await notification_channel.send(embed=notify_embed)
        except Exception as e:
            print(f"通知チャンネルへの送信エラー: {e}")

        # boss_postストーリー表示
        story_id = f"boss_post_{self.boss_stage}"
        if not await db.get_story_flag(interaction.user.id, story_id):
            await asyncio.sleep(2)
            from story import StoryView
            view = StoryView(interaction.user.id, story_id, self.user_processing)
            await view.send_story(self.ctx)
            return

        if self.ctx.author.id in self.user_processing:
            self.user_processing[self.ctx.author.id] = False

    async def on_timeout(self):
        """タイムアウト時にuser_processingをクリア"""
        if self.ctx.author.id in self.user_processing:
            self.user_processing[self.ctx.author.id] = False

# ==============================
# ラスボス戦View
# ==============================
