from supabase import create_client
import config

supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

def get_player(user_id):
    """プレイヤーデータを取得"""
    res = supabase.table("players").select("*").eq("user_id", str(user_id)).execute()
    return res.data[0] if res.data else None

def create_player(user_id: int):
    """新規プレイヤーを作成（デフォルト値はテーブル定義に従う）"""
    supabase.table("players").insert({
        "user_id": str(user_id)
    }).execute()

def update_player(user_id, **kwargs):
    """プレイヤーデータを更新"""
    supabase.table("players").update(kwargs).eq("user_id", str(user_id)).execute()

def delete_player(user_id):
    """プレイヤーデータを削除"""
    supabase.table("players").delete().eq("user_id", str(user_id)).execute()

def add_item_to_inventory(user_id, item_name):
    """インベントリにアイテムを追加"""
    if item_name == "none":
        """アイテムがnoneの場合は何もせず終了"""
        return

    player = get_player(user_id)
    if player:
        inventory = player.get("inventory", [])
        inventory.append(item_name)
        update_player(user_id, inventory=inventory)

def remove_item_from_inventory(user_id, item_name):
    """インベントリからアイテムを削除"""
    player = get_player(user_id)
    if player:
        inventory = player.get("inventory", [])
        if item_name in inventory:
            inventory.remove(item_name)
            update_player(user_id, inventory=inventory)

def add_gold(user_id, amount):
    """ゴールドを追加"""
    player = get_player(user_id)
    if player:
        current_gold = player.get("gold", 0)
        update_player(user_id, gold=current_gold + amount)

def get_player_distance(user_id):
    """プレイヤーの現在距離を取得"""
    player = get_player(user_id)
    return player.get("distance", 0) if player else 0

def update_player_distance(user_id, distance):
    """プレイヤーの距離を更新"""
    floor = distance // 100
    stage = distance // 1000
    update_player(user_id, distance=distance, current_floor=floor, current_stage=stage)

def add_player_distance(user_id, increment):
    """プレイヤーの距離を加算"""
    player = get_player(user_id)
    if not player:
        return 0

    current_distance = player.get("distance", 0)
    new_distance = current_distance + increment

    floor = new_distance // 100
    stage = new_distance // 1000

    # スキル解放チェック（1000m毎）
    check_and_unlock_distance_skills(user_id, new_distance)

    # 新しい距離を設定
    update_player(user_id, 
                  distance=new_distance, 
                  current_floor=floor, 
                  current_stage=stage)

    return new_distance

def get_previous_distance(user_id):
    """前回の距離を取得（現在の距離を返す）"""
    player = get_player(user_id)
    return player.get("distance", 0) if player else 0

def get_milestone_flag(user_id, flag_name):
    """マイルストーンフラグを取得"""
    player = get_player(user_id)
    if player:
        flags = player.get("milestone_flags", {})
        return flags.get(flag_name, False)
    return False

def set_milestone_flag(user_id, flag_name, value=True):
    """マイルストーンフラグを設定"""
    player = get_player(user_id)
    if player:
        flags = player.get("milestone_flags", {})
        flags[flag_name] = value
        update_player(user_id, milestone_flags=flags)

def is_boss_defeated(user_id, boss_id):
    """ボスが倒されたかチェック"""
    player = get_player(user_id)
    if player:
        boss_flags = player.get("boss_defeated_flags", {})
        return boss_flags.get(str(boss_id), False)
    return False

def set_boss_defeated(user_id, boss_id):
    """ボス撃破フラグを設定"""
    player = get_player(user_id)
    if player:
        boss_flags = player.get("boss_defeated_flags", {})
        boss_flags[str(boss_id)] = True
        update_player(user_id, boss_defeated_flags=boss_flags)

def get_tutorial_flag(user_id, tutorial_name):
    """チュートリアルフラグを取得"""
    player = get_player(user_id)
    if player:
        flags = player.get("tutorial_flags", {})
        return flags.get(tutorial_name, False)
    return False

def set_tutorial_flag(user_id, tutorial_name):
    """チュートリアルフラグを設定"""
    player = get_player(user_id)
    if player:
        flags = player.get("tutorial_flags", {})
        flags[tutorial_name] = True
        update_player(user_id, tutorial_flags=flags)

def add_secret_weapon(user_id, weapon_id):
    """シークレット武器を追加"""
    player = get_player(user_id)
    if player:
        secret_weapons = player.get("secret_weapon_ids", [])
        if weapon_id not in secret_weapons:
            secret_weapons.append(weapon_id)
            update_player(user_id, secret_weapon_ids=secret_weapons)
            return True
    return False

def get_loop_count(user_id):
    """周回数を取得（互換性のため残す。death_countを返す）"""
    return get_death_count(user_id)

def get_death_count(user_id):
    """死亡回数を取得"""
    player = get_player(user_id)
    return player.get("death_count", 0) if player else 0

def equip_weapon(user_id, weapon_name):
    """武器を装備"""
    update_player(user_id, equipped_weapon=weapon_name)

def equip_armor(user_id, armor_name):
    """防具を装備"""
    update_player(user_id, equipped_armor=armor_name)

def get_equipped_items(user_id):
    """装備中のアイテムを取得"""
    player = get_player(user_id)
    if player:
        return {
            "weapon": player.get("equipped_weapon"),
            "armor": player.get("equipped_armor")
        }
    return {"weapon": None, "armor": None}

def add_upgrade_points(user_id, points):
    """アップグレードポイントを追加"""
    player = get_player(user_id)
    if player:
        current_points = player.get("upgrade_points", 0)
        update_player(user_id, upgrade_points=current_points + points)

def spend_upgrade_points(user_id, points):
    """アップグレードポイントを消費"""
    player = get_player(user_id)
    if player:
        current_points = player.get("upgrade_points", 0)
        if current_points >= points:
            update_player(user_id, upgrade_points=current_points - points)
            return True
    return False

def increment_death_count(user_id):
    """死亡回数を増やす"""
    player = get_player(user_id)
    if player:
        death_count = player.get("death_count", 0)
        update_player(user_id, death_count=death_count + 1)
        return death_count + 1
    return 0

def get_upgrade_levels(user_id):
    """アップグレードレベルを取得"""
    player = get_player(user_id)
    if player:
        return {
            "initial_hp": player.get("initial_hp_upgrade", 0),
            "initial_mp": player.get("initial_mp_upgrade", 0),
            "coin_gain": player.get("coin_gain_upgrade", 0)
        }
    return {"initial_hp": 0, "initial_mp": 0, "coin_gain": 0}

def upgrade_initial_hp(user_id):
    """初期HP最大量をアップグレード"""
    player = get_player(user_id)
    if player:
        current_level = player.get("initial_hp_upgrade", 0)
        new_max_hp = player.get("max_hp", 100) + 20
        update_player(user_id, initial_hp_upgrade=current_level + 1, max_hp=new_max_hp)
        return True
    return False

def upgrade_initial_mp(user_id):
    """初期MP最大量をアップグレード"""
    player = get_player(user_id)
    if player:
        current_level = player.get("initial_mp_upgrade", 0)
        new_max_mp = player.get("max_mp", 100) + 15
        update_player(user_id, initial_mp_upgrade=current_level + 1, max_mp=new_max_mp)
        return True
    return False

def upgrade_coin_gain(user_id):
    """コイン取得量をアップグレード"""
    player = get_player(user_id)
    if player:
        current_level = player.get("coin_gain_upgrade", 0)
        new_multiplier = player.get("coin_multiplier", 1.0) + 0.1
        update_player(user_id, coin_gain_upgrade=current_level + 1, coin_multiplier=new_multiplier)
        return True
    return False

def handle_player_death(user_id, killed_by_enemy_name=None, enemy_type="normal"):
    """プレイヤー死亡時の処理（ポイント付与、死亡回数増加、全アイテム消失、フラグクリア）"""
    player = get_player(user_id)
    if player:
        distance = player.get("distance", 0)
        floor = distance // 100
        stage = distance // 1000
        points = max(1, floor // 2)

        add_upgrade_points(user_id, points)
        death_count = increment_death_count(user_id)

        # 🆕 死亡履歴を記録
        if killed_by_enemy_name:
            record_death_history(user_id, killed_by_enemy_name, distance, floor, stage, enemy_type)

        # 死亡時リセット：全アイテム消失、装備解除、ゴールドリセット、フラグクリア、ゲームクリア状態リセット
        update_player(user_id, 
                      hp=player.get("max_hp", 100),
                      mp=player.get("max_mp", 100),
                      distance=0, 
                      current_floor=0, 
                      current_stage=0,
                      inventory=[],
                      equipped_weapon=None,
                      equipped_armor=None,
                      gold=0,
                      story_flags={},
                      boss_defeated_flags={},
                      mp_stunned=False,
                      game_cleared=False)

        return {
            "points": points, 
            "death_count": death_count, 
            "floor": floor, 
            "distance": distance,
            "killed_by": killed_by_enemy_name  # 🆕 追加
        }
    return None

def handle_boss_clear(user_id):
    """ラスボス撃破時の処理（クリア報酬、クリア状態フラグ設定）

    注意: この関数ではデータリセットを行わない。
    リセットは!resetコマンドでユーザーが手動で行う。
    """
    player = get_player(user_id)
    if player:
        # クリア報酬（固定50ポイント）
        add_upgrade_points(user_id, 50)

        # クリア状態フラグを設定（リセットは行わない）
        update_player(user_id, game_cleared=True)

        return {
            "points_gained": 50
        }
    return None

def get_story_flag(user_id, story_id):
    """ストーリー既読フラグを取得"""
    player = get_player(user_id)
    if player:
        flags = player.get("story_flags", {})
        return flags.get(story_id, False)
    return False

def set_story_flag(user_id, story_id):
    """ストーリー既読フラグを設定"""
    player = get_player(user_id)
    if player:
        flags = player.get("story_flags", {})
        flags[story_id] = True
        update_player(user_id, story_flags=flags)

def clear_story_flags(user_id):
    """ストーリーフラグをクリア（周回リセット用）"""
    player = get_player(user_id)
    if player:
        update_player(user_id, story_flags={})

def get_global_weapon_count(weapon_id):
    """シークレット武器のグローバル排出数を取得"""
    try:
        res = supabase.table("secret_weapons_global").select("total_dropped").eq("weapon_id", weapon_id).execute()
        if res.data and len(res.data) > 0:
            return res.data[0].get("total_dropped", 0)
        return 0
    except:
        return 0

def increment_global_weapon_count(weapon_id):
    """シークレット武器のグローバル排出数を増やす"""
    try:
        current_count = get_global_weapon_count(weapon_id)

        if current_count == 0:
            supabase.table("secret_weapons_global").insert({
                "weapon_id": weapon_id,
                "total_dropped": 1,
                "max_limit": 10
            }).execute()
        else:
            supabase.table("secret_weapons_global").update({
                "total_dropped": current_count + 1
            }).eq("weapon_id", weapon_id).execute()

        return True
    except Exception as e:
        print(f"Error incrementing weapon count: {e}")
        return False

def get_available_secret_weapons():
    """排出可能なシークレット武器リストを取得（上限10個未満のもの）"""
    import game
    available_weapons = []

    for weapon in game.SECRET_WEAPONS:
        weapon_id = weapon["id"]
        count = get_global_weapon_count(weapon_id)
        if count < 10:
            available_weapons.append(weapon)

    return available_weapons

# ==============================
# EXP / レベルシステム
# ==============================

def get_required_exp(level):
    """レベルアップに必要なEXPを計算"""
    return level * 100

def add_exp(user_id, amount):
    """EXPを追加してレベルアップ処理"""
    player = get_player(user_id)
    if not player:
        return None

    current_exp = player.get("exp", 0)
    current_level = player.get("level", 1)
    new_exp = current_exp + amount

    level_ups = []

    # レベルアップチェック
    while new_exp >= get_required_exp(current_level):
        new_exp -= get_required_exp(current_level)
        current_level += 1

        # ステータス上昇
        new_hp = player.get("hp", 100) + 5
        new_max_hp = player.get("max_hp", 100) + 5
        new_atk = player.get("atk", 5) + 1
        new_def = player.get("def", 3) + 1

        update_data = {
            "level": current_level,
            "hp": new_hp,
            "max_hp": new_max_hp,
            "atk": new_atk,
            "def": new_def
        }
        update_player(user_id, **update_data)

        level_ups.append({
            "new_level": current_level,
            "hp_gain": 5,
            "atk_gain": 1,
            "def_gain": 1
        })

        player = get_player(user_id)

    # 残りEXPを更新
    update_player(user_id, exp=new_exp)

    return {
        "exp_gained": amount,
        "current_exp": new_exp,
        "current_level": current_level,
        "level_ups": level_ups
    }

# ==============================
# MP システム
# ==============================

def consume_mp(user_id, amount):
    """MPを消費"""
    player = get_player(user_id)
    if not player:
        return False

    current_mp = player.get("mp", 100)
    if current_mp >= amount:
        new_mp = current_mp - amount
        update_player(user_id, mp=new_mp)

        # MP=0の場合、行動不能フラグ
        if new_mp == 0:
            update_player(user_id, mp_stunned=True)

        return True
    return False

def restore_mp(user_id, amount):
    """MPを回復"""
    player = get_player(user_id)
    if not player:
        return 0

    current_mp = player.get("mp", 100)
    max_mp = player.get("max_mp", 100)
    new_mp = min(current_mp + amount, max_mp)
    update_player(user_id, mp=new_mp)

    return new_mp - current_mp

def set_mp_stunned(user_id, stunned):
    """MP枯渇による行動不能フラグを設定"""
    update_player(user_id, mp_stunned=stunned)

def is_mp_stunned(user_id):
    """MP枯渇チェック"""
    player = get_player(user_id)
    return player.get("mp_stunned", False) if player else False

# ==============================
# スキル システム
# ==============================

def get_unlocked_skills(user_id):
    """解放済みスキルリストを取得"""
    player = get_player(user_id)
    if player:
        return player.get("unlocked_skills", ["体当たり"])
    return ["体当たり"]

def unlock_skill(user_id, skill_id):
    """スキルを解放"""
    player = get_player(user_id)
    if player:
        unlocked = player.get("unlocked_skills", ["体当たり"])
        if skill_id not in unlocked:
            unlocked.append(skill_id)
            update_player(user_id, unlocked_skills=unlocked)
            return True
    return False

def check_and_unlock_distance_skills(user_id, distance):
    """距離に応じてスキルを自動解放"""
    skill_unlock_map = {
        1000: "小火球",
        2000: "軽傷治癒",
        3000: "強攻撃",
        4000: "ファイアボール",
        5000: "中治癒",
        6000: "猛攻撃",
        7000: "爆炎",
        8000: "完全治癒",
        9000: "神速の一閃",
        10000: "究極魔法"
    }

    for unlock_distance, skill_id in skill_unlock_map.items():
        if distance >= unlock_distance:
            unlock_skill(user_id, skill_id)

# ==============================
# 倉庫システム (Storage System)
# ==============================

def add_to_storage(user_id, item_name, item_type):
    """倉庫にアイテムを追加"""
    try:
        supabase.table("storage").insert({
            "user_id": str(user_id),
            "item_name": item_name,
            "item_type": item_type,
            "is_taken": False
        }).execute()
        return True
    except Exception as e:
        print(f"Error adding to storage: {e}")
        return False

def get_storage_items(user_id, include_taken=False):
    """倉庫のアイテムリストを取得"""
    try:
        query = supabase.table("storage").select("*").eq("user_id", str(user_id))

        if not include_taken:
            query = query.eq("is_taken", False)

        res = query.order("stored_at", desc=True).execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"Error getting storage items: {e}")
        return []

def take_from_storage(user_id, storage_id):
    """倉庫からアイテムを取り出す（is_takenをTrueにする）"""
    try:
        from datetime import datetime
        supabase.table("storage").update({
            "is_taken": True,
            "taken_at": datetime.now().isoformat()
        }).eq("id", storage_id).eq("user_id", str(user_id)).execute()
        return True
    except Exception as e:
        print(f"Error taking from storage: {e}")
        return False

def get_storage_item_by_id(storage_id):
    """倉庫アイテムをIDで取得"""
    try:
        res = supabase.table("storage").select("*").eq("id", storage_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        print(f"Error getting storage item: {e}")
        return None

# ==============================
# ゲームクリア状態管理
# ==============================

def set_game_cleared(user_id, cleared=True):
    """ゲームクリア状態を設定"""
    update_player(user_id, game_cleared=cleared)

def is_game_cleared(user_id):
    """ゲームクリア状態を取得"""
    player = get_player(user_id)
    return player.get("game_cleared", False) if player else False

def is_player_banned(user_id):
    """プレイヤーがBANされているかチェック"""
    player = get_player(user_id)
    if player:
        bot_banned = player.get("bot_banned", False)
        return bot_banned
    return False

def get_ban_status(user_id):
    """BAN状態の詳細を取得"""
    player = get_player(user_id)
    if player:
        return {
            "bot_banned": player.get("bot_banned", False),
            "web_banned": player.get("web_banned", False)
        }
    return {"bot_banned": False, "web_banned": False}

# 死亡履歴システム

def record_death_history(user_id, enemy_name, distance=0, floor=0, stage=0, enemy_type="normal"):
    """死亡履歴を記録"""
    try:
        supabase.table("death_history").insert({
            "user_id": str(user_id),
            "enemy_name": enemy_name,
            "enemy_type": enemy_type,
            "distance": distance,
            "floor": floor,
            "stage": stage
        }).execute()

        # total_deaths カウントアップ（オプション）
        player = get_player(user_id)
        if player:
            total_deaths = player.get("total_deaths", 0) + 1
            update_player(user_id, total_deaths=total_deaths)

        return True
    except Exception as e:
        print(f"Error recording death history: {e}")
        return False

def get_death_history(user_id, limit=100):
    """死亡履歴を取得（最新limit件）"""
    try:
        res = supabase.table("death_history")\
            .select("*")\
            .eq("user_id", str(user_id))\
            .order("died_at", desc=True)\
            .limit(limit)\
            .execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"Error getting death history: {e}")
        return []

def get_death_count_by_enemy(user_id, enemy_name):
    """特定の敵に殺された回数を取得"""
    try:
        res = supabase.table("death_history")\
            .select("id", count="exact")\
            .eq("user_id", str(user_id))\
            .eq("enemy_name", enemy_name)\
            .execute()
        return res.count if res.count else 0
    except Exception as e:
        print(f"Error getting death count: {e}")
        return 0

def get_death_stats(user_id):
    """死亡統計を取得（敵ごとの死亡回数）"""
    try:
        history = get_death_history(user_id, limit=1000)
        stats = {}

        for death in history:
            enemy_name = death.get("enemy_name", "不明")
            if enemy_name in stats:
                stats[enemy_name] += 1
            else:
                stats[enemy_name] = 1

        # 死亡回数順にソート
        sorted_stats = dict(sorted(stats.items(), key=lambda x: x[1], reverse=True))
        return sorted_stats
    except Exception as e:
        print(f"Error getting death stats: {e}")
        return {}

def get_recent_deaths(user_id, limit=5):
    """直近N回の死亡履歴を取得"""
    try:
        res = supabase.table("death_history")\
            .select("*")\
            .eq("user_id", str(user_id))\
            .order("died_at", desc=True)\
            .limit(limit)\
            .execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"Error getting recent deaths: {e}")
        return []

def check_death_pattern(user_id, pattern):
    """
    特定の死亡パターンをチェック
    pattern: ["敵A", "敵B", "敵C"] のようなリスト（順番重要）
    """
    try:
        recent = get_recent_deaths(user_id, limit=len(pattern))
        if len(recent) < len(pattern):
            return False

        for i, expected_enemy in enumerate(pattern):
            if recent[i].get("enemy_name") != expected_enemy:
                return False

        return True
    except Exception as e:
        print(f"Error checking death pattern: {e}")
        return False

# 称号システム

def add_title(user_id, title_id, title_name):
    """称号を追加（重複は無視）"""
    try:
        supabase.table("player_titles").insert({
            "user_id": str(user_id),
            "title_id": title_id,
            "title_name": title_name
        }).execute()
        return True
    except Exception as e:
        # UNIQUE制約違反（既に持っている）は無視
        if "duplicate key" in str(e).lower():
            return False
        print(f"Error adding title: {e}")
        return False

def get_player_titles(user_id):
    """プレイヤーが持っている称号一覧を取得"""
    try:
        res = supabase.table("player_titles")\
            .select("*")\
            .eq("user_id", str(user_id))\
            .order("unlocked_at", desc=True)\
            .execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"Error getting titles: {e}")
        return []

def has_title(user_id, title_id):
    """特定の称号を持っているかチェック"""
    try:
        res = supabase.table("player_titles")\
            .select("id")\
            .eq("user_id", str(user_id))\
            .eq("title_id", title_id)\
            .execute()
        return len(res.data) > 0 if res.data else False
    except Exception as e:
        print(f"Error checking title: {e}")
        return False

def set_active_title(user_id, title_id):
    """装備中の称号を設定"""
    # 称号を持っているか確認
    if not has_title(user_id, title_id):
        return False

    update_player(user_id, active_title=title_id)
    return True

def get_active_title(user_id):
    """現在装備中の称号を取得"""
    player = get_player(user_id)
    if player:
        title_id = player.get("active_title")
        if title_id:
            # 称号名を取得
            titles = get_player_titles(user_id)
            for title in titles:
                if title.get("title_id") == title_id:
                    return title.get("title_name")
    return None

def unequip_title(user_id):
    """称号を外す"""
    update_player(user_id, active_title=None)
    return True
