import discord
import db
import random
import asyncio
import game
import config
import logging
from discord.ui import View, button, Select
from db import get_player, update_player, delete_player
import death_system
from titles import get_title_rarity_emoji, get_title_rarity_color
from runtime_settings import (
    NOTIFY_CHANNEL_ID,
    SELECT_MAX_OPTIONS,
    SELECT_MAX_POTION_OPTIONS,
    VIEW_TIMEOUT_SHORT,
)

from settings import balance as balance_settings
from ui.events import FinalBossClearView

logger = logging.getLogger("rpgbot")
from ui.common import handle_death_with_triggers, finalize_view_on_timeout

class FinalBossBattleView(View):
    def __init__(self, ctx, player, boss, user_processing: dict, boss_stage: int):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.player = player
        self.boss = boss
        self._boss_max_hp = int(boss.get("hp", 0) or 0)
        self.message = None
        self.user_processing = user_processing
        self.boss_stage = boss_stage
        self._battle_lock = asyncio.Lock()

    @classmethod
    async def create(cls, ctx, player, boss, user_processing: dict, boss_stage: int):
        """Async factory method to create and initialize FinalBossBattleView"""
        instance = cls(ctx, player, boss, user_processing, boss_stage)
        await instance._async_init()
        return instance

    async def _async_init(self):
        """Async initialization logic"""
        if "user_id" in self.player:
            fresh_player = await db.get_player(self.player["user_id"])
            if fresh_player:
                self.player.update({
                    "hp": fresh_player.get("hp", self.player.get("hp", 50)),
                    "max_hp": fresh_player.get("max_hp", self.player.get("max_hp", 50)),
                    "mp": fresh_player.get("mp", self.player.get("mp", 20)),
                    "max_mp": fresh_player.get("max_mp", self.player.get("max_mp", 20)),
                    "attack": fresh_player.get("atk", self.player.get("attack", 5)),
                    "defense": fresh_player.get("def", self.player.get("defense", 2))
                })
            
            equipment_bonus = await game.calculate_equipment_bonus(self.player["user_id"])
            self.player["attack"] = self.player.get("attack", 5) + equipment_bonus["attack_bonus"]
            self.player["defense"] = self.player.get("defense", 2) + equipment_bonus["defense_bonus"]

            unlocked_skills = await db.get_unlocked_skills(self.player["user_id"])
            if unlocked_skills:
                skill_options = []
                for skill_id in unlocked_skills[:SELECT_MAX_OPTIONS]:
                    skill_info = game.get_skill_info(skill_id)
                    if skill_info:
                        skill_options.append(discord.SelectOption(
                            label=skill_info["name"],
                            description=f"MP:{skill_info['mp_cost']} - {skill_info['description'][:50]}",
                            value=skill_id
                        ))

                if skill_options:
                    skill_select = discord.ui.Select(
                        placeholder="スキルを選択",
                        options=skill_options,
                        custom_id="final_skill_select"
                    )
                    skill_select.callback = self.use_skill
                    self.add_item(skill_select)

    async def send_initial_embed(self):
        embed = await self.create_battle_embed()
        self.message = await self.ctx.send(embed=embed, view=self)

    async def create_battle_embed(self):
        boss_hp = int(self.boss.get("hp", 0) or 0)
        boss_max_hp = int(self._boss_max_hp or boss_hp or 0)
        boss_atk = int(self.boss.get("atk", 0) or 0)
        boss_def = int(self.boss.get("def", 0) or 0)

        player_hp = int(self.player.get("hp", 0) or 0)
        player_atk = int(self.player.get("attack", 0) or 0)
        player_def = int(self.player.get("defense", 0) or 0)

        mp = None
        max_mp = None
        max_hp = int(self.player.get("max_hp", player_hp) or player_hp or 0)
        if "user_id" in self.player:
            player_data = await db.get_player(self.player["user_id"])
            if player_data:
                mp = int(player_data.get("mp", 20) or 20)
                max_mp = int(player_data.get("max_mp", 20) or 20)
                max_hp = int(player_data.get("max_hp", max_hp) or max_hp)

        is_critical = (player_hp > 0) and (player_hp <= 5)
        is_low = (player_hp > 0) and (not is_critical) and (max_hp > 0) and (player_hp <= max(1, int(max_hp * 0.25)))

        if is_critical:
            color = discord.Color.red()
            warning_line = "💀 **瀕死です！** 回復を強く推奨"
        elif is_low:
            color = discord.Color.orange()
            warning_line = "⚠️ **HPが少ないです。** 回復を推奨"
        else:
            color = discord.Color.dark_gold()
            warning_line = ""

        boss_is_critical = (boss_hp > 0) and (boss_max_hp > 0) and (boss_hp <= max(1, int(boss_max_hp * 0.15)))
        boss_is_low = (boss_hp > 0) and (boss_max_hp > 0) and (not boss_is_critical) and (boss_hp <= max(1, int(boss_max_hp * 0.30)))

        boss_name = str(self.boss.get("name", "ラスボス") or "ラスボス")
        if boss_is_critical:
            boss_name += "（瀕死）"
            boss_hp_suffix = " 💀"
        elif boss_is_low:
            boss_name += "（弱っている）"
            boss_hp_suffix = " ⚠️"
        else:
            boss_hp_suffix = ""

        enemy_line = (
            f"👑 **{boss_name}**\n"
            f"HP **{boss_hp}/{boss_max_hp}**{boss_hp_suffix} / ATK **{boss_atk}** / DEF **{boss_def}**"
        )

        if mp is not None and max_mp is not None:
            player_line = (
                "🧍 **あなた**\n"
                f"HP **{player_hp}/{max_hp}** / MP **{mp}/{max_mp}** / ATK **{player_atk}** / DEF **{player_def}**"
            )
        else:
            player_line = (
                "🧍 **あなた**\n"
                f"HP **{player_hp}/{max_hp}** / ATK **{player_atk}** / DEF **{player_def}**"
            )

        parts = []
        if warning_line:
            parts.append(warning_line)
        parts.append(enemy_line)
        parts.append(player_line)

        embed = discord.Embed(
            title="⚔️ 最終決戦！",
            description="\n\n".join(parts),
            color=color,
        )
        embed.set_footer(text="▶ 行動を選択してください")
        return embed

    def _format_battle_log(self, text: str) -> str:
        import re

        if not text:
            return ""

        text = re.sub(
            r"あなたの攻撃！\s*(\d+)\s*のダメージを与えた！",
            r"⚔️ あなたの攻撃！ **\1** ダメージ",
            text,
        )
        text = re.sub(
            r"敵の反撃！\s*(\d+)\s*のダメージを受けた！",
            r"💥 敵の反撃！ **\1** ダメージ",
            text,
        )
        text = re.sub(
            r"ボスの反撃！\s*(\d+)\s*のダメージを受けた！",
            r"💥 ボスの反撃！ **\1** ダメージ",
            text,
        )
        text = re.sub(
            r"ラスボスの反撃！\s*(\d+)\s*のダメージを受けた！",
            r"💥 ラスボスの反撃！ **\1** ダメージ",
            text,
        )
        text = re.sub(
            r"ラスボスの攻撃で\s*(\d+)\s*のダメージを受けた！",
            r"💥 ラスボスの攻撃！ **\1** ダメージ",
            text,
        )

        text = text.replace("\n💥 ", "\n\n💥 ")
        return text

    async def _staged_update(self, first_text: str, second_text: str | None = None, first_delay: float = 1.0, second_delay: float = 0.5):
        if first_delay and first_delay > 0:
            await asyncio.sleep(first_delay)
        await self.update_embed(first_text)
        if second_text is not None:
            if second_delay and second_delay > 0:
                await asyncio.sleep(second_delay)
            await self.update_embed(second_text)

    async def update_embed(self, text=""):
        embed = await self.create_battle_embed()
        if text:
            log_text = self._format_battle_log(text)
            embed.description += f"\n\n— 戦闘ログ —\n{log_text}"
        await self.message.edit(embed=embed, view=self)

    # =====================================
    # ✨ スキル使用
    # =====================================
    async def use_skill(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("これはあなたの戦闘ではありません！", ephemeral=True)

        # アトミックなロックチェック（ロック取得できなければ処理中）
        if self._battle_lock.locked():
            return await interaction.response.send_message("⚠️ 処理中です。少々お待ちください。", ephemeral=True)
        
        async with self._battle_lock:
            try:
                # ボタンを即座に無効化
                for child in self.children:
                    child.disabled = True
                await self.message.edit(view=self)

                # ✅ プレイヤーデータを最新化
                fresh_player_data = await db.get_player(interaction.user.id)
                if fresh_player_data:
                    self.player["hp"] = fresh_player_data.get("hp", self.player["hp"])
                    self.player["mp"] = fresh_player_data.get("mp", self.player.get("mp", 20))
                    self.player["max_hp"] = fresh_player_data.get("max_hp", self.player.get("max_hp", 50))
                    self.player["max_mp"] = fresh_player_data.get("max_mp", self.player.get("max_mp", 20))
                    
                    # ✅ 装備ボーナスを再計算してattackとdefenseを更新
                    base_atk = fresh_player_data.get("atk", 5)
                    base_def = fresh_player_data.get("def", 2)
                    equipment_bonus = await game.calculate_equipment_bonus(interaction.user.id)
                    self.player["attack"] = base_atk + equipment_bonus["attack_bonus"]
                    self.player["defense"] = base_def + equipment_bonus["defense_bonus"]
                    if config.VERBOSE_DEBUG:
                        logger.debug(
                            "use_skill player refreshed: hp=%s mp=%s atk=%s+%s=%s",
                            self.player["hp"],
                            self.player["mp"],
                            base_atk,
                            equipment_bonus["attack_bonus"],
                            self.player["attack"],
                        )

                if await db.is_mp_stunned(interaction.user.id):
                    await db.set_mp_stunned(interaction.user.id, False)
                    await interaction.response.send_message("⚠️ MP枯渇で行動不能！\n『嘘だろ!?』\n次のターンから行動可能になります。", ephemeral=True)
                    # ボタンを再有効化
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return

                skill_id = interaction.data['values'][0]
                skill_info = game.get_skill_info(skill_id)

                if not skill_info:
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return await interaction.response.send_message("⚠️ スキル情報が見つかりません。", ephemeral=True)

                player_data = await db.get_player(interaction.user.id)
                current_mp = player_data.get("mp", 20)
                mp_cost = skill_info["mp_cost"]

                if current_mp < mp_cost:
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return await interaction.response.send_message(f"⚠️ MPが足りません！（必要: {mp_cost}, 現在: {current_mp}）", ephemeral=True)

                if not await db.consume_mp(interaction.user.id, mp_cost):
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return await interaction.response.send_message("⚠️ MP消費に失敗しました。", ephemeral=True)

                player_data = await db.get_player(interaction.user.id)
                if player_data and player_data.get("mp", 0) == 0:
                    await db.set_mp_stunned(interaction.user.id, True)

                text = f"✨ **{skill_info['name']}** を使用！（MP -{mp_cost}）\n"

                if skill_info["type"] == "attack":
                    base_damage = game.calculate_physical_damage(self.player["attack"], self.boss["def"], -3, 3)
                    skill_damage = int(base_damage * skill_info["power"])
                    self.boss["hp"] -= skill_damage
                    text += f"⚔️ {skill_damage} のダメージを与えた！"

                    if self.boss["hp"] <= 0:
                        await db.update_player(interaction.user.id, hp=self.player["hp"])
                        distance = self.player.get("distance", 0)
                        drop_result = game.get_enemy_drop(self.boss["name"], distance)

                        drop_text = ""
                        if drop_result:
                            if drop_result["type"] == "coins":
                                await db.add_gold(interaction.user.id, drop_result["amount"])
                                drop_text = f"\n💰 **{drop_result['amount']}コイン** を手に入れた！"
                            elif drop_result["type"] == "item":
                                await db.add_item_to_inventory(interaction.user.id, drop_result["name"])
                                drop_text = f"\n🎁 **{drop_result['name']}** を手に入れた！"

                        await self.update_embed(text + "\n🏆 敵を倒した！" + drop_text)
                        self.disable_all_items()
                        await self.message.edit(view=self)
                        if self.ctx.author.id in self.user_processing:
                            self.user_processing[self.ctx.author.id] = False
                        await interaction.response.defer()
                        return

                    enemy_dmg = game.calculate_physical_damage(self.boss["atk"], self.player["defense"], -2, 2)
                    self.player["hp"] -= enemy_dmg
                    self.player["hp"] = max(0, self.player["hp"])
                    text += f"\n敵の反撃！ {enemy_dmg} のダメージを受けた！"

                    if self.player["hp"] <= 0:
                        death_result = await handle_death_with_triggers(
                            self.ctx if hasattr(self, 'ctx') else interaction.channel,
                            interaction.user.id, 
                            self.user_processing if hasattr(self, 'user_processing') else {},
                            enemy_name=getattr(self, 'enemy', {}).get('name') or getattr(self, 'boss', {}).get('name') or '不明',
                            enemy_type='boss' if hasattr(self, 'boss') else 'normal'
                        )
                        if death_result:
                            await self.update_embed(text + f"\n💀 あなたは倒れた…\n\n🔄 リスタート\n📍 アップグレードポイント: +{death_result['points']}pt")
                        else:
                            await self.update_embed(text + "\n💀 あなたは倒れた…")
                        self.disable_all_items()
                        await self.message.edit(view=self)
                        if self.ctx.author.id in self.user_processing:
                            self.user_processing[self.ctx.author.id] = False
                        await interaction.response.defer()
                        return

                elif skill_info["type"] == "heal":
                    heal_amount = skill_info["heal_amount"]
                    max_hp = self.player.get("max_hp", 50)
                    old_hp = self.player["hp"]
                    self.player["hp"] = min(max_hp, self.player["hp"] + heal_amount)
                    actual_heal = self.player["hp"] - old_hp
                    text += f"💚 HP+{actual_heal} 回復した！"

                await db.update_player(interaction.user.id, hp=self.player["hp"])
                await self.update_embed(text)
                # ボタンを再有効化
                for child in self.children:
                    child.disabled = False
                await self.message.edit(view=self)
                await interaction.response.defer()
            
            except Exception as e:
                logger.exception("[BattleView] use_skill error: %s", e)
                # エラー時もボタンを再有効化
                for child in self.children:
                    child.disabled = False
                try:
                    await self.message.edit(view=self)
                    if not interaction.response.is_done():
                        await interaction.response.send_message("⚠️ エラーが発生しました。もう一度お試しください。", ephemeral=True)
                except:
                    pass

    @button(label="戦う", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def fight(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("これはあなたの戦闘ではありません！", ephemeral=True)

        if self._battle_lock.locked():
            return await interaction.response.send_message("⚠️ 処理中です。少々お待ちください。", ephemeral=True)

        # 先にdeferしてタイムアウトを回避
        await interaction.response.defer()

        async with self._battle_lock:
            try:
                # ボタンを即座に無効化
                for child in self.children:
                    child.disabled = True
                await self.message.edit(view=self)

                if await db.is_mp_stunned(interaction.user.id):
                    await db.set_mp_stunned(interaction.user.id, False)
                    text = "⚠️ MP枯渇で行動不能…次のターンから行動可能になります。"
                    await self.update_embed(text)
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return

                # プレイヤー攻撃
                base_damage = game.calculate_physical_damage(self.player["attack"], self.boss["def"], -5, 5)

                # ability効果を適用
                enemy_type = "boss"
                equipment_bonus = await game.calculate_equipment_bonus(self.player["user_id"]) if "user_id" in self.player else {}
                weapon_ability = equipment_bonus.get("weapon_ability", "")

                ability_result = game.apply_ability_effects(base_damage, weapon_ability, self.player["hp"], enemy_type)

                player_dmg = ability_result["damage"]
                self.boss["hp"] -= player_dmg

                # HP吸収
                if ability_result["lifesteal"] > 0:
                    self.player["hp"] = min(self.player.get("max_hp", 50), self.player["hp"] + ability_result["lifesteal"])

                # 召喚回復
                if ability_result.get("summon_heal", 0) > 0:
                    self.player["hp"] = min(self.player.get("max_hp", 50), self.player["hp"] + ability_result["summon_heal"])

                # 自傷ダメージ
                if ability_result.get("self_damage", 0) > 0:
                    self.player["hp"] -= ability_result["self_damage"]
                    self.player["hp"] = max(0, self.player["hp"])

                player_text = f"あなたの攻撃！ {player_dmg} のダメージを与えた！"
                if ability_result["effect_text"]:
                    player_text += f"\n{ability_result['effect_text']}"

                # 即死判定（ボス戦では無効）
                if ability_result["instant_kill"]:
                    player_text += "\n💀即死効果発動！...しかしボスには効かなかった！"

                if self.boss["hp"] <= 0:
                    # HPを保存
                    await db.update_player(interaction.user.id, hp=self.player["hp"])
                    await db.set_boss_defeated(interaction.user.id, self.boss_stage)

                    reward_gold = random.randint(
                        balance_settings.REWARD_GOLD_BOSS_MIN,
                        balance_settings.REWARD_GOLD_BOSS_MAX,
                    )
                    await db.add_gold(interaction.user.id, reward_gold)

                    embed = discord.Embed(
                        title="🎉 ダンジョンクリア！",
                        description=f"**{self.boss['name']}** を倒した！\n\n🏆 ダンジョンを踏破した――\n💰 {reward_gold}ゴールドを手に入れた！",
                        color=discord.Color.gold()
                    )

                    self.disable_all_items()

                    # ラスボスクリア時の選択Viewを表示（攻撃ログは1拍置いてから結果表示）
                    await self._staged_update(first_text=player_text, second_text=None, first_delay=1.0)
                    clear_view = await FinalBossClearView.create(interaction.user.id, self.ctx, self.user_processing, self.boss_stage)
                    await interaction.message.edit(embed=embed, view=clear_view)
                    return

                # 怯み効果で敵がスキップ
                if ability_result.get("enemy_flinch", False):
                    text = player_text + "\nラスボスは怯んで動けない！"
                    # HPを保存
                    await db.update_player(interaction.user.id, hp=self.player["hp"])
                    await self._staged_update(first_text=text, second_text=None, first_delay=1.0)

                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return

                # 凍結効果で敵がスキップ
                if ability_result.get("enemy_freeze", False):
                    text = player_text + "\nラスボスは凍りついて動けない！"
                    # HPを保存
                    await db.update_player(interaction.user.id, hp=self.player["hp"])
                    await self._staged_update(first_text=text, second_text=None, first_delay=1.0)

                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return

                # 麻痺効果で敵がスキップ
                if ability_result.get("paralyze", False):
                    text = player_text + "\nラスボスは麻痺して動けない！"
                    # HPを保存
                    await db.update_player(interaction.user.id, hp=self.player["hp"])
                    await self._staged_update(first_text=text, second_text=None, first_delay=1.0)

                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return

                # ラスボス反撃
                enemy_base_dmg = game.calculate_physical_damage(self.boss["atk"], self.player["defense"], -3, 3)

                # 鎧/盾の効果を適用（盾は防御系アビリティ枠として合算）
                armor_ability = equipment_bonus.get("armor_ability", "")
                shield_ability = equipment_bonus.get("shield_ability", "")
                combined_def_ability = "\n".join([a for a in [armor_ability, shield_ability] if a])
                armor_result = game.apply_armor_effects(
                    enemy_base_dmg, 
                    combined_def_ability, 
                    self.player["hp"], 
                    self.player.get("max_hp", 50),
                    enemy_base_dmg,
                    self.boss.get("attribute", "none")
                )

                if armor_result["evaded"]:
                    text = player_text + f"\nラスボスの攻撃！ {armor_result['effect_text']}"
                else:
                    enemy_dmg = armor_result["damage"]
                    self.player["hp"] -= enemy_dmg
                    self.player["hp"] = max(0, self.player["hp"])
                    text = player_text + f"\nラスボスの反撃！ {enemy_dmg} のダメージを受けた！"
                    if armor_result["effect_text"]:
                        text += f"\n{armor_result['effect_text']}"

                    # 反撃ダメージ
                    if armor_result["counter_damage"] > 0:
                        self.boss["hp"] -= armor_result["counter_damage"]
                        if self.boss["hp"] <= 0:
                            await db.update_player(interaction.user.id, hp=self.player["hp"])
                            text += "\n反撃でラスボスを倒した！"
                            await db.set_boss_defeated(interaction.user.id, self.boss_stage)
                            reward_gold = random.randint(
                                balance_settings.REWARD_GOLD_BOSS_MIN,
                                balance_settings.REWARD_GOLD_BOSS_MAX,
                            )
                            await db.add_gold(interaction.user.id, reward_gold)
                            embed = discord.Embed(
                                title="🎉 ダンジョンクリア！",
                                description=f"反撃で **{self.boss['name']}** を倒した！\n\n🏆 ダンジョンを踏破した――\n💰 {reward_gold}ゴールドを手に入れた！",
                                color=discord.Color.gold()
                            )
                            embed.add_field(
                                name="📦 アイテムを倉庫に保管", 
                                value="インベントリから1つアイテムを選んで倉庫に保管できます。\n次回 `!start` 時に倉庫から取り出せます。", 
                                inline=False
                            )
                            self.disable_all_items()
                            await interaction.message.edit(embed=embed, view=None)
                            await self._staged_update(first_text=text, second_text=None, first_delay=1.0)

                            storage_view = await FinalBossClearView.create(interaction.user.id, self.ctx, self.user_processing, self.boss_stage)
                            storage_embed = discord.Embed(
                                title="📦 倉庫にアイテムを保管",
                                description="インベントリから1つ選んで倉庫に保管してください。\n次回の冒険で取り出すことができます。",
                                color=discord.Color.blue()
                            )
                            await interaction.channel.send(embed=storage_embed, view=storage_view)
                            return

                    # 反射ダメージ
                    if armor_result["reflect_damage"] > 0:
                        self.boss["hp"] -= armor_result["reflect_damage"]
                        if self.boss["hp"] <= 0:
                            await db.update_player(interaction.user.id, hp=self.player["hp"])
                            text += "\n反射ダメージでラスボスを倒した！"
                            await db.set_boss_defeated(interaction.user.id, self.boss_stage)
                            reward_gold = random.randint(
                                balance_settings.REWARD_GOLD_BOSS_MIN,
                                balance_settings.REWARD_GOLD_BOSS_MAX,
                            )
                            await db.add_gold(interaction.user.id, reward_gold)
                            embed = discord.Embed(
                                title="🎉 ダンジョンクリア！",
                                description=f"反射ダメージで **{self.boss['name']}** を倒した！\n\n🏆 ダンジョンを制覇した！\n💰 {reward_gold}ゴールドを手に入れた！",
                                color=discord.Color.gold()
                            )
                            embed.add_field(
                                name="📦 アイテムを倉庫に保管", 
                                value="インベントリから1つアイテムを選んで倉庫に保管できます。\n次回 `!start` 時に倉庫から取り出せます。", 
                                inline=False
                            )
                            self.disable_all_items()
                            await interaction.message.edit(embed=embed, view=None)
                            await self._staged_update(first_text=text, second_text=None, first_delay=1.0)

                            storage_view = await FinalBossClearView.create(interaction.user.id, self.ctx, self.user_processing, self.boss_stage)
                            storage_embed = discord.Embed(
                                title="📦 倉庫にアイテムを保管",
                                description="インベントリから1つ選んで倉庫に保管してください。\n次回の冒険で取り出すことができます。",
                                color=discord.Color.blue()
                            )
                            await interaction.channel.send(embed=storage_embed, view=storage_view)
                            return

                    # HP回復
                    if armor_result["hp_regen"] > 0:
                        self.player["hp"] = min(self.player.get("max_hp", 50), self.player["hp"] + armor_result["hp_regen"])

                if self.player["hp"] <= 0:
                    if armor_result.get("revived", False):
                        self.player["hp"] = 1
                        text += "\n蘇生効果で生き残った！"
                    else:
                        death_result = await handle_death_with_triggers(
                            self.ctx if hasattr(self, 'ctx') else interaction.channel,
                            interaction.user.id, 
                            self.user_processing if hasattr(self, 'user_processing') else {},
                            enemy_name=getattr(self, 'enemy', {}).get('name') or getattr(self, 'boss', {}).get('name') or '不明',
                            enemy_type='boss' if hasattr(self, 'boss') else 'normal'
                        )
                        if death_result:
                            await self.update_embed(
                                text + f"\n\n💀 あなたは倒れた…\n\n⭐ {death_result['points']}アップグレードポイントを獲得！"
                            )
                        else:
                            await self.update_embed(text + "\n💀 あなたは倒れた…")
                        self.disable_all_items()
                        await self.message.edit(view=self)
                        if self.ctx.author.id in self.user_processing:
                            self.user_processing[self.ctx.author.id] = False
                        return

                # HPを保存
                await db.update_player(interaction.user.id, hp=self.player["hp"])
                await self._staged_update(first_text=player_text, second_text=text, first_delay=1.0, second_delay=0.5)

                for child in self.children:
                    child.disabled = False
                await self.message.edit(view=self)
                return
            except Exception as e:
                logger.exception("[FinalBossBattleView] fight error: %s", e)
                for child in self.children:
                    child.disabled = False
                try:
                    await self.message.edit(view=self)
                except Exception:
                    pass
                return

        if armor_result["evaded"]:
            text = player_text + f"\nラスボスの攻撃！ {armor_result['effect_text']}"
        else:
            enemy_dmg = armor_result["damage"]
            self.player["hp"] -= enemy_dmg
            self.player["hp"] = max(0, self.player["hp"])
            text = player_text + f"\nラスボスの反撃！ {enemy_dmg} のダメージを受けた！"
            if armor_result["effect_text"]:
                text += f"\n{armor_result['effect_text']}"

            # 反撃ダメージ
            if armor_result["counter_damage"] > 0:
                self.boss["hp"] -= armor_result["counter_damage"]
                if self.boss["hp"] <= 0:
                    # HPを保存
                    await db.update_player(interaction.user.id, hp=self.player["hp"])
                    text += "\n反撃でラスボスを倒した！"
                    await db.set_boss_defeated(interaction.user.id, self.boss_stage)
                    reward_gold = random.randint(
                        balance_settings.REWARD_GOLD_BOSS_MIN,
                        balance_settings.REWARD_GOLD_BOSS_MAX,
                    )
                    await db.add_gold(interaction.user.id, reward_gold)
                    embed = discord.Embed(
                        title="🎉 ダンジョンクリア！",
                        description=f"反撃で **{self.boss['name']}** を倒した！\n\n🏆 ダンジョンを踏破した――\n💰 {reward_gold}ゴールドを手に入れた！",
                        color=discord.Color.gold()
                    )
                    embed.add_field(
                        name="📦 アイテムを倉庫に保管", 
                        value="インベントリから1つアイテムを選んで倉庫に保管できます。\n次回 `!start` 時に倉庫から取り出せます。", 
                        inline=False
                    )
                    self.disable_all_items()
                    await interaction.message.edit(embed=embed, view=None)
                    # 反撃/反射で勝利した場合も、ログを1回だけ見せてから結果へ
                    await self._staged_update(first_text=text, second_text=None, first_delay=1.0)

                    # アイテム持ち帰りViewを表示
                    storage_view = await FinalBossClearView.create(interaction.user.id, self.ctx, self.user_processing, self.boss_stage)
                    storage_embed = discord.Embed(
                        title="📦 倉庫にアイテムを保管",
                        description="インベントリから1つ選んで倉庫に保管してください。\n次回の冒険で取り出すことができます。",
                        color=discord.Color.blue()
                    )
                    await interaction.channel.send(embed=storage_embed, view=storage_view)
                    return

            # 反射ダメージ
            if armor_result["reflect_damage"] > 0:
                self.boss["hp"] -= armor_result["reflect_damage"]
                if self.boss["hp"] <= 0:
                    # HPを保存
                    await db.update_player(interaction.user.id, hp=self.player["hp"])
                    text += "\n反射ダメージでラスボスを倒した！"
                    await db.set_boss_defeated(interaction.user.id, self.boss_stage)
                    reward_gold = random.randint(
                        balance_settings.REWARD_GOLD_BOSS_MIN,
                        balance_settings.REWARD_GOLD_BOSS_MAX,
                    )
                    await db.add_gold(interaction.user.id, reward_gold)
                    embed = discord.Embed(
                        title="🎉 ダンジョンクリア！",
                        description=f"反射ダメージで **{self.boss['name']}** を倒した！\n\n🏆 ダンジョンを制覇した！\n💰 {reward_gold}ゴールドを手に入れた！",
                        color=discord.Color.gold()
                    )
                    embed.add_field(
                        name="📦 アイテムを倉庫に保管", 
                        value="インベントリから1つアイテムを選んで倉庫に保管できます。\n次回 `!start` 時に倉庫から取り出せます。", 
                        inline=False
                    )
                    self.disable_all_items()
                    await interaction.message.edit(embed=embed, view=None)
                    await self._staged_update(first_text=text, second_text=None, first_delay=1.0)

                    # アイテム持ち帰りViewを表示
                    storage_view = await FinalBossClearView.create(interaction.user.id, self.ctx, self.user_processing, self.boss_stage)
                    storage_embed = discord.Embed(
                        title="📦 倉庫にアイテムを保管",
                        description="インベントリから1つ選んで倉庫に保管してください。\n次回の冒険で取り出すことができます。",
                        color=discord.Color.blue()
                    )
                    await interaction.channel.send(embed=storage_embed, view=storage_view)
                    return

            # HP回復
            if armor_result["hp_regen"] > 0:
                self.player["hp"] = min(self.player.get("max_hp", 50), self.player["hp"] + armor_result["hp_regen"])

            if self.player["hp"] <= 0:
                if armor_result.get("revived", False):
                    self.player["hp"] = 1
                    text += "\n蘇生効果で生き残った！"
                else:
                    # 【重要】先にインタラクションに応答
                    await interaction.response.defer()

                    # 死亡処理 + トリガーチェック
                    death_result = await handle_death_with_triggers(
                        self.ctx,
                        interaction.user.id,
                        self.user_processing,
                        enemy_name=self.boss.get('name', '不明'),
                        enemy_type='boss'
                    )

                    # 死亡通知を送信
                    try:
                        notify_channel = interaction.client.get_channel(NOTIFY_CHANNEL_ID) if NOTIFY_CHANNEL_ID else None
                        if notify_channel and death_result:
                            distance = death_result.get("distance", 0)
                            await notify_channel.send(
                                f"💀 {interaction.user.mention} がラスボス戦で倒れた…\n"
                                f"到達距離: {distance}m"
                            )
                    except Exception as e:
                        logger.warning("通知送信エラー: %s", e, exc_info=True)

                    if death_result:
                        await self.update_embed(
                            text + f"\n\n💀 あなたは倒れた…\n\n⭐ {death_result['points']}アップグレードポイントを獲得！"
                        )
                    else:
                        await self.update_embed(text + "\n💀 あなたは倒れた…")

                    self.disable_all_items()
                    await self.message.edit(view=self)

                    if self.ctx.author.id in self.user_processing:
                        self.user_processing[self.ctx.author.id] = False
                    return

            # 生存している場合
            # HPを保存
            await db.update_player(interaction.user.id, hp=self.player["hp"])
            await self._staged_update(first_text=player_text, second_text=text, first_delay=1.0, second_delay=0.5)

            # ✅ 修正: ボタンを再有効化
            for child in self.children:
                child.disabled = False
            await self.message.edit(view=self)

    @button(label="防御", style=discord.ButtonStyle.secondary, emoji="🛡️")
    async def defend(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("これはあなたの戦闘ではありません！", ephemeral=True)

        if self._battle_lock.locked():
            return await interaction.response.send_message("⚠️ 処理中です。少々お待ちください。", ephemeral=True)

        await interaction.response.defer()

        async with self._battle_lock:
            # ボタンを即座に無効化
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)

        reduction = random.randint(
            balance_settings.DAMAGE_REDUCTION_HIGH_MIN,
            balance_settings.DAMAGE_REDUCTION_HIGH_MAX,
        )
        reduced_raw = int((self.boss["atk"] + random.randint(-3, 3)) * (1 - reduction / 100))
        enemy_dmg = game.mitigate_physical_damage(reduced_raw, self.player["defense"])
        self.player["hp"] -= enemy_dmg
        self.player["hp"] = max(0, self.player["hp"])

        first_text = f"防御した！ ダメージを {reduction}% 軽減！"
        text = f"{first_text}\nラスボスの攻撃で {enemy_dmg} のダメージを受けた！"

        if self.player["hp"] <= 0:
            # 【重要】先にインタラクションに応答
            await interaction.response.defer()

            # 死亡処理 + トリガーチェック
            death_result = await handle_death_with_triggers(
                self.ctx,
                interaction.user.id,
                self.user_processing,
                enemy_name=self.boss.get('name', '不明'),
                enemy_type='boss'
            )

            # 死亡通知を送信
            try:
                notify_channel = interaction.client.get_channel(NOTIFY_CHANNEL_ID) if NOTIFY_CHANNEL_ID else None
                if notify_channel and death_result:
                    distance = death_result.get("distance", 0)
                    await notify_channel.send(
                        f"💀 {interaction.user.mention} がラスボス戦で倒れた…\n"
                        f"到達距離: {distance}m"
                    )
            except Exception as e:
                logger.warning("通知送信エラー: %s", e, exc_info=True)

            if death_result:
                await self.update_embed(
                    text + f"\n\n💀 あなたは倒れた…\n\n⭐ {death_result['points']}アップグレードポイントを獲得！"
                )
            else:
                await self.update_embed(text + "\n💀 あなたは倒れた…")

            self.disable_all_items()
            await self.message.edit(view=self)

            if self.ctx.author.id in self.user_processing:
                self.user_processing[self.ctx.author.id] = False
            return

        # 生存している場合
        await db.update_player(interaction.user.id, hp=self.player["hp"])
        await self._staged_update(first_text=first_text, second_text=text, first_delay=1.0, second_delay=0.5)

        for child in self.children:
            child.disabled = False
        await self.message.edit(view=self)

    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def on_timeout(self):
        await finalize_view_on_timeout(self, user_processing=self.user_processing, user_id=getattr(self.ctx.author, "id", None))

# ==============================
# ボス戦View
# ==============================
class BossBattleView(View):
    def __init__(self, ctx, player, boss, user_processing: dict, boss_stage: int):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.player = player
        self.boss = boss
        self.message = None
        self.user_processing = user_processing
        self.boss_stage = boss_stage
        self._battle_lock = asyncio.Lock()

    @classmethod
    async def create(cls, ctx, player, boss, user_processing: dict, boss_stage: int):
        """Async factory method to create and initialize BossBattleView"""
        instance = cls(ctx, player, boss, user_processing, boss_stage)
        await instance._async_init()
        return instance

    async def _async_init(self):
        """Async initialization logic"""
        fresh_boss = game.get_boss(self.boss_stage)
        if fresh_boss:
            self.boss = fresh_boss
            self._boss_max_hp = int(self.boss.get("hp", 0) or 0)
            if config.VERBOSE_DEBUG:
                logger.debug(
                    "boss init name=%s hp=%s atk=%s def=%s",
                    self.boss.get("name"),
                    self.boss.get("hp"),
                    self.boss.get("atk"),
                    self.boss.get("def"),
                )
        
        if "user_id" in self.player:
            fresh_player = await db.get_player(self.player["user_id"])
            if fresh_player:
                self.player.update({
                    "hp": fresh_player.get("hp", self.player.get("hp", 50)),
                    "max_hp": fresh_player.get("max_hp", self.player.get("max_hp", 50)),
                    "mp": fresh_player.get("mp", self.player.get("mp", 20)),
                    "max_mp": fresh_player.get("max_mp", self.player.get("max_mp", 20)),
                    "attack": fresh_player.get("atk", self.player.get("attack", 5)),
                    "defense": fresh_player.get("def", self.player.get("defense", 2))
                })
            
            equipment_bonus = await game.calculate_equipment_bonus(self.player["user_id"])
            self.player["attack"] = self.player.get("attack", 5) + equipment_bonus["attack_bonus"]
            self.player["defense"] = self.player.get("defense", 2) + equipment_bonus["defense_bonus"]

            unlocked_skills = await db.get_unlocked_skills(self.player["user_id"])
            if unlocked_skills:
                skill_options = []
                for skill_id in unlocked_skills[:SELECT_MAX_OPTIONS]:
                    skill_info = game.get_skill_info(skill_id)
                    if skill_info:
                        skill_options.append(discord.SelectOption(
                            label=skill_info["name"],
                            description=f"MP:{skill_info['mp_cost']} - {skill_info['description'][:50]}",
                            value=skill_id
                        ))

                if skill_options:
                    skill_select = discord.ui.Select(
                        placeholder="スキルを選択",
                        options=skill_options,
                        custom_id="boss_skill_select"
                    )
                    skill_select.callback = self.use_skill
                    self.add_item(skill_select)

    async def send_initial_embed(self):
        embed = await self.create_battle_embed()
        self.message = await self.ctx.send(embed=embed, view=self)

    async def create_battle_embed(self):
        boss_hp = int(self.boss.get("hp", 0) or 0)
        boss_max_hp = int(getattr(self, "_boss_max_hp", 0) or boss_hp or 0)
        boss_atk = int(self.boss.get("atk", 0) or 0)
        boss_def = int(self.boss.get("def", 0) or 0)

        player_hp = int(self.player.get("hp", 0) or 0)
        player_atk = int(self.player.get("attack", 0) or 0)
        player_def = int(self.player.get("defense", 0) or 0)

        mp = None
        max_mp = None
        max_hp = int(self.player.get("max_hp", player_hp) or player_hp or 0)
        if "user_id" in self.player:
            player_data = await db.get_player(self.player["user_id"])
            if player_data:
                mp = int(player_data.get("mp", 20) or 20)
                max_mp = int(player_data.get("max_mp", 20) or 20)
                max_hp = int(player_data.get("max_hp", max_hp) or max_hp)

        is_critical = (player_hp > 0) and (player_hp <= 5)
        is_low = (player_hp > 0) and (not is_critical) and (max_hp > 0) and (player_hp <= max(1, int(max_hp * 0.25)))

        if is_critical:
            color = discord.Color.red()
            warning_line = "💀 **瀕死です！** 回復を強く推奨"
        elif is_low:
            color = discord.Color.orange()
            warning_line = "⚠️ **HPが少ないです。** 回復を推奨"
        else:
            color = discord.Color.dark_red()
            warning_line = ""

        boss_is_critical = (boss_hp > 0) and (boss_max_hp > 0) and (boss_hp <= max(1, int(boss_max_hp * 0.15)))
        boss_is_low = (boss_hp > 0) and (boss_max_hp > 0) and (not boss_is_critical) and (boss_hp <= max(1, int(boss_max_hp * 0.30)))

        boss_name = str(self.boss.get("name", "ボス") or "ボス")
        if boss_is_critical:
            boss_name += "（瀕死）"
            boss_hp_suffix = " 💀"
        elif boss_is_low:
            boss_name += "（弱っている）"
            boss_hp_suffix = " ⚠️"
        else:
            boss_hp_suffix = ""

        enemy_line = (
            f"👑 **{boss_name}**\n"
            f"HP **{boss_hp}/{boss_max_hp}**{boss_hp_suffix} / ATK **{boss_atk}** / DEF **{boss_def}**"
        )

        if mp is not None and max_mp is not None:
            player_line = (
                "🧍 **あなた**\n"
                f"HP **{player_hp}/{max_hp}** / MP **{mp}/{max_mp}** / ATK **{player_atk}** / DEF **{player_def}**"
            )
        else:
            player_line = (
                "🧍 **あなた**\n"
                f"HP **{player_hp}/{max_hp}** / ATK **{player_atk}** / DEF **{player_def}**"
            )

        parts = []
        if warning_line:
            parts.append(warning_line)
        parts.append(enemy_line)
        parts.append(player_line)

        embed = discord.Embed(
            title="🔥 ボス戦！",
            description="\n\n".join(parts),
            color=color,
        )
        embed.set_footer(text="▶ 行動を選択してください")
        return embed

    def _format_battle_log(self, text: str) -> str:
        import re

        if not text:
            return ""

        text = re.sub(
            r"あなたの攻撃！\s*(\d+)\s*のダメージを与えた！",
            r"⚔️ あなたの攻撃！ **\1** ダメージ",
            text,
        )
        text = re.sub(
            r"ボスの反撃！\s*(\d+)\s*のダメージを受けた！",
            r"💥 ボスの反撃！ **\1** ダメージ",
            text,
        )
        text = re.sub(
            r"ボスの攻撃で\s*(\d+)\s*のダメージを受けた！",
            r"💥 ボスの攻撃！ **\1** ダメージ",
            text,
        )

        text = text.replace("\n💥 ", "\n\n💥 ")
        return text

    async def _staged_update(self, first_text: str, second_text: str | None = None, first_delay: float = 1.0, second_delay: float = 0.5):
        if first_delay and first_delay > 0:
            await asyncio.sleep(first_delay)
        await self.update_embed(first_text)
        if second_text is not None:
            if second_delay and second_delay > 0:
                await asyncio.sleep(second_delay)
            await self.update_embed(second_text)

    async def update_embed(self, text=""):
        embed = await self.create_battle_embed()
        if text:
            log_text = self._format_battle_log(text)
            embed.description += f"\n\n— 戦闘ログ —\n{log_text}"
        await self.message.edit(embed=embed, view=self)

    # =====================================
    # ✨ スキル使用
    # =====================================
    async def use_skill(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("これはあなたの戦闘ではありません！", ephemeral=True)

        # アトミックなロックチェック（ロック取得できなければ処理中）
        if self._battle_lock.locked():
            return await interaction.response.send_message("⚠️ 処理中です。少々お待ちください。", ephemeral=True)
        
        async with self._battle_lock:
            try:
                # ボタンを即座に無効化
                for child in self.children:
                    child.disabled = True
                await self.message.edit(view=self)

                # ✅ プレイヤーデータを最新化
                fresh_player_data = await db.get_player(interaction.user.id)
                if fresh_player_data:
                    self.player["hp"] = fresh_player_data.get("hp", self.player["hp"])
                    self.player["mp"] = fresh_player_data.get("mp", self.player.get("mp", 20))
                    self.player["max_hp"] = fresh_player_data.get("max_hp", self.player.get("max_hp", 50))
                    self.player["max_mp"] = fresh_player_data.get("max_mp", self.player.get("max_mp", 20))
                    
                    # ✅ 装備ボーナスを再計算してattackとdefenseを更新
                    base_atk = fresh_player_data.get("atk", 5)
                    base_def = fresh_player_data.get("def", 2)
                    equipment_bonus = await game.calculate_equipment_bonus(interaction.user.id)
                    self.player["attack"] = base_atk + equipment_bonus["attack_bonus"]
                    self.player["defense"] = base_def + equipment_bonus["defense_bonus"]
                    if config.VERBOSE_DEBUG:
                        logger.debug(
                            "use_skill player refreshed: hp=%s mp=%s atk=%s+%s=%s",
                            self.player["hp"],
                            self.player["mp"],
                            base_atk,
                            equipment_bonus["attack_bonus"],
                            self.player["attack"],
                        )

                if await db.is_mp_stunned(interaction.user.id):
                    await db.set_mp_stunned(interaction.user.id, False)
                    await interaction.response.send_message("⚠️ MP枯渇で行動不能！\n『嘘だろ!?』\n次のターンから行動可能になります。", ephemeral=True)
                    # ボタンを再有効化
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return

                skill_id = interaction.data['values'][0]
                skill_info = game.get_skill_info(skill_id)

                if not skill_info:
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return await interaction.response.send_message("⚠️ スキル情報が見つかりません。", ephemeral=True)

                player_data = await db.get_player(interaction.user.id)
                current_mp = player_data.get("mp", 20)
                mp_cost = skill_info["mp_cost"]

                if current_mp < mp_cost:
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return await interaction.response.send_message(f"⚠️ MPが足りません！（必要: {mp_cost}, 現在: {current_mp}）", ephemeral=True)

                if not await db.consume_mp(interaction.user.id, mp_cost):
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return await interaction.response.send_message("⚠️ MP消費に失敗しました。", ephemeral=True)

                player_data = await db.get_player(interaction.user.id)
                if player_data and player_data.get("mp", 0) == 0:
                    await db.set_mp_stunned(interaction.user.id, True)

                text = f"✨ **{skill_info['name']}** を使用！（MP -{mp_cost}）\n"

                if skill_info["type"] == "attack":
                    base_damage = game.calculate_physical_damage(self.player["attack"], self.boss["def"], -3, 3)
                    skill_damage = int(base_damage * skill_info["power"])
                    self.boss["hp"] -= skill_damage
                    text += f"⚔️ {skill_damage} のダメージを与えた！"

                    if self.boss["hp"] <= 0:
                        await db.update_player(interaction.user.id, hp=self.player["hp"])
                        distance = self.player.get("distance", 0)
                        drop_result = game.get_enemy_drop(self.boss["name"], distance)

                        drop_text = ""
                        if drop_result:
                            if drop_result["type"] == "coins":
                                await db.add_gold(interaction.user.id, drop_result["amount"])
                                drop_text = f"\n💰 **{drop_result['amount']}コイン** を手に入れた！"
                            elif drop_result["type"] == "item":
                                await db.add_item_to_inventory(interaction.user.id, drop_result["name"])
                                drop_text = f"\n🎁 **{drop_result['name']}** を手に入れた！"

                        await self.update_embed(text + "\n🏆 敵を倒した！" + drop_text)
                        self.disable_all_items()
                        await self.message.edit(view=self)
                        if self.ctx.author.id in self.user_processing:
                            self.user_processing[self.ctx.author.id] = False
                        await interaction.response.defer()
                        return

                    enemy_dmg = game.calculate_physical_damage(self.boss["atk"], self.player["defense"], -2, 2)
                    self.player["hp"] -= enemy_dmg
                    self.player["hp"] = max(0, self.player["hp"])
                    text += f"\n敵の反撃！ {enemy_dmg} のダメージを受けた！"

                    if self.player["hp"] <= 0:
                        death_result = await handle_death_with_triggers(
                            self.ctx if hasattr(self, 'ctx') else interaction.channel,
                            interaction.user.id, 
                            self.user_processing if hasattr(self, 'user_processing') else {},
                            enemy_name=getattr(self, 'enemy', {}).get('name') or getattr(self, 'boss', {}).get('name') or '不明',
                            enemy_type='boss' if hasattr(self, 'boss') else 'normal'
                        )
                        if death_result:
                            await self.update_embed(text + f"\n💀 あなたは倒れた…\n\n🔄 リスタート\n📍 アップグレードポイント: +{death_result['points']}pt")
                        else:
                            await self.update_embed(text + "\n💀 あなたは倒れた…")
                        self.disable_all_items()
                        await self.message.edit(view=self)
                        if self.ctx.author.id in self.user_processing:
                            self.user_processing[self.ctx.author.id] = False
                        await interaction.response.defer()
                        return

                elif skill_info["type"] == "heal":
                    heal_amount = skill_info["heal_amount"]
                    max_hp = self.player.get("max_hp", 50)
                    old_hp = self.player["hp"]
                    self.player["hp"] = min(max_hp, self.player["hp"] + heal_amount)
                    actual_heal = self.player["hp"] - old_hp
                    text += f"💚 HP+{actual_heal} 回復した！"

                await db.update_player(interaction.user.id, hp=self.player["hp"])
                await self.update_embed(text)
                # ボタンを再有効化
                for child in self.children:
                    child.disabled = False
                await self.message.edit(view=self)
                await interaction.response.defer()
            
            except Exception as e:
                logger.exception("[BattleView] use_skill error: %s", e)
                # エラー時もボタンを再有効化
                for child in self.children:
                    child.disabled = False
                try:
                    await self.message.edit(view=self)
                    if not interaction.response.is_done():
                        await interaction.response.send_message("⚠️ エラーが発生しました。もう一度お試しください。", ephemeral=True)
                except:
                    pass

    @button(label="戦う", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def fight(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("これはあなたの戦闘ではありません！", ephemeral=True)

        if self._battle_lock.locked():
            return await interaction.response.send_message("⚠️ 処理中です。少々お待ちください。", ephemeral=True)

        await interaction.response.defer()

        async with self._battle_lock:
            try:
                for child in self.children:
                    child.disabled = True
                await self.message.edit(view=self)

                if await db.is_mp_stunned(interaction.user.id):
                    await db.set_mp_stunned(interaction.user.id, False)
                    text = "⚠️ MP枯渇で行動不能…\n『嘘だろ!?』\n次のターンから行動可能になります。"
                    await self.update_embed(text)
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return

                # プレイヤー攻撃
                base_damage = game.calculate_physical_damage(self.player["attack"], self.boss["def"], -5, 5)

                # ability効果を適用
                enemy_type = "boss"
                equipment_bonus = await game.calculate_equipment_bonus(self.player["user_id"]) if "user_id" in self.player else {}
                weapon_ability = equipment_bonus.get("weapon_ability", "")
                ability_result = game.apply_ability_effects(base_damage, weapon_ability, self.player["hp"], enemy_type)

                player_dmg = ability_result["damage"]
                self.boss["hp"] -= player_dmg

                if ability_result["lifesteal"] > 0:
                    self.player["hp"] = min(self.player.get("max_hp", 50), self.player["hp"] + ability_result["lifesteal"])

                if ability_result.get("summon_heal", 0) > 0:
                    self.player["hp"] = min(self.player.get("max_hp", 50), self.player["hp"] + ability_result["summon_heal"])

                if ability_result.get("self_damage", 0) > 0:
                    self.player["hp"] -= ability_result["self_damage"]
                    self.player["hp"] = max(0, self.player["hp"])

                player_text = f"あなたの攻撃！ {player_dmg} のダメージを与えた！"
                if ability_result["effect_text"]:
                    player_text += f"\n{ability_result['effect_text']}"

                if ability_result["instant_kill"]:
                    player_text += "\n💀即死効果発動！...しかしボスには効かなかった！"

                # 勝利
                if self.boss["hp"] <= 0:
                    await db.update_player(interaction.user.id, hp=self.player["hp"])
                    await db.set_boss_defeated(interaction.user.id, self.boss_stage)

                    reward_gold = random.randint(
                        balance_settings.REWARD_GOLD_NORMAL_MIN,
                        balance_settings.REWARD_GOLD_NORMAL_MAX,
                    )
                    await db.add_gold(interaction.user.id, reward_gold)

                    try:
                        notify_channel = interaction.client.get_channel(NOTIFY_CHANNEL_ID) if NOTIFY_CHANNEL_ID else None
                        if notify_channel:
                            await notify_channel.send(
                                f"⚔️ {interaction.user.mention} がステージ{self.boss_stage}のボス「{self.boss['name']}」を撃破した！"
                            )
                    except Exception as e:
                        logger.warning("通知送信エラー: %s", e, exc_info=True)

                    text = player_text + f"\n\n🏆 ボスを倒した！\n💰 {reward_gold}ゴールドを手に入れた！"
                    await self._staged_update(first_text=player_text, second_text=text, first_delay=1.0, second_delay=0.5)
                    self.disable_all_items()
                    await self.message.edit(view=self)

                    story_id = f"boss_post_{self.boss_stage}"
                    if not await db.get_story_flag(interaction.user.id, story_id):
                        await asyncio.sleep(2)
                        from story import StoryView
                        view = StoryView(interaction.user.id, story_id, self.user_processing)
                        await view.send_story(self.ctx)
                        return

                    if self.ctx.author.id in self.user_processing:
                        self.user_processing[self.ctx.author.id] = False
                    return

                # 敵がスキップ
                if ability_result.get("enemy_flinch", False):
                    text = player_text + "\n敵は怯んで動けない！"
                    await db.update_player(interaction.user.id, hp=self.player["hp"])
                    await self._staged_update(first_text=text, second_text=None, first_delay=1.0)

                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return

                if ability_result.get("enemy_freeze", False):
                    text = player_text + "\n敵は凍りついて動けない！"
                    await db.update_player(interaction.user.id, hp=self.player["hp"])
                    await self._staged_update(first_text=text, second_text=None, first_delay=1.0)

                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return

                if ability_result.get("paralyze", False):
                    text = player_text + "\n敵は麻痺して動けない！"
                    await db.update_player(interaction.user.id, hp=self.player["hp"])
                    await self._staged_update(first_text=text, second_text=None, first_delay=1.0)

                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return

                # ボス反撃
                enemy_base_dmg = game.calculate_physical_damage(self.boss["atk"], self.player["defense"], -3, 3)

                armor_ability = equipment_bonus.get("armor_ability", "")
                shield_ability = equipment_bonus.get("shield_ability", "")
                combined_def_ability = "\n".join([a for a in [armor_ability, shield_ability] if a])
                armor_result = game.apply_armor_effects(
                    enemy_base_dmg,
                    combined_def_ability,
                    self.player["hp"],
                    self.player.get("max_hp", 50),
                    enemy_base_dmg,
                    self.boss.get("attribute", "none"),
                )

                if armor_result["evaded"]:
                    text = player_text + f"\nボスの攻撃！ {armor_result['effect_text']}"
                else:
                    enemy_dmg = armor_result["damage"]
                    self.player["hp"] -= enemy_dmg
                    self.player["hp"] = max(0, self.player["hp"])
                    text = player_text + f"\nボスの反撃！ {enemy_dmg} のダメージを受けた！"
                    if armor_result["effect_text"]:
                        text += f"\n{armor_result['effect_text']}"

                    # 反撃ダメージ
                    if armor_result["counter_damage"] > 0:
                        self.boss["hp"] -= armor_result["counter_damage"]
                        if self.boss["hp"] <= 0:
                            await db.update_player(interaction.user.id, hp=self.player["hp"])
                            text += "\n反撃でボスを倒した！"
                            await db.set_boss_defeated(interaction.user.id, self.boss_stage)
                            reward_gold = random.randint(
                                balance_settings.REWARD_GOLD_NORMAL_MIN,
                                balance_settings.REWARD_GOLD_NORMAL_MAX,
                            )
                            await db.add_gold(interaction.user.id, reward_gold)
                            await self.update_embed(text + f"\n💰 {reward_gold}ゴールドを手に入れた！")
                            self.disable_all_items()
                            await self.message.edit(view=self)

                            story_id = f"boss_post_{self.boss_stage}"
                            if not await db.get_story_flag(interaction.user.id, story_id):
                                await asyncio.sleep(2)
                                from story import StoryView
                                view = StoryView(interaction.user.id, story_id, self.user_processing)
                                await view.send_story(self.ctx)
                                return

                            if self.ctx.author.id in self.user_processing:
                                self.user_processing[self.ctx.author.id] = False
                            return

                    # 反射ダメージ
                    if armor_result["reflect_damage"] > 0:
                        self.boss["hp"] -= armor_result["reflect_damage"]
                        if self.boss["hp"] <= 0:
                            await db.update_player(interaction.user.id, hp=self.player["hp"])
                            text += "\n反射ダメージでボスを倒した！"
                            await db.set_boss_defeated(interaction.user.id, self.boss_stage)
                            reward_gold = random.randint(
                                balance_settings.REWARD_GOLD_NORMAL_MIN,
                                balance_settings.REWARD_GOLD_NORMAL_MAX,
                            )
                            await db.add_gold(interaction.user.id, reward_gold)
                            await self.update_embed(text + f"\n💰 {reward_gold}ゴールドを手に入れた！")
                            self.disable_all_items()
                            await self.message.edit(view=self)

                            story_id = f"boss_post_{self.boss_stage}"
                            if not await db.get_story_flag(interaction.user.id, story_id):
                                await asyncio.sleep(2)
                                from story import StoryView
                                view = StoryView(interaction.user.id, story_id, self.user_processing)
                                await view.send_story(self.ctx)
                                return

                            if self.ctx.author.id in self.user_processing:
                                self.user_processing[self.ctx.author.id] = False
                            return

                    if armor_result["hp_regen"] > 0:
                        self.player["hp"] = min(self.player.get("max_hp", 50), self.player["hp"] + armor_result["hp_regen"])

                # 死亡
                if self.player["hp"] <= 0:
                    if armor_result.get("revived", False):
                        self.player["hp"] = 1
                        text += "\n蘇生効果で生き残った！"
                    else:
                        death_result = await handle_death_with_triggers(
                            self.ctx if hasattr(self, 'ctx') else interaction.channel,
                            interaction.user.id,
                            self.user_processing if hasattr(self, 'user_processing') else {},
                            enemy_name=getattr(self, 'enemy', {}).get('name') or getattr(self, 'boss', {}).get('name') or '不明',
                            enemy_type='boss' if hasattr(self, 'boss') else 'normal'
                        )

                        try:
                            notify_channel = interaction.client.get_channel(NOTIFY_CHANNEL_ID) if NOTIFY_CHANNEL_ID else None
                            if notify_channel:
                                player = await db.get_player(interaction.user.id)
                                distance = player.get("distance", 0) if player else 0
                                await notify_channel.send(
                                    f"💀 {interaction.user.mention} がボス戦で倒れた…\n"
                                    f"到達距離: {distance}m"
                                )
                        except Exception as e:
                            logger.warning("通知送信エラー: %s", e, exc_info=True)

                        if death_result:
                            await self.update_embed(
                                text + f"\n\n💀 あなたは倒れた…\n\n⭐ {death_result['points']}アップグレードポイントを獲得！\n（死亡回数: {death_result['death_count']}回）"
                            )
                        else:
                            await self.update_embed(text + "\n💀 あなたは倒れた…")

                        self.disable_all_items()
                        await self.message.edit(view=self)

                        if self.ctx.author.id in self.user_processing:
                            self.user_processing[self.ctx.author.id] = False
                        return

                # 継続
                await db.update_player(interaction.user.id, hp=self.player["hp"])
                await self._staged_update(first_text=player_text, second_text=text, first_delay=1.0, second_delay=0.5)

                for child in self.children:
                    child.disabled = False
                await self.message.edit(view=self)
                return

            except Exception as e:
                logger.exception("[BossBattleView] fight error: %s", e)
                for child in self.children:
                    child.disabled = False
                try:
                    await self.message.edit(view=self)
                except Exception:
                    pass
                return

    @button(label="防御", style=discord.ButtonStyle.secondary, emoji="🛡️")
    async def defend(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("これはあなたの戦闘ではありません！", ephemeral=True)

        if self._battle_lock.locked():
            return await interaction.response.send_message("⚠️ 処理中です。少々お待ちください。", ephemeral=True)

        await interaction.response.defer()

        async with self._battle_lock:
            try:
                for child in self.children:
                    child.disabled = True
                await self.message.edit(view=self)

                reduction = random.randint(
                    balance_settings.DAMAGE_REDUCTION_MID_MIN,
                    balance_settings.DAMAGE_REDUCTION_MID_MAX,
                )
                reduced_raw = int((self.boss["atk"] + random.randint(-3, 3)) * (1 - reduction / 100))
                enemy_dmg = game.mitigate_physical_damage(reduced_raw, self.player["defense"])
                self.player["hp"] -= enemy_dmg
                self.player["hp"] = max(0, self.player["hp"])

                first_text = f"防御した！ ダメージを {reduction}% 軽減！"
                text = f"{first_text}\nボスの攻撃で {enemy_dmg} のダメージを受けた！"

                if self.player["hp"] <= 0:
                    death_result = await handle_death_with_triggers(
                        self.ctx if hasattr(self, 'ctx') else interaction.channel,
                        interaction.user.id,
                        self.user_processing if hasattr(self, 'user_processing') else {},
                        enemy_name=getattr(self, 'enemy', {}).get('name') or getattr(self, 'boss', {}).get('name') or '不明',
                        enemy_type='boss' if hasattr(self, 'boss') else 'normal'
                    )
                    if death_result:
                        await self.update_embed(
                            text + f"\n\n💀 あなたは倒れた…\n\n⭐ {death_result['points']}アップグレードポイントを獲得！"
                        )
                    else:
                        await self.update_embed(text + "\n💀 あなたは倒れた…")

                    self.disable_all_items()
                    await self.message.edit(view=self)
                    if self.ctx.author.id in self.user_processing:
                        self.user_processing[self.ctx.author.id] = False
                    return

                await db.update_player(interaction.user.id, hp=self.player["hp"])
                await self._staged_update(first_text=first_text, second_text=text, first_delay=1.0, second_delay=0.5)

                for child in self.children:
                    child.disabled = False
                await self.message.edit(view=self)
                return

            except Exception as e:
                logger.exception("[BossBattleView] defend error: %s", e)
                for child in self.children:
                    child.disabled = False
                try:
                    await self.message.edit(view=self)
                except Exception:
                    pass
                return

    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def on_timeout(self):
        await finalize_view_on_timeout(self, user_processing=self.user_processing, user_id=getattr(self.ctx.author, "id", None))

#戦闘Embed
import discord
from discord.ui import View, button, Select
import random

class BattleView(View):
    def __init__(self, ctx, player, enemy, user_processing: dict, post_battle_hook=None, enemy_max_hp: int | None = None, allow_flee: bool = True):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.player = player  # { "hp": int, "attack": int, "defense": int, "inventory": [ ... ] }
        self.enemy = enemy    # { "name": str, "hp": int, "atk": int, "def": int }
        self.message = None
        self.user_processing = user_processing
        self._battle_lock = asyncio.Lock()  # アトミックなロック機構
        self._post_battle_hook = post_battle_hook
        self._enemy_max_hp = int(enemy_max_hp) if enemy_max_hp is not None else int(enemy.get("hp", 0) or 0)
        self._allow_flee = bool(allow_flee)

        if not self._allow_flee:
            for child in list(self.children):
                if isinstance(child, discord.ui.Button) and (
                    getattr(child.callback, "__name__", "") == "run" or str(getattr(child, "label", "")) == "逃げる"
                ):
                    self.remove_item(child)

    @classmethod
    async def create(cls, ctx, player, enemy, user_processing: dict, post_battle_hook=None, enemy_max_hp: int | None = None, allow_flee: bool = True):
        """Async factory method to create and initialize BattleView"""
        instance = cls(ctx, player, enemy, user_processing, post_battle_hook=post_battle_hook, enemy_max_hp=enemy_max_hp, allow_flee=allow_flee)
        await instance._async_init()
        return instance

    async def _maybe_finish_story_battle(self, outcome: str) -> bool:
        """ストーリー駆動の戦闘なら、勝敗に応じてフックを呼ぶ。"""
        if not self._post_battle_hook:
            return False

        try:
            await self._post_battle_hook(
                outcome=outcome,
                enemy_hp=int(self.enemy.get("hp", 0) or 0),
                enemy_max_hp=int(self._enemy_max_hp or 0),
            )
        except Exception as e:
            try:
                await self.ctx.send(f"⚠️ 戦闘後処理に失敗しました: {e}")
            except Exception:
                pass
        return True

    async def _async_init(self):
        """Async initialization logic"""
        if "user_id" in self.player:
            equipment_bonus = await game.calculate_equipment_bonus(self.player["user_id"])
            self.player["attack"] = self.player.get("attack", 10) + equipment_bonus["attack_bonus"]
            self.player["defense"] = self.player.get("defense", 5) + equipment_bonus["defense_bonus"]

            unlocked_skills = await db.get_unlocked_skills(self.player["user_id"])
            if unlocked_skills:
                skill_options = []
                for skill_id in unlocked_skills[:SELECT_MAX_OPTIONS]:
                    skill_info = game.get_skill_info(skill_id)
                    if skill_info:
                        skill_options.append(discord.SelectOption(
                            label=skill_info["name"],
                            description=f"MP:{skill_info['mp_cost']} - {skill_info['description'][:50]}",
                            value=skill_id
                        ))

                if skill_options:
                    skill_select = discord.ui.Select(
                        placeholder="スキルを選択",
                        options=skill_options,
                        custom_id="skill_select"
                    )
                    skill_select.callback = self.use_skill
                    self.add_item(skill_select)

    async def send_initial_embed(self):
        embed = await self.create_battle_embed()
        self.message = await self.ctx.send(embed=embed, view=self)

    async def create_battle_embed(self):
        enemy_hp = int(self.enemy.get("hp", 0) or 0)
        enemy_max_hp = int(self._enemy_max_hp or enemy_hp or 0)
        enemy_atk = int(self.enemy.get("atk", 0) or 0)
        enemy_def = int(self.enemy.get("def", 0) or 0)

        player_hp = int(self.player.get("hp", 0) or 0)
        player_atk = int(self.player.get("attack", 0) or 0)
        player_def = int(self.player.get("defense", 0) or 0)

        mp = None
        max_mp = None
        max_hp = int(self.player.get("max_hp", player_hp) or player_hp or 0)
        if "user_id" in self.player:
            player_data = await db.get_player(self.player["user_id"])
            if player_data:
                mp = int(player_data.get("mp", 20) or 20)
                max_mp = int(player_data.get("max_mp", 20) or 20)
                max_hp = int(player_data.get("max_hp", max_hp) or max_hp)

        is_critical = (player_hp > 0) and (player_hp <= 5)
        is_low = (player_hp > 0) and (not is_critical) and (max_hp > 0) and (player_hp <= max(1, int(max_hp * 0.25)))

        if is_critical:
            color = discord.Color.red()
            warning_line = "💀 **瀕死です！** 回復を強く推奨"
        elif is_low:
            color = discord.Color.orange()
            warning_line = "⚠️ **HPが少ないです。** 回復を推奨"
        else:
            color = discord.Color.dark_grey()
            warning_line = ""

        enemy_is_critical = (enemy_hp > 0) and (enemy_max_hp > 0) and (enemy_hp <= max(1, int(enemy_max_hp * 0.15)))
        enemy_is_low = (enemy_hp > 0) and (enemy_max_hp > 0) and (not enemy_is_critical) and (enemy_hp <= max(1, int(enemy_max_hp * 0.30)))

        enemy_name = str(self.enemy.get("name", "敵") or "敵")
        if enemy_is_critical:
            enemy_name += "（瀕死）"
            enemy_hp_suffix = " 💀"
        elif enemy_is_low:
            enemy_name += "（弱っている）"
            enemy_hp_suffix = " ⚠️"
        else:
            enemy_hp_suffix = ""

        enemy_line = (
            f"🧟 **{enemy_name}**\n"
            f"HP **{enemy_hp}/{enemy_max_hp}**{enemy_hp_suffix} / ATK **{enemy_atk}** / DEF **{enemy_def}**"
        )

        if mp is not None and max_mp is not None:
            player_line = (
                "🧍 **あなた**\n"
                f"HP **{player_hp}/{max_hp}** / MP **{mp}/{max_mp}** / ATK **{player_atk}** / DEF **{player_def}**"
            )
        else:
            player_line = (
                "🧍 **あなた**\n"
                f"HP **{player_hp}/{max_hp}** / ATK **{player_atk}** / DEF **{player_def}**"
            )

        parts = []
        if warning_line:
            parts.append(warning_line)
        parts.append(enemy_line)
        parts.append(player_line)

        embed = discord.Embed(
            title="⚔️ 戦闘開始！",
            description="\n\n".join(parts),
            color=color,
        )
        embed.set_footer(text="▶ 行動を選択してください")

        # 低HP時は「アイテム使用」を目立たせる
        try:
            for child in self.children:
                if isinstance(child, discord.ui.Button) and str(getattr(child, "label", "")) == "アイテム使用":
                    child.style = discord.ButtonStyle.danger if (is_low or is_critical) else discord.ButtonStyle.primary
        except Exception:
            pass

        return embed

    def _format_battle_log(self, text: str) -> str:
        import re

        if not text:
            return ""

        # よく出るログだけ、数字を太字＋絵文字で強調
        text = re.sub(
            r"あなたの攻撃！\s*(\d+)\s*のダメージを与えた！",
            r"⚔️ あなたの攻撃！ **\1** ダメージ",
            text,
        )
        text = re.sub(
            r"敵の反撃！\s*(\d+)\s*のダメージを受けた！",
            r"💥 敵の反撃！ **\1** ダメージ",
            text,
        )
        text = re.sub(
            r"ボスの反撃！\s*(\d+)\s*のダメージを受けた！",
            r"💥 ボスの反撃！ **\1** ダメージ",
            text,
        )
        text = re.sub(
            r"ラスボスの反撃！\s*(\d+)\s*のダメージを受けた！",
            r"💥 ラスボスの反撃！ **\1** ダメージ",
            text,
        )
        text = re.sub(
            r"⚔️\s*(\d+)\s*のダメージを与えた！",
            r"⚔️ **\1** ダメージ",
            text,
        )

        # 攻撃→反撃の2行は、間に1行余白を入れて視線の休憩を作る
        text = text.replace("\n💥 ", "\n\n💥 ")

        return text
    async def _staged_update(self, first_text: str, second_text: str | None = None, first_delay: float = 1.0, second_delay: float = 0.5):
        if first_delay and first_delay > 0:
            await asyncio.sleep(first_delay)
        await self.update_embed(first_text)
        if second_text is not None:
            if second_delay and second_delay > 0:
                await asyncio.sleep(second_delay)
            await self.update_embed(second_text)

    async def update_embed(self, text=""):
        embed = await self.create_battle_embed()
        if text:
            log_text = self._format_battle_log(text)
            # 余白＋見出しで「直近ログ感」を上げる
            embed.description += f"\n\n— 戦闘ログ —\n{log_text}"
        await self.message.edit(embed=embed, view=self)

    # =====================================
    # ✨ スキル使用
    # =====================================
    async def use_skill(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("これはあなたの戦闘ではありません！", ephemeral=True)

        # アトミックなロックチェック（ロック取得できなければ処理中）
        if self._battle_lock.locked():
            return await interaction.response.send_message("⚠️ 処理中です。少々お待ちください。", ephemeral=True)
        
        async with self._battle_lock:
            try:
                # ボタンを即座に無効化
                for child in self.children:
                    child.disabled = True
                await self.message.edit(view=self)

                # ✅ プレイヤーデータを最新化
                fresh_player_data = await db.get_player(interaction.user.id)
                if fresh_player_data:
                    self.player["hp"] = fresh_player_data.get("hp", self.player["hp"])
                    self.player["mp"] = fresh_player_data.get("mp", self.player.get("mp", 20))
                    self.player["max_hp"] = fresh_player_data.get("max_hp", self.player.get("max_hp", 50))
                    self.player["max_mp"] = fresh_player_data.get("max_mp", self.player.get("max_mp", 20))
                    
                    # ✅ 装備ボーナスを再計算してattackとdefenseを更新
                    base_atk = fresh_player_data.get("atk", 5)
                    base_def = fresh_player_data.get("def", 2)
                    equipment_bonus = await game.calculate_equipment_bonus(interaction.user.id)
                    self.player["attack"] = base_atk + equipment_bonus["attack_bonus"]
                    self.player["defense"] = base_def + equipment_bonus["defense_bonus"]
                    if config.VERBOSE_DEBUG:
                        logger.debug(
                            "use_skill player refreshed: hp=%s mp=%s atk=%s+%s=%s",
                            self.player["hp"],
                            self.player["mp"],
                            base_atk,
                            equipment_bonus["attack_bonus"],
                            self.player["attack"],
                        )

                if await db.is_mp_stunned(interaction.user.id):
                    await db.set_mp_stunned(interaction.user.id, False)
                    await interaction.response.send_message("⚠️ MP枯渇で行動不能！\n『嘘だろ!?』\n次のターンから行動可能になります。", ephemeral=True)
                    # ボタンを再有効化
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return

                skill_id = interaction.data['values'][0]
                skill_info = game.get_skill_info(skill_id)

                if not skill_info:
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return await interaction.response.send_message("⚠️ スキル情報が見つかりません。", ephemeral=True)

                player_data = await db.get_player(interaction.user.id)
                current_mp = player_data.get("mp", 20)
                mp_cost = skill_info["mp_cost"]

                if current_mp < mp_cost:
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return await interaction.response.send_message(f"⚠️ MPが足りません！（必要: {mp_cost}, 現在: {current_mp}）", ephemeral=True)

                if not await db.consume_mp(interaction.user.id, mp_cost):
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return await interaction.response.send_message("⚠️ MP消費に失敗しました。", ephemeral=True)

                player_data = await db.get_player(interaction.user.id)
                if player_data and player_data.get("mp", 0) == 0:
                    await db.set_mp_stunned(interaction.user.id, True)

                text = f"✨ **{skill_info['name']}** を使用！（MP -{mp_cost}）\n"

                if skill_info["type"] == "attack":
                    base_damage = game.calculate_physical_damage(self.player["attack"], self.enemy["def"], -3, 3)
                    skill_damage = int(base_damage * skill_info["power"])
                    self.enemy["hp"] -= skill_damage
                    text += f"⚔️ {skill_damage} のダメージを与えた！"

                    if self.enemy["hp"] <= 0:
                        if await self._maybe_finish_story_battle("win"):
                            self.disable_all_items()
                            await self.message.edit(view=self)
                            if self.ctx.author.id in self.user_processing:
                                self.user_processing[self.ctx.author.id] = False
                            await interaction.response.defer()
                            return

                        await db.update_player(interaction.user.id, hp=self.player["hp"])
                        distance = self.player.get("distance", 0)
                        drop_result = game.get_enemy_drop(self.enemy["name"], distance)

                        drop_text = ""
                        if drop_result:
                            if drop_result["type"] == "coins":
                                await db.add_gold(interaction.user.id, drop_result["amount"])
                                drop_text = f"\n💰 **{drop_result['amount']}コイン** を手に入れた！"
                            elif drop_result["type"] == "item":
                                await db.add_item_to_inventory(interaction.user.id, drop_result["name"])
                                drop_text = f"\n🎁 **{drop_result['name']}** を手に入れた！"

                        await self.update_embed(text + "\n🏆 敵を倒した！" + drop_text)
                        self.disable_all_items()
                        await self.message.edit(view=self)
                        if self.ctx.author.id in self.user_processing:
                            self.user_processing[self.ctx.author.id] = False
                        await interaction.response.defer()
                        return

                    enemy_dmg = game.calculate_physical_damage(self.enemy["atk"], self.player["defense"], -2, 2)
                    self.player["hp"] -= enemy_dmg
                    self.player["hp"] = max(0, self.player["hp"])
                    text += f"\n敵の反撃！ {enemy_dmg} のダメージを受けた！"

                    if self.player["hp"] <= 0:
                        if await self._maybe_finish_story_battle("lose"):
                            # ストーリー駆動戦闘でも、致死ターンのHP/ログを反映してから終了する
                            try:
                                await db.update_player(interaction.user.id, hp=self.player["hp"])
                            except Exception:
                                pass
                            try:
                                await self.update_embed(text)
                            except Exception:
                                pass
                            self.disable_all_items()
                            await self.message.edit(view=self)
                            if self.ctx.author.id in self.user_processing:
                                self.user_processing[self.ctx.author.id] = False
                            await interaction.response.defer()
                            return

                        death_result = await handle_death_with_triggers(
                            self.ctx if hasattr(self, 'ctx') else interaction.channel,
                            interaction.user.id, 
                            self.user_processing if hasattr(self, 'user_processing') else {},
                            enemy_name=getattr(self, 'enemy', {}).get('name') or getattr(self, 'boss', {}).get('name') or '不明',
                            enemy_type='boss' if hasattr(self, 'boss') else 'normal'
                        )
                        if death_result:
                            await self.update_embed(text + f"\n💀 あなたは倒れた…\n\n🔄 リスタート\n📍 アップグレードポイント: +{death_result['points']}pt")
                        else:
                            await self.update_embed(text + "\n💀 あなたは倒れた…")
                        self.disable_all_items()
                        await self.message.edit(view=self)
                        if self.ctx.author.id in self.user_processing:
                            self.user_processing[self.ctx.author.id] = False
                        await interaction.response.defer()
                        return

                elif skill_info["type"] == "heal":
                    heal_amount = skill_info["heal_amount"]
                    max_hp = self.player.get("max_hp", 50)
                    old_hp = self.player["hp"]
                    self.player["hp"] = min(max_hp, self.player["hp"] + heal_amount)
                    actual_heal = self.player["hp"] - old_hp
                    text += f"💚 HP+{actual_heal} 回復した！"

                await db.update_player(interaction.user.id, hp=self.player["hp"])
                await self.update_embed(text)
                # ボタンを再有効化
                for child in self.children:
                    child.disabled = False
                await self.message.edit(view=self)
                await interaction.response.defer()
            
            except Exception as e:
                logger.exception("[BattleView] use_skill error: %s", e)
                # エラー時もボタンを再有効化
                for child in self.children:
                    child.disabled = False
                try:
                    await self.message.edit(view=self)
                    if not interaction.response.is_done():
                        await interaction.response.send_message("⚠️ エラーが発生しました。もう一度お試しください。", ephemeral=True)
                except:
                    pass

    # =====================================
    # 🗡️ 戦う
    # =====================================
    @button(label="戦う", style=discord.ButtonStyle.danger, emoji="🗡️")
    async def fight(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 権限チェック
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("これはあなたの戦闘ではありません！", ephemeral=True)

        # アトミックなロックチェック（ロック取得できなければ処理中）
        if self._battle_lock.locked():
            return await interaction.response.send_message("⚠️ 処理中です。少々お待ちください。", ephemeral=True)
        
        # 先にdeferしてタイムアウトを回避
        await interaction.response.defer()
        
        async with self._battle_lock:
            try:
                # ボタンを即座に無効化
                for child in self.children:
                    child.disabled = True
                await self.message.edit(view=self)

                # ✅ プレイヤーデータを最新化
                fresh_player_data = await db.get_player(interaction.user.id)
                if fresh_player_data:
                    self.player["hp"] = fresh_player_data.get("hp", self.player["hp"])
                    self.player["max_hp"] = fresh_player_data.get("max_hp", self.player.get("max_hp", 50))
                    
                    # ✅ 装備ボーナスを再計算してattackとdefenseを更新
                    base_atk = fresh_player_data.get("atk", 5)
                    base_def = fresh_player_data.get("def", 2)
                    equipment_bonus = await game.calculate_equipment_bonus(interaction.user.id)
                    self.player["attack"] = base_atk + equipment_bonus["attack_bonus"]
                    self.player["defense"] = base_def + equipment_bonus["defense_bonus"]
                    if config.VERBOSE_DEBUG:
                        logger.debug(
                            "fight player refreshed: hp=%s atk=%s+%s=%s def=%s+%s=%s",
                            self.player["hp"],
                            base_atk,
                            equipment_bonus["attack_bonus"],
                            self.player["attack"],
                            base_def,
                            equipment_bonus["defense_bonus"],
                            self.player["defense"],
                        )

                # MP枯渇チェック
                if await db.is_mp_stunned(interaction.user.id):
                    await db.set_mp_stunned(interaction.user.id, False)
                    text = "⚠️ MP枯渇で行動不能…\n『嘘だろ!?』\n次のターンから行動可能になります。"
                    await self.update_embed(text)
                    # ボタンを再有効化
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)
                    return

                # プレイヤー攻撃
                base_damage = game.calculate_physical_damage(self.player["attack"], self.enemy["def"], -3, 3)

                # ability効果を適用
                enemy_type = game.get_enemy_type(self.enemy["name"])
                equipment_bonus = await game.calculate_equipment_bonus(self.player["user_id"]) if "user_id" in self.player else {}
                weapon_ability = equipment_bonus.get("weapon_ability", "")

                ability_result = game.apply_ability_effects(base_damage, weapon_ability, self.player["hp"], enemy_type)
                
                player_dmg = ability_result["damage"]
                self.enemy["hp"] -= player_dmg

                # HP吸収
                if ability_result["lifesteal"] > 0:
                    self.player["hp"] = min(self.player.get("max_hp", 50), self.player["hp"] + ability_result["lifesteal"])

                # 召喚回復
                if ability_result.get("summon_heal", 0) > 0:
                    self.player["hp"] = min(self.player.get("max_hp", 50), self.player["hp"] + ability_result["summon_heal"])

                # 自傷ダメージ
                if ability_result.get("self_damage", 0) > 0:
                    self.player["hp"] -= ability_result["self_damage"]
                    self.player["hp"] = max(0, self.player["hp"])

                player_text = f"あなたの攻撃！ {player_dmg} のダメージを与えた！"
                if ability_result["effect_text"]:
                    player_text += f"\n{ability_result['effect_text']}"

                # 即死判定
                if ability_result["instant_kill"]:
                    self.enemy["hp"] = 0

                # 勝利チェック
                if self.enemy["hp"] <= 0:
                    if await self._maybe_finish_story_battle("win"):
                        self.disable_all_items()
                        await self.message.edit(view=self)
                        if self.ctx.author.id in self.user_processing:
                            self.user_processing[self.ctx.author.id] = False
                        return

                    # HPを保存
                    await db.update_player(interaction.user.id, hp=self.player["hp"])

                    # ドロップアイテムを取得
                    distance = self.player.get("distance", 0)
                    drop_result = game.get_enemy_drop(self.enemy["name"], distance)

                    drop_text = ""
                    if drop_result:
                        if drop_result["type"] == "coins":
                            await db.add_gold(interaction.user.id, drop_result["amount"])
                            drop_text = f"\n💰 **{drop_result['amount']}コイン** を手に入れた！"
                        elif drop_result["name"] == "none":
                            drop_text = f"\n **敵は何も落とさなかった...**"
                        elif drop_result["type"] == "item":
                            await db.add_item_to_inventory(interaction.user.id, drop_result["name"])
                            drop_text = f"\n🎁 **{drop_result['name']}** を手に入れた！"

                    await self._staged_update(
                        first_text=player_text,
                        second_text=player_text + "\n🏆 敵を倒した！" + drop_text,
                        first_delay=1.0,
                        second_delay=0.5,
                    )
                    self.disable_all_items()
                    await self.message.edit(view=self)
                    if self.ctx.author.id in self.user_processing:
                        self.user_processing[self.ctx.author.id] = False
                        # ロックはasync withで自動解放される
                    return

                # 怯み効果で敵がスキップ
                if ability_result.get("enemy_flinch", False):
                    combined = player_text + "\n敵は怯んで動けない！"
                    # HPを保存
                    await db.update_player(interaction.user.id, hp=self.player["hp"])
                    await self._staged_update(first_text=player_text, second_text=combined, first_delay=1.0, second_delay=0.5)

                    # ✅ ボタンを再有効化
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)

                    # ロックはasync withで自動解放される
                    return

                # 凍結効果で敵がスキップ
                if ability_result.get("enemy_freeze", False):
                    combined = player_text + "\n敵は凍りついて動けない！"
                    # HPを保存
                    await db.update_player(interaction.user.id, hp=self.player["hp"])
                    await self._staged_update(first_text=player_text, second_text=combined, first_delay=1.0, second_delay=0.5)

                    # ✅ ボタンを再有効化
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)

                    # ロックはasync withで自動解放される
                    return

                # 麻痺効果で敵がスキップ
                if ability_result.get("paralyze", False):
                    combined = player_text + "\n敵は麻痺して動けない！"
                    # HPを保存
                    await db.update_player(interaction.user.id, hp=self.player["hp"])
                    await self._staged_update(first_text=player_text, second_text=combined, first_delay=1.0, second_delay=0.5)

                    # ✅ ボタンを再有効化
                    for child in self.children:
                        child.disabled = False
                    await self.message.edit(view=self)

                    # ロックはasync withで自動解放される
                    return

                # 敵反撃
                text = player_text
                enemy_base_dmg = game.calculate_physical_damage(self.enemy["atk"], self.player["defense"], -2, 2)

                # 鎧/盾の効果を適用（盾は防御系アビリティ枠として合算）
                armor_ability = equipment_bonus.get("armor_ability", "")
                shield_ability = equipment_bonus.get("shield_ability", "")
                combined_def_ability = "\n".join([a for a in [armor_ability, shield_ability] if a])
                armor_result = game.apply_armor_effects(
                    enemy_base_dmg, 
                    combined_def_ability, 
                    self.player["hp"], 
                    self.player.get("max_hp", 50),
                    enemy_base_dmg,
                    self.enemy.get("attribute", "none")
                )

                if armor_result["evaded"]:
                    text += f"\n敵の攻撃！ {armor_result['effect_text']}"
                else:
                    enemy_dmg = armor_result["damage"]
                    self.player["hp"] -= enemy_dmg
                    self.player["hp"] = max(0, self.player["hp"])
                    text += f"\n敵の反撃！ {enemy_dmg} のダメージを受けた！"
                    if armor_result["effect_text"]:
                        text += f"\n{armor_result['effect_text']}"

                    # 反撃ダメージ
                    if armor_result["counter_damage"] > 0:
                        self.enemy["hp"] -= armor_result["counter_damage"]
                        if self.enemy["hp"] <= 0:
                            # HPを保存
                            await db.update_player(interaction.user.id, hp=self.player["hp"])
                            text += "\n反撃で敵を倒した！"
                            await self.update_embed(text)
                            self.disable_all_items()
                            await self.message.edit(view=self)
                            if self.ctx.author.id in self.user_processing:
                                self.user_processing[self.ctx.author.id] = False
                            # ロックはasync with‌で自動解放される
                            return

                    # 反射ダメージ
                    if armor_result["reflect_damage"] > 0:
                        self.enemy["hp"] -= armor_result["reflect_damage"]
                        if self.enemy["hp"] <= 0:
                            # HPを保存
                            await db.update_player(interaction.user.id, hp=self.player["hp"])
                            text += "\n反射ダメージで敵を倒した！"
                            await self.update_embed(text)
                            self.disable_all_items()
                            await self.message.edit(view=self)
                            if self.ctx.author.id in self.user_processing:
                                self.user_processing[self.ctx.author.id] = False
                            # ロックはasync withで自動解放される
                            return

                    # HP回復
                    if armor_result["hp_regen"] > 0:
                        self.player["hp"] = min(self.player.get("max_hp", 50), self.player["hp"] + armor_result["hp_regen"])

                # 敗北チェック
                if self.player["hp"] <= 0:
                    if armor_result.get("revived", False):
                        self.player["hp"] = 1
                        text += "\n蘇生効果で生き残った！\n『死んだかと思った……どんなシステムなんだろう』"
                    else:
                        if await self._maybe_finish_story_battle("lose"):
                            # ストーリー駆動戦闘でも、致死ターンのHP/ログを反映してから終了する
                            try:
                                await db.update_player(interaction.user.id, hp=self.player["hp"])
                            except Exception:
                                pass
                            try:
                                await self._staged_update(
                                    first_text=player_text,
                                    second_text=text,
                                    first_delay=1.0,
                                    second_delay=0.5,
                                )
                            except Exception:
                                pass
                            self.disable_all_items()
                            await self.message.edit(view=self)
                            if self.ctx.author.id in self.user_processing:
                                self.user_processing[self.ctx.author.id] = False
                            return

                        # 死亡処理（HPリセット、距離リセット、アップグレードポイント付与）
                        death_result = await handle_death_with_triggers(
                            self.ctx if hasattr(self, 'ctx') else interaction.channel,
                            interaction.user.id, 
                            self.user_processing if hasattr(self, 'user_processing') else {},
                            enemy_name=getattr(self, 'enemy', {}).get('name') or getattr(self, 'boss', {}).get('name') or '不明',
                            enemy_type='boss' if hasattr(self, 'boss') else 'normal'
                        )
                        if death_result:
                            await self._staged_update(
                                first_text=player_text,
                                second_text=text + f"\n💀 あなたは倒れた…\n\n🔄 リスタート\n📍 アップグレードポイント: +{death_result['points']}pt",
                                first_delay=1.0,
                                second_delay=0.5,
                            )
                        else:
                            await self._staged_update(
                                first_text=player_text,
                                second_text=text + "\n💀 あなたは倒れた…",
                                first_delay=1.0,
                                second_delay=0.5,
                            )
                        self.disable_all_items()
                        await self.message.edit(view=self)
                        if self.ctx.author.id in self.user_processing:
                            self.user_processing[self.ctx.author.id] = False
                        # ロックはasync withで自動解放される
                        return

                # HPを保存（戦闘継続時）
                await db.update_player(interaction.user.id, hp=self.player["hp"])
                await self._staged_update(
                    first_text=player_text,
                    second_text=text,
                    first_delay=1.0,
                    second_delay=0.5,
                )
                # ボタンを再有効化
                for child in self.children:
                    child.disabled = False
                await self.message.edit(view=self)
            
            except Exception as e:
                logger.exception("[BattleView] fight error: %s", e)
                # エラー時もボタンを再有効化
                for child in self.children:
                    child.disabled = False
                try:
                    await self.message.edit(view=self)
                except:
                    pass

    # =====================================
    # 🛡️ 防御
    # =====================================
    @button(label="防御", style=discord.ButtonStyle.secondary, emoji="🛡️")
    async def defend(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("これはあなたの戦闘ではありません！", ephemeral=True)

        # アトミックなロックチェック
        if self._battle_lock.locked():
            return await interaction.response.send_message("⚠️ 処理中です。少々お待ちください。", ephemeral=True)
        
        # 先にdeferしてタイムアウトを回避
        await interaction.response.defer()
        
        async with self._battle_lock:
            try:
                # ボタンを即座に無効化
                for child in self.children:
                    child.disabled = True
                await self.message.edit(view=self)

                # ✅ プレイヤーデータを最新化
                fresh_player_data = await db.get_player(interaction.user.id)
                if fresh_player_data:
                    self.player["hp"] = fresh_player_data.get("hp", self.player["hp"])
                    
                    # ✅ 装備ボーナスを再計算してdefenseを更新
                    base_def = fresh_player_data.get("def", 2)
                    equipment_bonus = await game.calculate_equipment_bonus(interaction.user.id)
                    self.player["defense"] = base_def + equipment_bonus["defense_bonus"]
                    if config.VERBOSE_DEBUG:
                        logger.debug(
                            "defend player refreshed: hp=%s def=%s+%s=%s",
                            self.player["hp"],
                            base_def,
                            equipment_bonus["defense_bonus"],
                            self.player["defense"],
                        )

                reduction = random.randint(
                    balance_settings.DAMAGE_REDUCTION_LOW_MIN,
                    balance_settings.DAMAGE_REDUCTION_LOW_MAX,
                )
                reduced_raw = int((self.enemy["atk"] + random.randint(-2, 2)) * (1 - reduction / 100))
                enemy_dmg = game.mitigate_physical_damage(reduced_raw, self.player["defense"])
                self.player["hp"] -= enemy_dmg
                self.player["hp"] = max(0, self.player["hp"])

                first_text = f"防御した！ ダメージを {reduction}% 軽減！"
                text = f"{first_text}\n敵の攻撃で {enemy_dmg} のダメージを受けた！"

                if self.player["hp"] <= 0:
                    if await self._maybe_finish_story_battle("lose"):
                        # ストーリー駆動戦闘でも、致死ターンのHP/ログを反映してから終了する
                        try:
                            await db.update_player(interaction.user.id, hp=self.player["hp"])
                        except Exception:
                            pass
                        try:
                            await self.update_embed(text)
                        except Exception:
                            pass
                        self.disable_all_items()
                        await self.message.edit(view=self)
                        if self.ctx.author.id in self.user_processing:
                            self.user_processing[self.ctx.author.id] = False
                        return

                    # 死亡処理
                    death_result = await handle_death_with_triggers(
                        self.ctx if hasattr(self, 'ctx') else interaction.channel,
                        interaction.user.id, 
                        self.user_processing if hasattr(self, 'user_processing') else {},
                        enemy_name=getattr(self, 'enemy', {}).get('name') or getattr(self, 'boss', {}).get('name') or '不明',
                        enemy_type='boss' if hasattr(self, 'boss') else 'normal'
                    )
                    if death_result:
                        await self.update_embed(text + f"\n💀 あなたは倒れた…\n\n🔄 リスタート\n📍 アップグレードポイント: +{death_result['points']}pt")
                    else:
                        await self.update_embed(text + "\n💀 あなたは倒れた…")
                    self.disable_all_items()
                    await self.message.edit(view=self)
                    if self.ctx.author.id in self.user_processing:
                        self.user_processing[self.ctx.author.id] = False
                    return

                # HPを保存
                await db.update_player(interaction.user.id, hp=self.player["hp"])
                await self._staged_update(first_text=first_text, second_text=text, first_delay=1.0, second_delay=0.5)
                # ボタンを再有効化
                for child in self.children:
                    child.disabled = False
                await self.message.edit(view=self)
            
            except Exception as e:
                logger.exception("[BattleView] defend error: %s", e)
                # エラー時もボタンを再有効化
                for child in self.children:
                    child.disabled = False
                try:
                    await self.message.edit(view=self)
                except:
                    pass

    # =====================================
    # 🏃‍♂️ 逃げる
    # =====================================
    @button(label="逃げる", style=discord.ButtonStyle.success, emoji="🏃‍♂️")
    async def run(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("これはあなたの戦闘ではありません！", ephemeral=True)

        # アトミックなロックチェック
        if self._battle_lock.locked():
            return await interaction.response.send_message("⚠️ 処理中です。少々お待ちください。", ephemeral=True)
        
        # 先にdeferしてタイムアウトを回避
        await interaction.response.defer()
        
        async with self._battle_lock:
            try:
                # ボタンを即座に無効化
                for child in self.children:
                    child.disabled = True
                await self.message.edit(view=self)

                # ✅ プレイヤーデータを最新化
                fresh_player_data = await db.get_player(interaction.user.id)
                if fresh_player_data:
                    self.player["hp"] = fresh_player_data.get("hp", self.player["hp"])
                    
                    # ✅ 装備ボーナスを再計算してdefenseを更新
                    base_def = fresh_player_data.get("def", 2)
                    equipment_bonus = await game.calculate_equipment_bonus(interaction.user.id)
                    self.player["defense"] = base_def + equipment_bonus["defense_bonus"]
                    logger.debug(
                        "battle.run: refresh hp=%s def=%s+%s=%s",
                        self.player["hp"],
                        base_def,
                        equipment_bonus["defense_bonus"],
                        self.player["defense"],
                    )

                first_text = "🏃‍♂️ 逃走を試みた…"

                # 逃走確率
                if random.randint(1, 100) <= balance_settings.FLEE_CHANCE_PERCENT:
                    # 逃走成功 - HPを保存
                    await db.update_player(interaction.user.id, hp=self.player["hp"])
                    text = "🏃‍♂️ うまく逃げ切れた！\n『戦っとけば良かったかな――。』"
                    self.disable_all_items()
                    await self._staged_update(first_text=first_text, second_text=text, first_delay=1.0, second_delay=0.5)
                    await self.message.edit(view=self)
                    if self.ctx.author.id in self.user_processing:
                        self.user_processing[self.ctx.author.id] = False
                else:
                    # 逃走失敗時の反撃も、戦闘モデル（legacy/lol/poe）に統一
                    enemy_dmg = game.calculate_physical_damage(self.enemy["atk"], self.player["defense"], -2, 2)
                    self.player["hp"] -= enemy_dmg
                    self.player["hp"] = max(0, self.player["hp"])
                    
                    # ★修正: 死亡判定を先に行い、条件分岐で適切なEmbed表示
                    if self.player["hp"] <= 0:
                        # 死亡処理
                        death_result = await handle_death_with_triggers(
                            self.ctx if hasattr(self, 'ctx') else interaction.channel,
                            interaction.user.id, 
                            self.user_processing if hasattr(self, 'user_processing') else {},
                            enemy_name=getattr(self, 'enemy', {}).get('name') or getattr(self, 'boss', {}).get('name') or '不明',
                            enemy_type='boss' if hasattr(self, 'boss') else 'normal'
                        )
                        if death_result:
                            text = f"逃げられなかった！ 敵の攻撃で {enemy_dmg} のダメージ！\n💀 あなたは倒れた…\n\n🔄 リスタート\n📍 アップグレードポイント: +{death_result['points']}pt"
                        else:
                            text = f"逃げられなかった！ 敵の攻撃で {enemy_dmg} のダメージ！\n💀 あなたは倒れた…"
                        self.disable_all_items()
                        await self._staged_update(first_text=first_text, second_text=text, first_delay=1.0, second_delay=0.5)
                        await self.message.edit(view=self)
                        if self.ctx.author.id in self.user_processing:
                            self.user_processing[self.ctx.author.id] = False
                    else:
                        # HPを保存（生存時）
                        await db.update_player(interaction.user.id, hp=self.player["hp"])
                        text = f"逃げられなかった！ 敵の攻撃で {enemy_dmg} のダメージ！"
                        await self._staged_update(first_text=first_text, second_text=text, first_delay=1.0, second_delay=0.5)
                        # ボタンを再有効化
                        for child in self.children:
                            child.disabled = False
                        await self.message.edit(view=self)
            
            except Exception as e:
                logger.exception("battle.run error: %s", e)
                # エラー時もボタンを再有効化
                for child in self.children:
                    child.disabled = False
                try:
                    await self.message.edit(view=self)
                except:
                    pass

    # =====================================
    # 💊 アイテム使用
    # =====================================
    @button(label="アイテム使用", style=discord.ButtonStyle.primary, emoji="💊")
    async def use_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("これはあなたの戦闘ではありません！", ephemeral=True)

        # ✅ 最新のプレイヤーデータを取得
        self.player = await db.get_player(self.ctx.author.id)
        if not self.player:
            return await interaction.response.send_message("プレイヤーデータが見つかりません", ephemeral=True)

        items = self.player.get("inventory", [])
        if not items:
            return await interaction.response.send_message("使えるアイテムがありません！", ephemeral=True)

        # HP回復薬とMP回復薬を分類
        hp_potions = []
        mp_potions = []
        
        for item in items:
            item_info = game.get_item_info(item)
            if item_info and item_info.get('type') == 'potion':
                effect = item_info.get('effect', '')
                if 'MP+' in effect or 'MP全回復' in effect:
                    mp_potions.append((item, item_info))
                else:
                    hp_potions.append((item, item_info))

        if not hp_potions and not mp_potions:
            return await interaction.response.send_message("戦闘で使えるアイテムがありません！", ephemeral=True)

        # （以下は元のコードと同じ）

        # Viewを作成
        item_view = discord.ui.View(timeout=VIEW_TIMEOUT_SHORT)
        
        # HP回復薬のプルダウン（最大15個）
        if hp_potions:
            hp_options = []
            for idx, (item, info) in enumerate(hp_potions[:SELECT_MAX_POTION_OPTIONS]):
                effect = info.get('effect', 'HP回復')
                hp_options.append(discord.SelectOption(
                    label=item,
                    description=effect,
                    value=f"hp_{idx}_{item}",
                    emoji="💚"
                ))
            
            hp_select = discord.ui.Select(
                placeholder="💚 HP回復薬",
                options=hp_options,
                custom_id="hp_potion_select"
            )
            hp_select.callback = self.make_item_callback(hp_potions)
            item_view.add_item(hp_select)
        
        # MP回復薬のプルダウン（最大15個）
        if mp_potions:
            mp_options = []
            for idx, (item, info) in enumerate(mp_potions[:SELECT_MAX_POTION_OPTIONS]):
                effect = info.get('effect', 'MP回復')
                mp_options.append(discord.SelectOption(
                    label=item,
                    description=effect,
                    value=f"mp_{idx}_{item}",
                    emoji="💙"
                ))
            
            mp_select = discord.ui.Select(
                placeholder="💙 MP回復薬",
                options=mp_options,
                custom_id="mp_potion_select"
            )
            mp_select.callback = self.make_item_callback(mp_potions)
            item_view.add_item(mp_select)

        await interaction.response.send_message("アイテムを選択してください:", view=item_view, ephemeral=True)
    
    def make_item_callback(self, potion_list):
        """アイテム選択のコールバック関数を生成"""

        async def item_select_callback(select_interaction: discord.Interaction):
            if select_interaction.user.id != self.ctx.author.id:
                return await select_interaction.response.send_message("これはあなたの戦闘ではありません！", ephemeral=True)

            # ✅ プレイヤーデータを再取得（アイテム所持確認のため）
            fresh_player_data = await db.get_player(select_interaction.user.id)
            if not fresh_player_data:
                return await select_interaction.response.send_message("プレイヤーデータが見つかりません。", ephemeral=True)
            
            self.player["hp"] = fresh_player_data.get("hp", self.player["hp"])
            self.player["mp"] = fresh_player_data.get("mp", self.player.get("mp", 20))
            self.player["max_hp"] = fresh_player_data.get("max_hp", self.player.get("max_hp", 50))
            self.player["max_mp"] = fresh_player_data.get("max_mp", self.player.get("max_mp", 20))
            self.player["inventory"] = fresh_player_data.get("inventory", [])
            if config.VERBOSE_DEBUG:
                logger.debug(
                    "item_select_callback player refreshed: hp=%s inventory_count=%s",
                    self.player["hp"],
                    len(self.player["inventory"]),
                )

            selected_value = select_interaction.data['values'][0]
            parts = selected_value.split("_", 2)  # 例: "hp_0_小さい回復薬"
            potion_type = parts[0]
            idx = int(parts[1])
            item_name = parts[2]

            # ✅ アイテム所持確認
            if item_name not in self.player["inventory"]:
                if config.VERBOSE_DEBUG:
                    logger.debug("item_select_callback missing item: %s", item_name)
                return await select_interaction.response.send_message(f"⚠️ {item_name} を所持していません。", ephemeral=True)

            item_info = game.get_item_info(item_name)
            if not item_info:
                return await select_interaction.response.send_message("アイテム情報が見つかりません。", ephemeral=True)

            text = ""
            
            # MP回復薬の処理
            if potion_type == "mp":
                current_mp = self.player.get('mp', 20)
                max_mp = self.player.get('max_mp', 20)
                effect = item_info.get('effect', '')
                
                if 'MP+15' in effect:
                    mp_heal = 15
                elif 'MP+40' in effect:
                    mp_heal = 40
                elif 'MP+100' in effect:
                    mp_heal = 100
                else:
                    mp_heal = 30
                
                new_mp = min(max_mp, current_mp + mp_heal)
                actual_mp_heal = new_mp - current_mp
                self.player['mp'] = new_mp
                
                await db.remove_item_from_inventory(self.ctx.author.id, item_name)
                await db.update_player(self.ctx.author.id, mp=new_mp)
                
                text = f"✨ **{item_name}** を使用した！\nMP +{actual_mp_heal} 回復！"
            
            # HP回復薬の処理
            else:
                current_hp = self.player.get('hp', 50)
                max_hp = self.player.get('max_hp', 50)
                effect = item_info.get('effect', '')

                if 'HP+30' in effect:
                    heal = 30
                elif 'HP+80' in effect:
                    heal = 80
                elif 'HP200' in effect:
                    heal = 200
                else:
                    heal = 30

                new_hp = min(max_hp, current_hp + heal)
                actual_heal = new_hp - current_hp
                self.player['hp'] = new_hp

                await db.remove_item_from_inventory(self.ctx.author.id, item_name)
                await db.update_player(self.ctx.author.id, hp=new_hp)

                text = f"✨ **{item_name}** を使用した！\nHP +{actual_heal} 回復！"
                
            # 敵の反撃
            enemy_dmg = game.calculate_physical_damage(self.enemy["atk"], self.player["defense"], -3, 3)
            self.player["hp"] -= enemy_dmg
            self.player["hp"] = max(0, self.player["hp"])
            text += f"\n敵の攻撃！ {enemy_dmg} のダメージを受けた！"

            if self.player["hp"] <= 0:
                death_result = await handle_death_with_triggers(
                    self.ctx, 
                    self.ctx.author.id, 
                    self.user_processing if hasattr(self, 'user_processing') else {},
                    enemy_name=getattr(self, 'enemy', {}).get('name') or getattr(self, 'boss', {}).get('name') or '不明',
                    enemy_type='boss' if hasattr(self, 'boss') else 'normal'
                )
                if death_result:
                    text += f"\n\n💀 あなたは倒れた…\n\n⭐ {death_result['points']}アップグレードポイントを獲得！\n（死亡回数: {death_result['death_count']}回）"
                else:
                    text += "\n💀 あなたは倒れた…"
                self.disable_all_items()
                await self.update_embed(text)
                await self.message.edit(view=self)
                if self.ctx.author.id in self.user_processing:
                    self.user_processing[self.ctx.author.id] = False
                await select_interaction.response.defer()
                return

            # HPを保存（生存時）
            await db.update_player(self.ctx.author.id, hp=self.player["hp"])
            await self.update_embed(text)
            await select_interaction.response.defer()
        
        return item_select_callback

    # =====================================
    # 終了時無効化
    # =====================================
    def disable_all_items(self):
        for item in self.children:
            item.disabled = True

    async def on_timeout(self):
        await finalize_view_on_timeout(self, user_processing=self.user_processing, user_id=getattr(self.ctx.author, "id", None))


#ステータスEmbed
