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
from runtime_settings import NOTIFY_CHANNEL_ID, VIEW_TIMEOUT_TREASURE
from settings.balance import TREASURE_COIN_MAX, TREASURE_COIN_MIN, TREASURE_RARE_CHANCE

logger = logging.getLogger("rpgbot")
class TreasureView(View):
    def __init__(self, user_id: int, user_processing: dict):
        super().__init__(timeout=VIEW_TIMEOUT_TREASURE)
        self.user_id = user_id
        self.user_processing = user_processing
        self.message = None

    # ==============================
    # 「開ける」ボタン
    # ==============================
    @button(label="開ける", style=discord.ButtonStyle.green)
    async def open_treasure(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これは君の宝箱じゃない！", ephemeral=True)
            return

        # メッセージを保存
        if not self.message:
            self.message = interaction.message

        await interaction.response.defer()

        # 通常宝箱は必ず報酬
        await self.handle_reward(interaction)

        # ボタン無効化
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        # 処理完了フラグをクリア
        if self.user_id in self.user_processing:
            self.user_processing[self.user_id] = False

    # ==============================
    # 「開けない」ボタン
    # ==============================
    @button(label="開けない", style=discord.ButtonStyle.red)
    async def ignore_treasure(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これは君の宝箱じゃない！", ephemeral=True)
            return

        # メッセージを保存
        if not self.message:
            self.message = interaction.message

        embed = discord.Embed(
            title="💨 宝箱を無視した",
            description="慎重な判断だ……何も起こらなかった。",
            color=discord.Color.dark_grey()
        )
        await interaction.response.edit_message(embed=embed, view=None)

        # 処理完了フラグをクリア
        if self.user_id in self.user_processing:
            self.user_processing[self.user_id] = False

    # ==============================
    # 宝箱報酬処理
    # ==============================
    async def handle_reward(self, interaction: discord.Interaction):
        player = await get_player(interaction.user.id)
        if not player:
            embed = discord.Embed(
                title="⚠️ エラー",
                description="プレイヤーデータが見つかりません。`!start` でゲームを開始してください。",
                color=discord.Color.red()
            )
            msg = self.message or interaction.message
            await msg.edit(embed=embed, view=None)
            return

        embed = None
        secret_weapon_hit = False

        # シークレット武器の超低確率抽選（0.1% = 1/1000）
        if random.random() < TREASURE_RARE_CHANCE:
            available_weapons = await db.get_available_secret_weapons()

            if available_weapons:
                secret_weapon = random.choice(available_weapons)

                await db.add_secret_weapon(interaction.user.id, secret_weapon['id'])
                await db.add_item_to_inventory(interaction.user.id, secret_weapon['name'])
                await db.increment_global_weapon_count(secret_weapon['id'])

                embed = discord.Embed(
                    title="……なんだこれは――。",
                    description=f"**{secret_weapon['name']}** と書いてある……シークレット武器というものらしい。\n\n{secret_weapon['ability']}\n⚔️ 攻撃力: {secret_weapon['attack']}\nとてつもなく強力な力が備わっている。注意しよう",
                    color=discord.Color.purple()
                )

                secret_weapon_hit = True

                try:
                    bot = interaction.client
                    log_channel = bot.get_channel(NOTIFY_CHANNEL_ID) if NOTIFY_CHANNEL_ID else None
                    if log_channel:
                        await log_channel.send(
                            f" **{interaction.user.mention} がシークレット武器を発見！**\n"
                            f"**{secret_weapon['name']}** を手に入れた！\n"
                            f"レアリティ: {secret_weapon['rarity']}\n"
                            f"サーバー: {interaction.guild.name}"
                        )
                except Exception as e:
                    print(f"グローバルログ通知エラー: {e}")
        
        # シークレット武器が出た場合はそのEmbedを表示
        if secret_weapon_hit and embed:
            msg = self.message or interaction.message
            await interaction.followup.send(embed=embed)
        else:
            # 通常の宝箱報酬を処理
            await self.open_treasure_box(interaction, player, secret_weapon_hit)

    async def open_treasure_box(self, interaction, player, secret_weapon_hit):
        if not secret_weapon_hit:
            reward_type = random.choices(
                ["coins", "weapon"],
                weights=[70, 30],
                k=1
            )[0]

            if reward_type == "coins":
                amount = random.randint(TREASURE_COIN_MIN, TREASURE_COIN_MAX)
                await db.add_gold(interaction.user.id, amount)

                embed = discord.Embed(
                    title="💰 宝箱の中身",
                    description=f"{amount}ゴールドを手に入れた！",
                    color=discord.Color.gold()
                )

            else:
                distance = player.get("distance", 0)
                available_equipment = game.get_treasure_box_equipment(distance)
                weapon_name = random.choice(available_equipment) if available_equipment else "木の剣"
                await db.add_item_to_inventory(interaction.user.id, weapon_name)
                item_info = game.get_item_info(weapon_name)

                embed = discord.Embed(
                    title="🗡️ 宝箱の中身",
                    description=f"**{weapon_name}** を手に入れた！\n\n{item_info.get('description', '')}",
                    color=discord.Color.green()
                )

            msg = self.message or interaction.message
            await msg.edit(embed=embed, view=None)


    # ==============================
    # トラップ発動処理
    # ==============================
    async def handle_trap(self, interaction: discord.Interaction, trap_type: str):
        player = await get_player(interaction.user.id)
        if not player:
            embed = discord.Embed(
                title="⚠️ エラー",
                description="プレイヤーデータが見つかりません。`!start` でゲームを開始してください。",
                color=discord.Color.red()
            )
            msg = self.message or interaction.message
            await msg.edit(embed=embed, view=None)
            return

        msg = self.message or interaction.message

        # --- HP20%ダメージ ---
        if trap_type == "damage":
            damage = int(player.get("hp", 50) * 0.2)
            new_hp = max(0, player.get("hp", 50) - damage)
            await update_player(interaction.user.id, hp=new_hp)

            embed = discord.Embed(
                title="💥 トラップ発動！",
                description=f"爆発が起きた！\n{damage}のダメージを受けた！\nこのダンジョンにはトラップチェストがある。気をつけよう――。\n\n残りHP: {new_hp}",
                color=discord.Color.red()
            )
            await msg.edit(embed=embed, view=None)


        # --- 奇襲（戦闘突入） ---
        elif trap_type == "ambush":
            embed = discord.Embed(
                title="😈 奇襲発生！",
                description="突如、敵が現れた！戦闘に備えて――",
                color=discord.Color.dark_red()
            )
            await msg.edit(embed=embed, view=None)

    async def on_timeout(self):
        """タイムアウト時にuser_processingをクリア"""
        if self.user_id in self.user_processing:
            self.user_processing[self.user_id] = False

# ==============================
# トラップ宝箱View
# ==============================
class TrapChestView(View):
    def __init__(self, user_id: int, user_processing: dict, player: dict):
        super().__init__(timeout=VIEW_TIMEOUT_TREASURE)
        self.user_id = user_id
        self.user_processing = user_processing
        self.player = player

    @button(label="開ける", style=discord.ButtonStyle.danger)
    async def open_trap_chest(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これは君の宝箱じゃない！", ephemeral=True)
            return

        await interaction.response.defer()

        # トラップ必ず発動
        trap_types = ["damage", "remove_weapon", "ambush"]
        trap_type = random.choice(trap_types)

        await self.handle_trap(interaction, trap_type)

        # ボタン無効化
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        # 処理完了フラグをクリア
        if self.user_id in self.user_processing:
            self.user_processing[self.user_id] = False

    @button(label="開けない", style=discord.ButtonStyle.secondary)
    async def ignore_trap_chest(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これは君の宝箱じゃない！", ephemeral=True)
            return

        embed = discord.Embed(
            title="🚶 立ち去った",
            description="見るからに怪しい宝箱を開けずに立ち去った。\n賢明な判断だ…",
            color=discord.Color.dark_grey()
        )
        await interaction.response.edit_message(embed=embed, view=None)

        # 処理完了フラグをクリア
        if self.user_id in self.user_processing:
            self.user_processing[self.user_id] = False

    async def handle_trap(self, interaction: discord.Interaction, trap_type: str):
        player = await get_player(interaction.user.id)
        if not player:
            embed = discord.Embed(
                title="⚠️ エラー",
                description="プレイヤーデータが見つかりません。",
                color=discord.Color.red()
            )
            await interaction.message.edit(embed=embed, view=None)
            return

        if trap_type == "damage":
            damage = random.randint(10, 20)
            new_hp = max(1, player.get("hp", 50) - damage)
            await update_player(interaction.user.id, hp=new_hp)

            embed = discord.Embed(
                title="💥 トラップ発動！",
                description=f"毒ガスが噴出した！\n{damage}のダメージを受けた！\n残りHP: {new_hp}",
                color=discord.Color.red()
            )
            await interaction.message.edit(embed=embed, view=None)

        elif trap_type == "ambush":
            embed = discord.Embed(
                title="😈 奇襲発生！",
                description="突如、敵が現れた！戦闘に備えて――",
                color=discord.Color.dark_red()
            )
            await interaction.message.edit(embed=embed, view=None)

            await asyncio.sleep(2)

            distance = player.get("distance", 0)
            enemy = game.get_random_enemy(distance)

            player_data = {
                "hp": player.get("hp", 50),
                "attack": player.get("attack", 5),
                "defense": player.get("defense", 2),
                "inventory": player.get("inventory", []),
                "distance": distance,
                "user_id": interaction.user.id
            }

            try:
                class FakeContext:
                    def __init__(self, interaction):
                        self.interaction = interaction
                        self.author = interaction.user
                        self.channel = interaction.channel

                    async def send(self, *args, **kwargs):
                        return await self.channel.send(*args, **kwargs)

                fake_ctx = FakeContext(interaction)
                view = await BattleView.create(fake_ctx, player_data, enemy, self.user_processing)
                await view.send_initial_embed()
            except Exception as e:
                print(f"[Error] BattleView transition failed: {e}")

    async def on_timeout(self):
        """タイムアウト時にuser_processingをクリア"""
        if self.user_id in self.user_processing:
            self.user_processing[self.user_id] = False

# ==============================
# 500m特殊イベントView
# ==============================
