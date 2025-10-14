import discord
from discord.ext import commands
import random
import asyncio
import os
from dotenv import load_dotenv
from aiohttp import web
import db
from db import get_player
import views
from views import (
    NameRequestView, 
    ResetConfirmView, 
    TreasureView, 
    BattleView,
    FinalBossBattleView,
    BossBattleView,
    SpecialEventView,
    TrapChestView
)
import game
from story import StoryView

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

user_processing = {}

from functools import wraps
def check_ban():
    """BAN確認デコレーター"""
    def decorator(func):
        @wraps(func)
        async def wrapper(ctx: commands.Context, *args, **kwargs):
            user_id = str(ctx.author.id)
            
            # BAN確認
            if db.is_player_banned(user_id):
                embed = discord.Embed(
                    title="❌ BOT利用禁止",
                    description="あなたはBOT利用禁止処分を受けています。\n\n運営チームにお問い合わせください。",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            
            return await func(ctx, *args, **kwargs)
        return wrapper
    return decorator

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


#スタート×チュートリアル開始
@bot.command(name="start")
@check_ban()
async def start(ctx: commands.Context):
    user = ctx.author
    user_id = str(user.id)
    
    # 処理中チェック
    if user_processing.get(user.id):
        await ctx.send("⚠️ 別の処理が実行中です。完了するまでお待ちください。", delete_after=5)
        return
    
    user_processing[user.id] = True
    try:
        # DBからプレイヤー取得
        player = get_player(user_id)
        if player and player.get("name"):
            await ctx.send("⚠️ あなたはすでにゲームを開始しています！", delete_after=10)
            return

        # プレイヤーデータが存在しない場合は作成
        if not player:
            db.create_player(user.id)

        # カテゴリ検索 or 作成
        guild = ctx.guild
        category = discord.utils.get(guild.categories, name="RPG")
        if not category:
            category = await guild.create_category("RPG")

        # 個人チャンネル検索 or 作成
        channel_name = f"{user.name}-冒険"
        existing_channel = discord.utils.get(category.channels, name=channel_name.lower())
        if existing_channel:
            await ctx.send(f"⚠️ すでにチャンネルが存在します: {existing_channel.mention}", delete_after=10)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

        await ctx.send(f"✅ 冒険チャンネルを作成しました！ {channel.mention}", delete_after=10)

        # チャンネルにウェルカムメッセージ
        await channel.send(
            f"{user.mention} さん！ようこそ 🎉\nここはあなた専用の冒険チャンネルです。"
        )

        # 名前入力モーダルを表示
        embed = discord.Embed(
            title="📝 名前を入力しよう！",
            description="これからの冒険で使うキャラクター名を決めてね！",
            color=discord.Color.blue()
        )
        view = NameRequestView(user.id, channel)
        await channel.send(embed=embed, view=view)
        
        # 通知チャンネルへメッセージ送信
        try:
            notify_channel = bot.get_channel(1424712515396305007)
            if notify_channel:
                await notify_channel.send(
                    f"🎮 {user.mention} が新しい冒険を開始しました！"
                )
        except Exception as e:
            print(f"通知送信エラー: {e}")
    finally:
        user_processing[user.id] = False



@bot.command(name="reset")
@check_ban()
async def reset(ctx: commands.Context):
    """2段階確認付きでプレイヤーデータと専用チャンネルを削除する"""
    user = ctx.author
    user_id = str(user.id)
    
    # 処理中チェック
    if user_processing.get(user.id):
        await ctx.send("⚠️ 別の処理が実行中です。完了するまでお待ちください。", delete_after=5)
        return
    
    player = get_player(user_id)

    if not player:
        await ctx.send(embed=discord.Embed(title="未登録", description="あなたはまだゲームを開始していません。`!start` を使ってゲームを開始してください。", color=discord.Color.orange()))
        return

    embed = discord.Embed(
        title="データを削除しますか？",
        description="リセットするとプレイヤーデータは完全に削除されます。よろしいですか？\n\n※確認は2段階です。",
        color=discord.Color.red()
    )
    view = ResetConfirmView(user.id, None)
    await ctx.send(embed=embed, view=view)


#move
@bot.command(name="move")
@check_ban()
async def move(ctx: commands.Context):
    user = ctx.author
    
    # 処理中チェック
    if user_processing.get(user.id):
        await ctx.send("⚠️ 別の処理が実行中です。完了するまでお待ちください。", delete_after=5)
        return
    
    user_processing[user.id] = True
    view_delegated = False
    
    try:
        # プレイヤーデータチェック
        player = get_player(user.id)
        if not player:
            await ctx.send("!start で冒険を始めてみてね。")
            return
        
        # クリア状態チェック
        if db.is_game_cleared(user.id):
            embed = discord.Embed(
                title="🏆 ダンジョン制覇済み！",
                description="ダンジョンをクリアしました！\n\n次の冒険を始めるには `!reset` でデータをリセットしてください。\n\n使用可能なコマンド:\n• `!reset` - データをリセット\n• `!inventory` - インベントリ確認\n• `!status` - ステータス確認",
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)
            return
        
        # intro_2: 1回目の死亡後、最初のmove時に表示
        loop_count = db.get_loop_count(user.id)
        intro_2_flag = db.get_story_flag(user.id, "intro_2")
        
        # デバッグログ（本番環境では削除可能）
        print(f"[DEBUG] intro_2チェック - User: {user.id}, loop_count: {loop_count}, intro_2_flag: {intro_2_flag}")
        
        if loop_count == 1 and not intro_2_flag:
            print(f"[DEBUG] intro_2を表示します - User: {user.id}")
            embed = discord.Embed(
                title="📖 既視感",
                description="不思議な声が聞こえる…\n誰なんだ？この声の正体は……",
                color=discord.Color.purple()
            )
            await ctx.send(embed=embed)
            await asyncio.sleep(2)
            
            view = StoryView(user.id, "intro_2", user_processing)
            await view.send_story(ctx)
            view_delegated = True
            return
        
        # 移動距離（5〜15m）
        distance = random.randint(5, 15)
        previous_distance = db.get_previous_distance(user.id)
        total_distance = db.add_player_distance(user.id, distance)
        
        current_floor = total_distance // 100 + 1
        current_stage = total_distance // 1000 + 1

        # 移動演出
        exploring_msg = await ctx.send(
            f"🚶‍♂️ ダンジョンを進んでいる…\n周囲は暗く静かだ……\n\n現在：第{current_floor}階層 / ステージ{current_stage}"
        )

        await asyncio.sleep(2.5)

        # ==========================
        # イベント分岐（通過判定方式）
        # ==========================
        
        # 通過したイベント距離を判定する関数
        def passed_through(event_distance):
            """前回の距離から今回の距離の間にevent_distanceを通過したか"""
            return previous_distance < event_distance <= total_distance
        
        # 優先度1: ボス戦（1000m毎）- 最優先
        boss_distances = [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]
        for boss_distance in boss_distances:
            if passed_through(boss_distance):
                boss_stage = boss_distance // 1000
                
                # ボス未撃破の場合のみ処理
                if not db.is_boss_defeated(user.id, boss_stage):
                    # boss_preストーリーチェック（未表示の場合のみ表示）
                    story_id = f"boss_pre_{boss_stage}"
                    if not db.get_story_flag(user.id, story_id):
                        # ラスボス判定（10000m）
                        if boss_stage == 10:
                            embed = discord.Embed(
                                title="📖 運命の時",
                                description="強大な気配を感じる…なにが来るんだ？",
                                color=discord.Color.purple()
                            )
                        else:
                            embed = discord.Embed(
                                title="📖 試練の予兆",
                                description="強大な存在の気配を感じる…気を引き締めて……",
                                color=discord.Color.purple()
                            )
                        
                        await exploring_msg.edit(content=None, embed=embed)
                        await asyncio.sleep(2)
                        
                        # ストーリー完了後にボス戦を開始するコールバックを設定
                        view = StoryView(user.id, story_id, user_processing, 
                                        callback_data={
                                            'type': 'boss_battle',
                                            'boss_stage': boss_stage,
                                            'ctx': ctx
                                        })
                        await view.send_story(ctx)
                        view_delegated = True
                        return
                    
                    # ストーリー表示済みの場合、ボス戦に進む
                    boss = game.get_boss(boss_stage)
                    if boss:
                        player_data = {
                            "hp": player.get("hp", 100),
                            "mp": player.get("mp", 100),
                            "attack": player.get("atk", 10),
                            "defense": player.get("def", 5),
                            "inventory": player.get("inventory", []),
                            "distance": total_distance,
                            "user_id": user.id
                        }
                        
                        # ラスボス判定（10000m）
                        if boss_stage == 10:
                            embed = discord.Embed(
                                title="⚔️ ラスボス出現！",
                                description=f"**{boss['name']}** が最後の戦いに臨む！\n\nこれが最終決戦だ…！",
                                color=discord.Color.dark_gold()
                            )
                            await exploring_msg.edit(content=None, embed=embed)
                            await asyncio.sleep(3)
                            
                            view = FinalBossBattleView(ctx, player_data, boss, user_processing, boss_stage)
                            await view.send_initial_embed()
                            view_delegated = True
                            return
                        else:
                            embed = discord.Embed(
                                title="⚠️ ボス出現！",
                                description=f"**{boss['name']}** が目の前に立ちはだかる！",
                                color=discord.Color.dark_red()
                            )
                            await exploring_msg.edit(content=None, embed=embed)
                            await asyncio.sleep(2)
                            
                            view = BossBattleView(ctx, player_data, boss, user_processing, boss_stage)
                            await view.send_initial_embed()
                            view_delegated = True
                            return
            
        # 優先度2: 特殊イベント（500m毎、1000m除く）
        special_distances = [500, 1500, 2500, 3500, 4500, 5500, 6500, 7500, 8500, 9500]
        for special_distance in special_distances:
            if passed_through(special_distance):
                view = SpecialEventView(user.id, user_processing, special_distance)
                embed = discord.Embed(
                    title="✨ 特殊な雰囲気の場所だ……",
                    description="何が起こるのだろうか？",
                    color=discord.Color.purple()
                )
                embed.set_footer(text=f"📏 現在の距離: {special_distance}m")
                await exploring_msg.edit(content=None, embed=embed, view=view)
                view_delegated = True
                return
        
        # 優先度3: 距離ベースストーリー（250m, 750m, 1250m, etc.）
        story_distances = [250, 750, 1250, 1750, 2250, 2750, 3250, 3750, 4250, 4750, 5250, 5750, 6250, 6750, 7250, 7750, 8250, 8750, 9250, 9750]
        for story_distance in story_distances:
            if passed_through(story_distance):
                # 周回数に応じたストーリーIDを生成
                story_id = f"story_{story_distance}"
                if loop_count >= 2:
                    loop_story_id = f"story_{story_distance}_loop{loop_count}"
                    # 周回専用ストーリーが存在するかチェック
                    if not db.get_story_flag(user.id, loop_story_id):
                        story_id = loop_story_id
                
                if not db.get_story_flag(user.id, story_id):
                    embed = discord.Embed(
                        title="📖 探索中に何かを見つけた",
                        description="不思議な出来事が起こる予感…",
                        color=discord.Color.purple()
                    )
                    await exploring_msg.edit(content=None, embed=embed)
                    await asyncio.sleep(2)
                    
                    view = StoryView(user.id, story_id, user_processing)
                    await view.send_story(ctx)
                    view_delegated = True
                    return

        # 優先度4: 超低確率で選択肢分岐ストーリー（3%）
        choice_story_roll = random.random() * 100
        if choice_story_roll < 3:
            # 選択肢ストーリーのリスト
            choice_story_ids = [
                "choice_mysterious_door",
                "choice_strange_merchant",
                "choice_fork_road",
                "choice_mysterious_well",
                "choice_sleeping_dragon",
                "choice_cursed_treasure",
                "choice_time_traveler",
                "choice_fairy_spring"
            ]
            
            # 未体験の選択肢ストーリーをフィルタリング
            available_stories = [sid for sid in choice_story_ids if not db.get_story_flag(user.id, sid)]
            
            # 未体験のストーリーがある場合、ランダムに選択
            if available_stories:
                selected_story_id = random.choice(available_stories)
                
                embed = discord.Embed(
                    title="✨ イベント発生！",
                    description="運命の分岐点が現れた…",
                    color=discord.Color.gold()
                )
                await exploring_msg.edit(content=None, embed=embed)
                await asyncio.sleep(2)
                
                view = StoryView(user.id, selected_story_id, user_processing)
                await view.send_story(ctx)
                view_delegated = True
                return

        # 優先度5: 通常イベント抽選（60%何もなし/30%敵/9%宝箱/1%トラップ宝箱）
        event_roll = random.random() * 100
        
        # 1% トラップ宝箱
        if event_roll < 1:
            embed = discord.Embed(
                title="⚠️ 宝箱を見つけた！",
                description="何か罠が仕掛けられているような気がする…\nどうする？",
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"📏 現在の距離: {total_distance}m")
            view = TrapChestView(user.id, user_processing, player)
            await exploring_msg.edit(content=None, embed=embed, view=view)
            view_delegated = True
            return
        
        # 9% 宝箱（1～10%）
        elif event_roll < 10:
            embed = discord.Embed(
                title="⚠️ 宝箱を見つけた！",
                description="何か罠が仕掛けられているような気がする…\nどうする？",
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"📏 現在の距離: {total_distance}m")
            view = TreasureView(user.id, user_processing)
            await exploring_msg.edit(content=None, embed=embed, view=view)
            view_delegated = True
            return
        # 30% 敵との遭遇（10～40%）
        elif event_roll < 40:
            # game.pyから距離に応じた敵を取得
            enemy = game.get_random_enemy(total_distance)
            
            player_data = {
                "hp": player.get("hp", 100),
                "mp": player.get("mp", 100),
                "attack": player.get("atk", 10),
                "defense": player.get("def", 5),
                "inventory": player.get("inventory", []),
                "distance": total_distance,
                "user_id": user.id
            }

            # 戦闘Embed呼び出し
            await exploring_msg.edit(content="⚔️ 敵が現れた！ 戦闘開始！")
            view = BattleView(ctx, player_data, enemy, user_processing)
            await view.send_initial_embed()
            view_delegated = True
            return

        # 3. 何もなし
        embed = discord.Embed(
            title="📜 探索結果",
            description=f"→ {distance}m進んだ！\n何も見つからなかったようだ。",
            color=discord.Color.dark_grey()
        )
        embed.set_footer(text=f"📏 現在の距離: {total_distance}m")
        await exploring_msg.edit(content=None, embed=embed)
    finally:
        # Viewに委譲していない場合のみクリア（View自身がクリアする責任を持つ）
        if not view_delegated:
            user_processing[user.id] = False


# インベントリ
@bot.command()
@check_ban()
async def inventory(ctx):
    # 処理中チェック
    if user_processing.get(ctx.author.id):
        await ctx.send("⚠️ 別の処理が実行中です。完了するまでお待ちください。", delete_after=5)
        return
    
    player = db.get_player(ctx.author.id)
    if not player:
        await ctx.send("!start で冒険を始めてね。")
        return

    view = views.InventorySelectView(player)
    await ctx.send("🎒 インベントリ", view=view)

# ステータス&装備
@bot.command()
@check_ban()
async def status(ctx):
    try:
        # 他処理中チェック
        if 'user_processing' in globals() and user_processing.get(ctx.author.id):
            await ctx.send("⚠️ 別の処理が実行中です。完了するまでお待ちください。", delete_after=5)
            return

        # プレイヤー情報取得
        player = None
        if 'db' in globals():
            player = db.get_player(ctx.author.id)

        if not player:
            await ctx.send("!start で冒険を始めてね。")
            return

        # 装備情報取得
        equipped = {"weapon": "なし", "armor": "なし"}
        if 'db' in globals():
            temp = db.get_equipped_items(ctx.author.id)
            if isinstance(temp, dict):
                equipped["weapon"] = str(temp.get("weapon") or "なし")
                equipped["armor"] = str(temp.get("armor") or "なし")

        # 装備ボーナスを計算
        import game
        equipment_bonus = game.calculate_equipment_bonus(ctx.author.id)
        base_attack = player.get("atk", 10)
        base_defense = player.get("def", 5)
        total_attack = base_attack + equipment_bonus.get("attack_bonus", 0)
        total_defense = base_defense + equipment_bonus.get("defense_bonus", 0)
        
        # Embed作成
        embed = discord.Embed(title="📊 ステータス", color=discord.Color.blue())
        embed.add_field(name="名前", value=str(player.get("name", "未設定")), inline=True)
        embed.add_field(name="レベル", value=str(player.get("level", 1)), inline=True)
        embed.add_field(name="距離", value=f"{player.get('distance', 0)}m", inline=True)
        embed.add_field(name="HP", value=f"{player.get('hp', 100)}/{player.get('max_hp', 100)}", inline=True)
        embed.add_field(name="MP", value=f"{player.get('mp', 100)}/{player.get('max_mp', 100)}", inline=True)
        embed.add_field(name="EXP", value=f"{player.get('exp', 0)}/{db.get_required_exp(player.get('level', 1))}", inline=True)
        embed.add_field(name="攻撃力", value=f"{total_attack} ({base_attack}+{equipment_bonus.get('attack_bonus', 0)})", inline=True)
        embed.add_field(name="防御力", value=f"{total_defense} ({base_defense}+{equipment_bonus.get('defense_bonus', 0)})", inline=True)
        embed.add_field(name="所持金", value=f'{player.get("gold", 0)}G', inline=True)
        embed.add_field(name="装備武器", value=equipped["weapon"], inline=True)
        embed.add_field(name="装備防具", value=equipped["armor"], inline=True)

        # 装備変更UIを追加
        player_with_id = player.copy()
        player_with_id["user_id"] = ctx.author.id
        equip_view = views.EquipmentSelectView(player_with_id)
        
        await ctx.send(embed=embed, view=equip_view)

    except Exception as e:
        # エラー時はBotが落ちずに報告
        await ctx.send(f"⚠️ ステータス取得中にエラーが発生しました: {e}")
        print(f"statusコマンドエラー: {e}")

# アップグレード
@bot.command()
@check_ban()
async def upgrade(ctx):
    if user_processing.get(ctx.author.id):
        await ctx.send("⚠️ 別の処理が実行中です。完了するまでお待ちください。", delete_after=5)
        return
    
    player = db.get_player(ctx.author.id)
    if not player:
        await ctx.send("!start で冒険を始めてね。")
        return
    
    # クリア状態チェック
    if db.is_game_cleared(ctx.author.id):
        embed = discord.Embed(
            title="⚠️ ダンジョン踏破済",
            description="あなたはダンジョンをクリアしています！\n`!reset` で'データをリセットして再度冒険を初めてください。\n\n※周回システムは実装予定です。アップデートにご期待ください！",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        return
    
    points = player.get("upgrade_points", 0)
    upgrades = db.get_upgrade_levels(ctx.author.id)
    
    embed = discord.Embed(title="⬆️ アップグレード", description=f"所持ポイント: **{points}**", color=0xFFD700)
    embed.add_field(
        name="1️⃣ 初期HP最大量アップ (5ポイント)",
        value=f"現在Lv.{upgrades['initial_hp']} → 最大HP +10",
        inline=False
    )
    embed.add_field(
        name="2️⃣ 初期MP最大量アップ (5ポイント)",
        value=f"現在Lv.{upgrades['initial_mp']} → 最大MP +10",
        inline=False
    )
    embed.add_field(
        name="3️⃣ コイン取得量アップ (5ポイント)",
        value=f"現在Lv.{upgrades['coin_gain']} → コイン +10%",
        inline=False
    )
    embed.set_footer(text="!buy_upgrade <番号> でアップグレード購入")
    
    await ctx.send(embed=embed)

# アップグレード購入
@bot.command()
@check_ban()
async def buy_upgrade(ctx, upgrade_type: int):
    if user_processing.get(ctx.author.id):
        await ctx.send("⚠️ 別の処理が実行中です。完了するまでお待ちください。", delete_after=5)
        return
    
    player = db.get_player(ctx.author.id)
    if not player:
        await ctx.send("!start で冒険を始めてね。")
        return
    
    # クリア状態チェック
    if db.is_game_cleared(ctx.author.id):
        embed = discord.Embed(
            title="⚠️ ダンジョン踏破済",
            description="あなたはダンジョンをクリアしています！\n`!reset` で'データをリセットして再度冒険を初めてください。\n\n※周回システムは実装予定です。アップデートにご期待ください！",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        return
    
    costs = {1: 5, 2: 5, 3: 5}
    
    if upgrade_type not in costs:
        await ctx.send("無効なアップグレード番号です。1, 2, 3から選んでください。")
        return
    
    cost = costs[upgrade_type]
    points = player.get("upgrade_points", 0)
    
    if points < cost:
        await ctx.send(f"ポイントが足りません！必要: {cost}ポイント、所持: {points}ポイント")
        return
    
    if upgrade_type == 1:
        db.upgrade_initial_hp(ctx.author.id)
        db.spend_upgrade_points(ctx.author.id, cost)
        await ctx.send("✅ 初期HP最大量をアップグレードしました！ 最大HP +10")
    elif upgrade_type == 2:
        db.upgrade_initial_mp(ctx.author.id)
        db.spend_upgrade_points(ctx.author.id, cost)
        await ctx.send("✅ 初期MP最大量をアップグレードしました！ 最大MP +10")
    elif upgrade_type == 3:
        db.upgrade_coin_gain(ctx.author.id)
        db.spend_upgrade_points(ctx.author.id, cost)
        await ctx.send("✅ コイン取得量をアップグレードしました！ コイン取得 +10%")

# デバッグコマンドの読み込み（削除可能）
try:
    import debug_commands
    debug_commands.setup(bot, user_processing)
    print("✅ デバッグコマンドを読み込みました")
except ImportError:
    print("ℹ️ デバッグコマンドは利用できません（debug_commands.py が見つかりません）")
except Exception as e:
    print(f"⚠️ デバッグコマンドの読み込みエラー: {e}")

import asyncio
from aiohttp import web

async def health_check(request):
    return web.Response(text="OK", status=200)

async def run_health_server():
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()
    print("✅ ヘルスチェックサーバーを起動しました (ポート 8000)")

async def main():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("❌ エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません")
        exit(1)
    
    # Health server を起動してから Bot を起動
    await run_health_server()
    
    print("🤖 Discord BOTを起動します...")
    async with bot:
        await bot.start(token)


@bot.command(name="servers")
async def show_servers(ctx: commands.Context):
    """BOTが参加しているサーバー一覧を表示(開発者用・ページネーション付き)"""
    
    # 開発者のみ実行可能にする
    DEVELOPER_ID = "1301416493401243694"  # あなたのDiscord ID
    
    if str(ctx.author.id) != DEVELOPER_ID:
        await ctx.send("❌ このコマンドは開発者のみ実行できます")
        return
    
    guilds_list = list(bot.guilds)
    total_servers = len(guilds_list)
    
    if total_servers == 0:
        await ctx.send("📭 BOTはどのサーバーにも参加していません")
        return
    
    # ページネーション用のView
    class ServerListView(discord.ui.View):
        def __init__(self, guilds, user_id):
            super().__init__(timeout=180)  # 3分でタイムアウト
            self.guilds = guilds
            self.user_id = user_id
            self.current_page = 0
            self.max_page = (len(guilds) - 1) // 10
            
            # 最初のページでは前のページボタンを無効化
            self.update_buttons()
        
        def update_buttons(self):
            """ボタンの有効/無効を更新"""
            self.children[0].disabled = (self.current_page == 0)  # 前へボタン
            self.children[1].disabled = (self.current_page >= self.max_page)  # 次へボタン
        
        def create_embed(self):
            """現在のページのEmbedを作成"""
            start_idx = self.current_page * 10
            end_idx = min(start_idx + 10, len(self.guilds))
            
            embed = discord.Embed(
                title="🌐 BOTが参加しているサーバー",
                description=f"合計: **{len(self.guilds)}** サーバー",
                color=discord.Color.blue()
            )
            
            for guild in self.guilds[start_idx:end_idx]:
                embed.add_field(
                    name=f"📍 {guild.name}",
                    value=f"ID: `{guild.id}`\nメンバー: {guild.member_count}人",
                    inline=False
                )
            
            embed.set_footer(text=f"ページ {self.current_page + 1} / {self.max_page + 1}")
            return embed
        
        @discord.ui.button(label="◀ 前へ", style=discord.ButtonStyle.primary)
        async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            # 実行者チェック
            if str(interaction.user.id) != self.user_id:
                await interaction.response.send_message("❌ このボタンは実行者のみ操作できます", ephemeral=True)
                return
            
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        
        @discord.ui.button(label="次へ ▶", style=discord.ButtonStyle.primary)
        async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            # 実行者チェック
            if str(interaction.user.id) != self.user_id:
                await interaction.response.send_message("❌ このボタンは実行者のみ操作できます", ephemeral=True)
                return
            
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        
        @discord.ui.button(label="❌ 閉じる", style=discord.ButtonStyle.danger)
        async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            # 実行者チェック
            if str(interaction.user.id) != self.user_id:
                await interaction.response.send_message("❌ このボタンは実行者のみ操作できます", ephemeral=True)
                return
            
            await interaction.message.delete()
    
    # Viewとメッセージを送信
    view = ServerListView(guilds_list, str(ctx.author.id))
    await ctx.send(embed=view.create_embed(), view=view)

asyncio.run(main())
