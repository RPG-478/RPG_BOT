import httpx
import config
import logging
import asyncio
import inspect
import threading
from typing import Optional, Dict, List, Any
import json
from typing import Callable

logger = logging.getLogger("rpgbot")

_http_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()

def _get_headers() -> Dict[str, str]:
    """Supabase REST API用のヘッダーを取得"""
    return {
        "apikey": config.SUPABASE_KEY or "",
        "Authorization": f"Bearer {config.SUPABASE_KEY or ''}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"  # INSERT/UPDATEでデータを返す
    }


def _format_httpx_error(exc: Exception) -> str:
    """httpx の例外からレスポンス本文を安全に取り出してログ用に整形。"""
    if isinstance(exc, httpx.HTTPStatusError):
        resp = exc.response
        try:
            body = resp.text
        except Exception:
            body = "<failed to read response body>"
        body = (body or "").strip()
        if len(body) > 800:
            body = body[:800] + "..."
        return f"{exc} | status={resp.status_code} body={body!r}"
    return str(exc)


def _extract_postgrest_error(exc: Exception) -> Optional[dict]:
    """PostgREST のエラーレスポンス(JSON)を取得できるなら返す。"""
    if not isinstance(exc, httpx.HTTPStatusError):
        return None
    try:
        data = exc.response.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None

async def get_client() -> httpx.AsyncClient:
    """非同期HTTPクライアントを取得（シングルトンパターン）"""
    global _http_client
    
    if _http_client is None:
        async with _client_lock:
            if _http_client is None:
                _http_client = httpx.AsyncClient(timeout=30.0)
                logger.info("✅ HTTPクライアントを初期化しました")
    
    return _http_client

async def close_client():
    """HTTPクライアントをクローズ（Bot終了時に呼び出し）"""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.info("✅ HTTPクライアントをクローズしました")

async def get_player(user_id):
    """プレイヤーデータを取得"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/players"
    params = {"user_id": f"eq.{str(user_id)}", "select": "*"}
    
    response = await client.get(url, headers=_get_headers(), params=params)
    response.raise_for_status()
    
    data = response.json()
    return data[0] if data else None

async def create_player(user_id: int):
    """新規プレイヤーを作成（デフォルト値を明示的に設定）"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/players"
    
    player_data = {
        "user_id": str(user_id),
        "hp": 50,
        "max_hp": 50,
        "mp": 20,
        "max_mp": 20,
        "atk": 5,
        "def": 2
    }
    
    response = await client.post(url, headers=_get_headers(), json=player_data)
    response.raise_for_status()
    return response.json()

async def update_player(user_id, **kwargs):
    """プレイヤーデータを更新"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/players"
    params = {"user_id": f"eq.{str(user_id)}"}
    
    response = await client.patch(url, headers=_get_headers(), params=params, json=kwargs)
    response.raise_for_status()
    return response.json()

async def delete_player(user_id):
    """プレイヤーデータを削除（レイドステータスは保持）"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/players"
    params = {"user_id": f"eq.{str(user_id)}"}
    
    response = await client.delete(url, headers=_get_headers(), params=params)
    response.raise_for_status()


# ==============================
# Guild settings (server-scoped)
# ==============================

async def get_guild_settings(guild_id: int) -> Optional[dict]:
    """ギルド（サーバー）単位の設定を取得。

    注意: Supabase側に `guild_settings` テーブルが無い場合でもBOTが落ちないように None を返す。
    """
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/guild_settings"
    params = {"guild_id": f"eq.{str(guild_id)}", "select": "*"}

    try:
        response = await client.get(url, headers=_get_headers(), params=params)
        if response.status_code >= 400:
            logger.warning(f"get_guild_settings failed: {response.status_code} {response.text}")
            return None
        data = response.json()
        return data[0] if data else None
    except Exception as e:
        logger.warning(f"get_guild_settings exception: {e}")
        return None


async def set_guild_adventure_parent_channel(guild_id: int, channel_id: int) -> bool:
    """ギルド単位で、冒険スレッドを作る親チャンネルを保存（UPSERT）。"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/guild_settings"

    payload = {
        "guild_id": str(guild_id),
        "adventure_parent_channel_id": str(channel_id),
    }

    # upsert
    headers = _get_headers().copy()
    headers["Prefer"] = "return=representation,resolution=merge-duplicates"

    try:
        response = await client.post(
            url,
            headers=headers,
            params={"on_conflict": "guild_id"},
            json=payload,
        )
        if response.status_code >= 400:
            logger.warning(f"set_guild_adventure_parent_channel failed: {response.status_code} {response.text}")
            return False
        return True
    except Exception as e:
        logger.warning(f"set_guild_adventure_parent_channel exception: {e}")
        return False


async def clear_guild_settings(guild_id: int) -> bool:
    """ギルド設定を削除（`!set off` 用）。"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/guild_settings"
    params = {"guild_id": f"eq.{str(guild_id)}"}
    try:
        response = await client.delete(url, headers=_get_headers(), params=params)
        if response.status_code >= 400:
            logger.warning(f"clear_guild_settings failed: {response.status_code} {response.text}")
            return False
        return True
    except Exception as e:
        logger.warning(f"clear_guild_settings exception: {e}")
        return False


# ==============================
# Adventure thread id (player-scoped)
# ==============================

_ADVENTURE_THREAD_KEY = "_adventure_thread_id"
_ADVENTURE_GUILD_KEY = "_adventure_guild_id"


async def get_adventure_thread_id(user_id: int) -> Optional[int]:
    """プレイヤーに紐づく冒険スレッドIDを取得（保存先は milestone_flags を利用）。"""
    player = await get_player(user_id)
    if not player:
        return None
    flags = player.get("milestone_flags", {}) or {}
    raw = flags.get(_ADVENTURE_THREAD_KEY)
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


async def set_adventure_thread(user_id: int, thread_id: int, guild_id: int) -> None:
    """冒険スレッドIDを保存（milestone_flags）。"""
    player = await get_player(user_id)
    flags = (player.get("milestone_flags", {}) if player else {}) or {}
    flags[_ADVENTURE_THREAD_KEY] = str(thread_id)
    flags[_ADVENTURE_GUILD_KEY] = str(guild_id)
    await update_player(user_id, milestone_flags=flags)


async def clear_adventure_thread(user_id: int) -> None:
    """冒険スレッドIDを削除（milestone_flags）。"""
    player = await get_player(user_id)
    if not player:
        return
    flags = player.get("milestone_flags", {}) or {}
    changed = False
    if _ADVENTURE_THREAD_KEY in flags:
        flags.pop(_ADVENTURE_THREAD_KEY, None)
        changed = True
    if _ADVENTURE_GUILD_KEY in flags:
        flags.pop(_ADVENTURE_GUILD_KEY, None)
        changed = True
    if changed:
        await update_player(user_id, milestone_flags=flags)

async def add_item_to_inventory(user_id, item_name):
    """インベントリにアイテムを追加"""
    if item_name == "none":
        """アイテムがnoneの場合は何もせず終了"""
        return

    player = await get_player(user_id)
    if player:
        inventory = player.get("inventory", [])
        inventory.append(item_name)
        await update_player(user_id, inventory=inventory)

async def remove_item_from_inventory(user_id, item_name):
    """インベントリからアイテムを削除"""
    player = await get_player(user_id)
    if player:
        inventory = player.get("inventory", [])
        if item_name in inventory:
            inventory.remove(item_name)
            await update_player(user_id, inventory=inventory)

async def add_gold(user_id, amount):
    """ゴールドを追加"""
    player = await get_player(user_id)
    if player:
        current_gold = player.get("gold", 0)
        await update_player(user_id, gold=current_gold + amount)

async def get_player_distance(user_id):
    """プレイヤーの現在距離を取得"""
    player = await get_player(user_id)
    return player.get("distance", 0) if player else 0

async def update_player_distance(user_id, distance):
    """プレイヤーの距離を更新"""
    floor = distance // 100
    stage = distance // 1000
    await update_player(user_id, distance=distance, current_floor=floor, current_stage=stage)

async def add_player_distance(user_id, increment):
    """プレイヤーの距離を加算"""
    player = await get_player(user_id)
    if not player:
        return 0

    current_distance = player.get("distance", 0)
    new_distance = current_distance + increment

    floor = new_distance // 100
    stage = new_distance // 1000

    # スキル解放チェック（1000m毎）
    await check_and_unlock_distance_skills(user_id, new_distance)

    # 新しい距離を設定
    await update_player(user_id, 
                  distance=new_distance, 
                  current_floor=floor, 
                  current_stage=stage)

    return new_distance

async def get_previous_distance(user_id):
    """前回の距離を取得（現在の距離を返す）"""
    player = await get_player(user_id)
    return player.get("distance", 0) if player else 0

async def get_milestone_flag(user_id, flag_name):
    """マイルストーンフラグを取得"""
    player = await get_player(user_id)
    if player:
        flags = player.get("milestone_flags", {})
        return flags.get(flag_name, False)
    return False

async def set_milestone_flag(user_id, flag_name, value=True):
    """マイルストーンフラグを設定"""
    player = await get_player(user_id)
    if player:
        flags = player.get("milestone_flags", {})
        flags[flag_name] = value
        await update_player(user_id, milestone_flags=flags)

async def is_boss_defeated(user_id, boss_id):
    """ボスが倒されたかチェック"""
    player = await get_player(user_id)
    if player:
        boss_flags = player.get("boss_defeated_flags", {})
        return boss_flags.get(str(boss_id), False)
    return False

async def set_boss_defeated(user_id, boss_id):
    """ボス撃破フラグを設定"""
    player = await get_player(user_id)
    if player:
        boss_flags = player.get("boss_defeated_flags", {})
        boss_flags[str(boss_id)] = True
        await update_player(user_id, boss_defeated_flags=boss_flags)

async def get_tutorial_flag(user_id, tutorial_name):
    """チュートリアルフラグを取得"""
    player = await get_player(user_id)
    if player:
        flags = player.get("tutorial_flags", {})
        return flags.get(tutorial_name, False)
    return False

async def set_tutorial_flag(user_id, tutorial_name):
    """チュートリアルフラグを設定"""
    player = await get_player(user_id)
    if player:
        flags = player.get("tutorial_flags", {})
        flags[tutorial_name] = True
        await update_player(user_id, tutorial_flags=flags)

async def add_secret_weapon(user_id, weapon_id):
    """シークレット武器を追加"""
    player = await get_player(user_id)
    if player:
        secret_weapons = player.get("secret_weapon_ids", [])
        if weapon_id not in secret_weapons:
            secret_weapons.append(weapon_id)
            await update_player(user_id, secret_weapon_ids=secret_weapons)
            return True
    return False

async def get_loop_count(user_id):
    """周回数を取得（互換性のため残す。death_countを返す）"""
    return await get_death_count(user_id)

async def get_death_count(user_id):
    """死亡回数を取得"""
    player = await get_player(user_id)
    return player.get("death_count", 0) if player else 0

async def equip_weapon(user_id, weapon_name):
    """武器を装備"""
    await update_player(user_id, equipped_weapon=weapon_name)

async def equip_armor(user_id, armor_name):
    """防具を装備"""
    await update_player(user_id, equipped_armor=armor_name)

async def get_equipped_items(user_id):
    """装備中のアイテムを取得"""
    player = await get_player(user_id)
    if player:
        return {
            "weapon": player.get("equipped_weapon"),
            "armor": player.get("equipped_armor")
        }
    return {"weapon": None, "armor": None}

async def add_upgrade_points(user_id, points):
    """アップグレードポイントを追加"""
    player = await get_player(user_id)
    if player:
        current_points = player.get("upgrade_points", 0)
        await update_player(user_id, upgrade_points=current_points + points)

async def spend_upgrade_points(user_id, points):
    """アップグレードポイントを消費"""
    player = await get_player(user_id)
    if player:
        current_points = player.get("upgrade_points", 0)
        if current_points >= points:
            await update_player(user_id, upgrade_points=current_points - points)
            return True
    return False

async def increment_death_count(user_id):
    """死亡回数を増やす"""
    player = await get_player(user_id)
    if player:
        death_count = player.get("death_count", 0)
        await update_player(user_id, death_count=death_count + 1)
        return death_count + 1
    return 0

async def get_upgrade_levels(user_id):
    """アップグレードレベルを取得"""
    player = await get_player(user_id)
    if player:
        return {
            "initial_hp": player.get("initial_hp_upgrade", 0),
            "initial_mp": player.get("initial_mp_upgrade", 0),
            "coin_gain": player.get("coin_gain_upgrade", 0),
            "atk": player.get("atk_upgrade", 0),
            "def_upgrade": player.get("def_upgrade", 0)
        }
    return {"initial_hp": 0, "initial_mp": 0, "coin_gain": 0, "atk": 0, "def_upgrade": 0}

async def get_upgrade_cost(upgrade_type, user_id):
    """アップグレードタイプと現在のレベルに応じたコストを計算
    
    繰り返し購入でコストが上昇する仕組み
    コスト = 基本コスト + (現在レベル × 上昇値)
    """
    upgrades = await get_upgrade_levels(user_id)
    
    if upgrade_type == 1:  # HP
        current_level = upgrades["initial_hp"]
        return 2 + (current_level * 1)
    elif upgrade_type == 2:  # MP
        current_level = upgrades["initial_mp"]
        return 2 + (current_level * 1)
    elif upgrade_type == 3:  # コイン取得量
        current_level = upgrades["coin_gain"]
        return 3 + (current_level * 2)
    elif upgrade_type == 4:  # ATK
        current_level = upgrades["atk"]
        return 3 + (current_level * 2)
    elif upgrade_type == 5:  # DEF
        current_level = upgrades["def_upgrade"]
        return 5 + (current_level * 5)
    
    return 1  # デフォルト

async def upgrade_initial_hp(user_id):
    """初期HP最大量をアップグレード"""
    player = await get_player(user_id)
    if player:
        current_level = player.get("initial_hp_upgrade", 0)
        new_max_hp = player.get("max_hp", 50) + 5
        new_hp = player.get("hp", 50) + 5
        await update_player(user_id, initial_hp_upgrade=current_level + 1, max_hp=new_max_hp)
        return True
    return False

async def upgrade_initial_mp(user_id):
    """初期MP最大量をアップグレード"""
    player = await get_player(user_id)
    if player:
        current_level = player.get("initial_mp_upgrade", 0)
        new_max_mp = player.get("max_mp", 20) + 5
        new_mp = player.get("mp", 20) + 5
        await update_player(user_id, initial_mp_upgrade=current_level + 1, max_mp=new_max_mp)
        return True
    return False

async def upgrade_coin_gain(user_id):
    """コイン取得量をアップグレード"""
    player = await get_player(user_id)
    if player:
        current_level = player.get("coin_gain_upgrade", 0)
        new_multiplier = player.get("coin_multiplier", 1.0) + 0.1
        await update_player(user_id, coin_gain_upgrade=current_level + 1, coin_multiplier=new_multiplier)
        return True
    return False

async def upgrade_atk(user_id):
    """攻撃力初期値をアップグレード（3PT で +1ATK）"""
    player = await get_player(user_id)
    if player:
        current_level = player.get("atk_upgrade", 0)
        new_atk = player.get("atk", 5) + 1
        await update_player(user_id, atk_upgrade=current_level + 1, atk=new_atk)
        return True
    return False

async def upgrade_def(user_id):
    """防御力初期値をアップグレード（5PT で +1DEF）"""
    player = await get_player(user_id)
    if player:
        current_level = player.get("def_upgrade", 0)
        new_def = player.get("def", 2) + 1
        update_data = {"def_upgrade": current_level + 1, "def": new_def}
        await update_player(user_id, **update_data)
        return True
    return False

async def handle_player_death(user_id, killed_by_enemy_name=None, enemy_type="normal"):
    """プレイヤー死亡時の処理（ポイント付与、死亡回数増加、全アイテム消失、フラグクリア）"""
    player = await get_player(user_id)
    if player:
        distance = player.get("distance", 0)
        floor = distance // 100
        stage = distance // 1000
        points = max(1, floor // 2)

        await add_upgrade_points(user_id, points)
        death_count = await increment_death_count(user_id)

        # 🆕 死亡履歴を記録
        if killed_by_enemy_name:
            await record_death_history(user_id, killed_by_enemy_name, distance, floor, stage, enemy_type)

        # 死亡時リセット：全アイテム消失、装備解除、ゴールドリセット、フラグクリア、ゲームクリア状態リセット
        await update_player(user_id, 
                      hp=player.get("max_hp", 50),
                      mp=player.get("max_mp", 50),
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

async def handle_boss_clear(user_id):
    """ラスボス撃破時の処理（クリア報酬、クリア状態フラグ設定、ゴールド倉庫自動送金）

    注意: この関数ではデータリセットを行わない。
    リセットは!resetコマンドでユーザーが手動で行う。
    """
    player = await get_player(user_id)
    if player:
        # クリア報酬（固定50ポイント）
        await add_upgrade_points(user_id, 50)
        
        # 現在のゴールドを倉庫ゴールドに自動送金
        current_gold = player.get("gold", 0)
        if current_gold > 0:
            await add_vault_gold(user_id, current_gold)
            logger.info(f"Auto-transferred {current_gold} gold to vault for user {user_id} upon boss clear")

        # クリア状態フラグを設定（リセットは行わない）
        await update_player(user_id, game_cleared=True)

        return {
            "points_gained": 50,
            "gold_saved": current_gold
        }
    return None

async def get_story_flag(user_id, story_id):
    """ストーリー既読フラグを取得"""
    player = await get_player(user_id)
    if player:
        flags = player.get("story_flags", {})
        return flags.get(story_id, False)
    return False

async def set_story_flag(user_id, story_id):
    """ストーリー既読フラグを設定"""
    player = await get_player(user_id)
    if player:
        flags = player.get("story_flags", {})
        flags[story_id] = True
        await update_player(user_id, story_flags=flags)

async def clear_story_flags(user_id):
    """ストーリーフラグをクリア（周回リセット用）"""
    player = await get_player(user_id)
    if player:
        await update_player(user_id, story_flags={})

async def get_global_weapon_count(weapon_id):
    """シークレット武器のグローバル排出数を取得"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/secret_weapons_global"
    params = {"weapon_id": f"eq.{weapon_id}", "select": "total_dropped"}
    
    try:
        response = await client.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            return data[0].get("total_dropped", 0)
        return 0
    except:
        return 0

async def increment_global_weapon_count(weapon_id):
    """シークレット武器のグローバル排出数を増やす"""
    client = await get_client()
    try:
        current_count = await get_global_weapon_count(weapon_id)

        if current_count == 0:
            url = f"{config.SUPABASE_URL}/rest/v1/secret_weapons_global"
            weapon_data = {
                "weapon_id": weapon_id,
                "total_dropped": 1,
                "max_limit": 10
            }
            response = await client.post(url, headers=_get_headers(), json=weapon_data)
            response.raise_for_status()
        else:
            url = f"{config.SUPABASE_URL}/rest/v1/secret_weapons_global"
            params = {"weapon_id": f"eq.{weapon_id}"}
            update_data = {"total_dropped": current_count + 1}
            response = await client.patch(url, headers=_get_headers(), params=params, json=update_data)
            response.raise_for_status()

        return True
    except Exception as e:
        print(f"Error incrementing weapon count: {e}")
        return False

async def get_available_secret_weapons():
    """排出可能なシークレット武器リストを取得（上限10個未満のもの）"""
    import game
    available_weapons = []

    for weapon in game.SECRET_WEAPONS:
        weapon_id = weapon["id"]
        count = await get_global_weapon_count(weapon_id)
        if count < 10:
            available_weapons.append(weapon)

    return available_weapons

# ==============================
# EXP / レベルシステム
# ==============================

def get_required_exp(level):
    """レベルアップに必要なEXPを計算"""
    return level * 100

async def add_exp(user_id, amount):
    """EXPを追加してレベルアップ処理"""
    player = await get_player(user_id)
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
        if player:
            new_hp = player.get("hp", 50) + 5
            new_max_hp = player.get("max_hp", 50) + 5
            new_atk = player.get("atk", 5) + 1
            new_def = player.get("def", 2) + 1

            update_data = {
                "level": current_level,
                "hp": new_hp,
                "max_hp": new_max_hp,
                "atk": new_atk,
                "def": new_def
            }
            await update_player(user_id, **update_data)

            level_ups.append({
                "new_level": current_level,
                "hp_gain": 5,
                "atk_gain": 1,
                "def_gain": 1
            })

            player = await get_player(user_id)

    # 残りEXPを更新
    await update_player(user_id, exp=new_exp)

    return {
        "exp_gained": amount,
        "current_exp": new_exp,
        "current_level": current_level,
        "level_ups": level_ups
    }

# ==============================
# MP システム
# ==============================

async def consume_mp(user_id, amount):
    """MPを消費"""
    player = await get_player(user_id)
    if not player:
        return False

    current_mp = player.get("mp", 100)
    if current_mp >= amount:
        new_mp = current_mp - amount
        await update_player(user_id, mp=new_mp)

        # MP=0の場合、行動不能フラグ
        if new_mp == 0:
            await update_player(user_id, mp_stunned=True)

        return True
    return False

async def restore_mp(user_id, amount):
    """MPを回復"""
    player = await get_player(user_id)
    if not player:
        return 0

    current_mp = player.get("mp", 20)
    max_mp = player.get("max_mp", 20)
    new_mp = min(current_mp + amount, max_mp)
    await update_player(user_id, mp=new_mp)

    return new_mp - current_mp

async def set_mp_stunned(user_id, stunned):
    """MP枯渇による行動不能フラグを設定"""
    await update_player(user_id, mp_stunned=stunned)

async def is_mp_stunned(user_id):
    """MP枯渇チェック"""
    player = await get_player(user_id)
    return player.get("mp_stunned", False) if player else False

# ==============================
# スキル システム
# ==============================

async def get_unlocked_skills(user_id):
    """解放済みスキルリストを取得"""
    player = await get_player(user_id)
    if player:
        return player.get("unlocked_skills", ["体当たり"])
    return ["体当たり"]

async def unlock_skill(user_id, skill_id):
    """スキルを解放"""
    player = await get_player(user_id)
    if player:
        unlocked = player.get("unlocked_skills", ["体当たり"])
        if skill_id not in unlocked:
            unlocked.append(skill_id)
            await update_player(user_id, unlocked_skills=unlocked)
            return True
    return False

async def check_and_unlock_distance_skills(user_id, distance):
    """距離に応じてスキルを自動解放"""
    skill_unlock_map = {
        1000: "小火球",
        2000: "軽傷治癒",
        3000: "強攻撃",
        4000: "ファイアボール",
        5000: "猛攻撃",
        6000: "中治癒",
        7000: "爆炎",
        8000: "完全治癒",
        9000: "神速の一閃",
        10000: "究極魔法"
    }

    for unlock_distance, skill_id in skill_unlock_map.items():
        if distance >= unlock_distance:
            await unlock_skill(user_id, skill_id)

# ==============================
# 倉庫システム (Storage System)
# ==============================

async def add_to_storage(user_id, item_name, item_type):
    """倉庫にアイテムを追加"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/storage"
    
    try:
        storage_data = {
            "user_id": str(user_id),
            "item_name": item_name,
            "item_type": item_type,
            "is_taken": False
        }
        response = await client.post(url, headers=_get_headers(), json=storage_data)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error adding to storage: {e}")
        return False

async def get_storage_items(user_id, include_taken=False):
    """倉庫のアイテムリストを取得"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/storage"
    
    try:
        params = {
            "user_id": f"eq.{str(user_id)}",
            "select": "*",
            "order": "stored_at.desc"
        }
        
        if not include_taken:
            params["is_taken"] = "eq.false"
        
        response = await client.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error getting storage items: {e}")
        return []

async def take_from_storage(user_id, storage_id):
    """倉庫からアイテムを取り出す（is_takenをTrueにする）"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/storage"
    
    try:
        from datetime import datetime
        params = {"id": f"eq.{storage_id}", "user_id": f"eq.{str(user_id)}"}
        update_data = {
            "is_taken": True,
            "taken_at": datetime.now().isoformat()
        }
        response = await client.patch(url, headers=_get_headers(), params=params, json=update_data)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error taking from storage: {e}")
        return False

async def get_storage_item_by_id(storage_id):
    """倉庫アイテムをIDで取得"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/storage"
    params = {"id": f"eq.{storage_id}", "select": "*"}
    
    try:
        response = await client.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        data = response.json()
        return data[0] if data else None
    except Exception as e:
        print(f"Error getting storage item: {e}")
        return None

# ==============================
# ゲームクリア状態管理
# ==============================

async def set_game_cleared(user_id, cleared=True):
    """ゲームクリア状態を設定"""
    await update_player(user_id, game_cleared=cleared)

async def is_game_cleared(user_id):
    """ゲームクリア状態を取得"""
    player = await get_player(user_id)
    return player.get("game_cleared", False) if player else False

async def is_player_banned(user_id):
    """プレイヤーがBANされているかチェック"""
    player = await get_player(user_id)
    if player:
        bot_banned = player.get("is_banned", False)
        return bot_banned
    return False

async def get_ban_status(user_id):
    """BAN状態の詳細を取得"""
    player = await get_player(user_id)
    if player:
        return {
            "bot_banned": player.get("is_banned", False),
            "web_banned": player.get("web_banned", False)
        }
    return {"bot_banned": False, "web_banned": False}

# 死亡履歴システム

async def record_death_history(user_id, enemy_name, distance=0, floor=0, stage=0, enemy_type="normal"):
    """死亡履歴を記録"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/death_history"
    
    try:
        death_data = {
            "user_id": str(user_id),
            "enemy_name": enemy_name,
            "enemy_type": enemy_type,
            "distance": distance,
            "floor": floor,
            "stage": stage
        }
        response = await client.post(url, headers=_get_headers(), json=death_data)
        response.raise_for_status()

        # total_deaths カウントアップ（オプション）
        player = await get_player(user_id)
        if player:
            total_deaths = player.get("total_deaths", 0) + 1
            await update_player(user_id, total_deaths=total_deaths)

        return True
    except Exception as e:
        print(f"Error recording death history: {e}")
        return False

async def get_death_history(user_id, limit=100):
    """死亡履歴を取得（最新limit件）"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/death_history"
    params = {
        "user_id": f"eq.{str(user_id)}",
        "select": "*",
        "order": "died_at.desc",
        "limit": limit
    }
    
    try:
        response = await client.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error getting death history: {e}")
        return []

async def get_death_count_by_enemy(user_id, enemy_name):
    """特定の敵に殺された回数を取得"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/death_history"
    params = {
        "user_id": f"eq.{str(user_id)}",
        "enemy_name": f"eq.{enemy_name}",
        "select": "id"
    }
    headers = _get_headers()
    headers["Prefer"] = "count=exact"
    
    try:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        # Content-Range ヘッダーから総数を取得
        content_range = response.headers.get("Content-Range", "")
        if content_range and "/" in content_range:
            count_str = content_range.split("/")[1]
            return int(count_str) if count_str != "*" else 0
        return 0
    except Exception as e:
        print(f"Error getting death count: {e}")
        return 0

async def get_death_stats(user_id):
    """死亡統計を取得（敵ごとの死亡回数）"""
    try:
        history = await get_death_history(user_id, limit=1000)
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

async def get_recent_deaths(user_id, limit=5):
    """直近N回の死亡履歴を取得"""
    return await get_death_history(user_id, limit=limit)

async def check_death_pattern(user_id, pattern):
    """
    特定の死亡パターンをチェック
    pattern: ["敵A", "敵B", "敵C"] のようなリスト（順番重要）
    """
    try:
        recent = await get_recent_deaths(user_id, limit=len(pattern))
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

async def add_title(user_id, title_id, title_name):
    """称号を追加（重複は無視）"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/player_titles"
    
    try:
        title_data = {
            "user_id": str(user_id),
            "title_id": title_id,
            "title_name": title_name
        }
        response = await client.post(url, headers=_get_headers(), json=title_data)
        response.raise_for_status()
        return True
    except Exception as e:
        # UNIQUE制約違反（既に持っている）は無視
        if "duplicate key" in str(e).lower() or "409" in str(e):
            return False
        print(f"Error adding title: {e}")
        return False

async def get_player_titles(user_id):
    """プレイヤーが持っている称号一覧を取得"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/player_titles"
    params = {
        "user_id": f"eq.{str(user_id)}",
        "select": "*",
        "order": "unlocked_at.desc"
    }
    
    try:
        response = await client.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error getting titles: {e}")
        return []

async def has_title(user_id, title_id):
    """特定の称号を持っているかチェック"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/player_titles"
    params = {
        "user_id": f"eq.{str(user_id)}",
        "title_id": f"eq.{title_id}",
        "select": "id"
    }
    
    try:
        response = await client.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        data = response.json()
        return len(data) > 0
    except Exception as e:
        print(f"Error checking title: {e}")
        return False

async def set_active_title(user_id, title_id):
    """装備中の称号を設定"""
    # 称号を持っているか確認
    if not await has_title(user_id, title_id):
        return False

    await update_player(user_id, active_title_id=title_id)
    return True

async def get_active_title(user_id):
    """現在装備中の称号を取得"""
    player = await get_player(user_id)
    if player:
        title_id = player.get("active_title_id")
        if title_id:
            # 称号名を取得
            titles = await get_player_titles(user_id)
            for title in titles:
                if title.get("title_id") == title_id:
                    return title.get("title_name")
    return None

async def unequip_title(user_id):
    """称号を外す"""
    await update_player(user_id, active_title_id=None)
    return True


_original_update_player = globals().get("update_player")
if _original_update_player and not getattr(_original_update_player, "_is_wrapped_logger", False):

    # スレッドローカルで再入制御
    _wrapper_state = threading.local()

    def update_player(*args, **kwargs):  # type: ignore[no-redef]
        # 抽出できれば user_id をログに載せる
        user_id = None
        if args:
            user_id = args[0]
        elif "user_id" in kwargs:
            user_id = kwargs.get("user_id")

        # すでに wrapper 内なら内部の呼び出しはログせず直接実行
        if getattr(_wrapper_state, "in_update_player", False):
            # 直接元の関数を呼ぶ（ログは出さない）
            return _original_update_player(*args, **kwargs)

        # ログ出力して元関数を呼ぶ
        _wrapper_state.in_update_player = True
        try:
            # 呼び出し元の簡易スタックを取得
            try:
                stack = inspect.stack()[1:6]  # 少数のフレームを取る
                callers = " | ".join(f"{s.filename.split('/')[-1]}:{s.lineno}" for s in stack)
            except Exception:
                callers = "stack-unavailable"

            logger.debug("db.update_player called user=%s args=%s kwargs=%s callers=%s",
                         user_id, args, kwargs, callers)

            return _original_update_player(*args, **kwargs)
        finally:
            _wrapper_state.in_update_player = False

    # マーカーを付けて二重ラップを防ぐ
    update_player._is_wrapped_logger = True  # type: ignore[attr-defined]

    # 置き換え
    globals()["update_player"] = update_player

else:
    logger.debug("db.update_player wrapper: original_update_player not found or already wrapped.")

# ==============================
# デバッグコマンド用関数
# ==============================

async def get_all_players():
    """全プレイヤーのリストを取得（管理者用）"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/players"
    params = {"select": "*"}
    
    try:
        response = await client.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error getting all players: {e}")
        return []

async def ban_player(user_id):
    """プレイヤーをBAN"""
    await update_player(user_id, is_banned=True)
    logger.warning(f"Player {user_id} has been banned")

async def unban_player(user_id):
    """プレイヤーのBANを解除"""
    await update_player(user_id, is_banned=False)
    logger.info(f"Player {user_id} has been unbanned")

async def is_player_banned(user_id):
    """プレイヤーがBANされているかチェック"""
    player = await get_player(user_id)
    if player:
        return player.get("is_banned", False)
    return False

async def restore_player_snapshot(user_id, snapshot_data: dict):
    """スナップショットからプレイヤーデータを復元"""
    # スナップショットデータから復元する主要フィールド
    restore_fields = {
        "hp": snapshot_data.get("hp"),
        "mp": snapshot_data.get("mp"),
        "distance": snapshot_data.get("distance"),
        "current_floor": snapshot_data.get("current_floor"),
        "current_stage": snapshot_data.get("current_stage"),
        "gold": snapshot_data.get("gold"),
        "exp": snapshot_data.get("exp"),
        "level": snapshot_data.get("level"),
        "inventory": snapshot_data.get("inventory"),
        "equipped_weapon": snapshot_data.get("equipped_weapon"),
        "equipped_armor": snapshot_data.get("equipped_armor"),
    }
    
    # Noneでないフィールドのみを更新
    update_data = {k: v for k, v in restore_fields.items() if v is not None}
    
    if update_data:
        await update_player(user_id, **update_data)
        logger.info(f"Restored snapshot for user {user_id}")
    else:
        logger.warning(f"No valid data to restore for user {user_id}")

# ==============================
# 倉庫ゴールドシステム関数
# ==============================

async def get_or_create_vault_gold(user_id):
    """プレイヤーの倉庫ゴールドデータを取得または作成"""
    from datetime import datetime, timezone
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/player_vault_gold"
    params = {"user_id": f"eq.{str(user_id)}", "select": "*"}
    
    try:
        response = await client.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        data = response.json()
        
        if data and len(data) > 0:
            return data[0]
        else:
            # 新規作成
            vault_data = {
                "user_id": str(user_id),
                "vault_gold": 0,
                "total_deposited": 0,
                "total_withdrawn": 0,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            response = await client.post(url, headers=_get_headers(), json=vault_data)
            response.raise_for_status()
            return response.json()[0] if response.json() else None
    except Exception as e:
        logger.error(f"Error getting/creating vault gold: {e}")
        return None

async def get_vault_gold(user_id):
    """倉庫ゴールドの現在の残高を取得"""
    vault_data = await get_or_create_vault_gold(user_id)
    return vault_data.get("vault_gold", 0) if vault_data else 0

async def add_vault_gold(user_id, amount):
    """倉庫ゴールドを追加（ラスボス撃破時の自動送金用）"""
    from datetime import datetime, timezone
    client = await get_client()
    
    if amount <= 0:
        return False
    
    vault_data = await get_or_create_vault_gold(user_id)
    if vault_data:
        current_vault = vault_data.get("vault_gold", 0)
        total_deposited = vault_data.get("total_deposited", 0)
        
        new_vault = current_vault + amount
        new_total_deposited = total_deposited + amount
        
        url = f"{config.SUPABASE_URL}/rest/v1/player_vault_gold"
        params = {"user_id": f"eq.{str(user_id)}"}
        
        update_data = {
            "vault_gold": new_vault,
            "total_deposited": new_total_deposited,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        
        try:
            response = await client.patch(url, headers=_get_headers(), params=params, json=update_data)
            response.raise_for_status()
            logger.info(f"Added {amount} gold to vault for user {user_id}. New balance: {new_vault}")
            return True
        except Exception as e:
            logger.error(f"Error adding vault gold: {e}")
            return False
    return False

async def spend_vault_gold(user_id, amount):
    """倉庫ゴールドを消費"""
    from datetime import datetime, timezone
    client = await get_client()
    
    if amount <= 0:
        return False
    
    vault_data = await get_or_create_vault_gold(user_id)
    if vault_data:
        current_vault = vault_data.get("vault_gold", 0)
        
        if current_vault < amount:
            logger.warning(f"Insufficient vault gold for user {user_id}. Required: {amount}, Available: {current_vault}")
            return False
        
        total_withdrawn = vault_data.get("total_withdrawn", 0)
        new_vault = current_vault - amount
        new_total_withdrawn = total_withdrawn + amount
        
        url = f"{config.SUPABASE_URL}/rest/v1/player_vault_gold"
        params = {"user_id": f"eq.{str(user_id)}"}
        
        update_data = {
            "vault_gold": new_vault,
            "total_withdrawn": new_total_withdrawn,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        
        try:
            response = await client.patch(url, headers=_get_headers(), params=params, json=update_data)
            response.raise_for_status()
            logger.info(f"Spent {amount} vault gold for user {user_id}. Remaining balance: {new_vault}")
            return True
        except Exception as e:
            logger.error(f"Error spending vault gold: {e}")
            return False
    return False

# ==============================
# Anti-Cheat System
# ==============================

async def log_command(user_id: int, command: str, success: bool = True, metadata: Dict = None):
    """コマンド実行をログに記録"""
    from datetime import datetime, timezone
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/command_logs"
    
    log_data = {
        "user_id": str(user_id),
        "command": command,
        "success": success,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        response = await client.post(url, headers=_get_headers(), json=log_data)
        response.raise_for_status()
        return True
    except Exception as e:
        # 旧スキーマ互換: command_name が NOT NULL の場合がある
        pg = _extract_postgrest_error(e)
        details = (pg or {}).get("details") if isinstance(pg, dict) else ""
        message = (pg or {}).get("message") if isinstance(pg, dict) else ""
        code = (pg or {}).get("code") if isinstance(pg, dict) else None
        haystack = f"{message} {details}"

        if code == "23502" and "command_name" in haystack:
            legacy_payload = dict(log_data)
            legacy_payload["command_name"] = command
            try:
                response2 = await client.post(url, headers=_get_headers(), json=legacy_payload)
                response2.raise_for_status()
                logger.warning("command_logs: fell back to legacy column command_name")
                return True
            except Exception as e2:
                logger.error(f"Error logging command (legacy retry): {_format_httpx_error(e2)}")
                return False

        logger.error(f"Error logging command: {_format_httpx_error(e)}")
        return False

async def get_recent_command_logs(user_id: int, limit: int = 100) -> List[Dict]:
    """最近のコマンドログを取得"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/command_logs"
    
    try:
        params = {
            "user_id": f"eq.{str(user_id)}",
            "select": "*",
            "order": "timestamp.desc",
            "limit": limit
        }
        response = await client.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        
        # Convert timestamp strings to datetime objects
        from datetime import datetime
        logs = response.json()
        for log in logs:
            if "timestamp" in log and isinstance(log["timestamp"], str):
                log["timestamp"] = datetime.fromisoformat(log["timestamp"].replace('Z', '+00:00'))
        
        return logs
    except Exception as e:
        logger.error(f"Error getting command logs: {e}")
        return []

async def get_total_command_count(user_id: int) -> int:
    """総コマンド実行数を取得"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/command_logs"
    
    try:
        params = {
            "user_id": f"eq.{str(user_id)}",
            "select": "id"
        }
        response = await client.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        return len(response.json())
    except Exception as e:
        logger.error(f"Error getting command count: {e}")
        return 0

async def log_anti_cheat_event(user_id: int, event_type: str, severity: str, score: int, details: Dict = None):
    """アンチチートイベントをログに記録"""
    from datetime import datetime, timezone
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/anti_cheat_logs"
    
    event_data = {
        "user_id": str(user_id),
        "event_type": event_type,
        "severity": severity,
        "anomaly_score": score,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        response = await client.post(url, headers=_get_headers(), json=event_data)
        response.raise_for_status()
        return True
    except Exception as e:
        # 旧スキーマ互換: detection_type/score が NOT NULL の場合がある
        pg = _extract_postgrest_error(e)
        details_text = (pg or {}).get("details") if isinstance(pg, dict) else ""
        message = (pg or {}).get("message") if isinstance(pg, dict) else ""
        code = (pg or {}).get("code") if isinstance(pg, dict) else None
        haystack = f"{message} {details_text}"

        if code == "23502":
            needs_detection_type = "detection_type" in haystack
            needs_score = "score" in haystack
            if needs_detection_type or needs_score:
                legacy_payload = dict(event_data)
                if needs_detection_type:
                    legacy_payload["detection_type"] = event_type
                if needs_score:
                    legacy_payload["score"] = score
                try:
                    response2 = await client.post(url, headers=_get_headers(), json=legacy_payload)
                    response2.raise_for_status()
                    logger.warning("anti_cheat_logs: fell back to legacy columns")
                    return True
                except Exception as e2:
                    logger.error(f"Error logging anti-cheat event (legacy retry): {_format_httpx_error(e2)}")
                    return False

        logger.error(f"Error logging anti-cheat event: {_format_httpx_error(e)}")
        return False

async def get_recent_anti_cheat_logs(user_id: int, limit: int = 10) -> List[Dict]:
    """最近のアンチチートログを取得"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/anti_cheat_logs"
    
    try:
        params = {
            "user_id": f"eq.{str(user_id)}",
            "select": "*",
            "order": "timestamp.desc",
            "limit": limit
        }
        response = await client.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error getting anti-cheat logs: {e}")
        return []

async def update_behavior_stats(user_id: int):
    """ユーザーの行動統計を更新"""
    from datetime import datetime, timezone, timedelta
    client = await get_client()
    
    try:
        player = await get_player(user_id)
        
        if not player:
            return False
        
        # 最近1時間のコマンドログを取得してセッション時間を計算
        recent_logs = await get_recent_command_logs(user_id, limit=1000)
        
        # セッション開始時刻を計算（最後のコマンドから1時間以上空いていたら新セッション）
        now = datetime.now(timezone.utc)
        session_start = None
        
        if recent_logs:
            # 最新のログから古い方へ遡って、1時間以上の空白を探す
            last_timestamp = None
            for log in recent_logs:
                current_time = log["timestamp"]
                if last_timestamp and (last_timestamp - current_time) > timedelta(hours=1):
                    session_start = last_timestamp
                    break
                last_timestamp = current_time
            
            # 空白が見つからなかった場合は一番古いログから
            if not session_start and recent_logs:
                session_start = recent_logs[-1]["timestamp"]
        
        # セッション時間を計算
        if session_start:
            session_duration = now - session_start
            session_hours = session_duration.total_seconds() / 3600
        else:
            session_hours = 0
        
        # 統計データをUPSERT（SELECTが空でも既存行があるケース対策）
        url = f"{config.SUPABASE_URL}/rest/v1/user_behavior_stats"
        
        stats_data = {
            "user_id": str(user_id),
            "total_commands": await get_total_command_count(user_id),
            "current_session_hours": session_hours,
            "unused_upgrade_points": player.get("upgrade_points", 0),
            "has_equipment": bool(player.get("equipped_weapon") or player.get("equipped_armor")),
            "last_active": now.isoformat(),
            "last_updated": now.isoformat()
        }

        headers = _get_headers().copy()
        headers["Prefer"] = "return=representation,resolution=merge-duplicates"
        response = await client.post(
            url,
            headers=headers,
            params={"on_conflict": "user_id"},
            json=stats_data,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Error updating behavior stats: {_format_httpx_error(e)}")
        return False

async def get_user_behavior_stats(user_id: int) -> Optional[Dict]:
    """ユーザーの行動統計を取得"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/user_behavior_stats"
    
    try:
        params = {
            "user_id": f"eq.{str(user_id)}",
            "select": "*"
        }
        response = await client.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        data = response.json()
        return data[0] if data else None
    except Exception as e:
        logger.error(f"Error getting behavior stats: {e}")
        return None

async def ban_player(user_id: int, reason: str = "Violation of Terms"):
    """プレイヤーをBANする"""
    from datetime import datetime, timezone
    
    try:
        await update_player(user_id, is_banned=True, ban_reason=reason)
        
        # BANログを記録
        await log_anti_cheat_event(
            user_id=user_id,
            event_type="banned",
            severity="critical",
            score=100,
            details={"reason": reason, "banned_at": datetime.now(timezone.utc).isoformat()}
        )
        
        logger.warning(f"Banned user {user_id}: {reason}")
        return True
    except Exception as e:
        logger.error(f"Error banning user {user_id}: {e}")
        return False

async def unban_player(user_id: int):
    """プレイヤーのBANを解除"""
    try:
        await update_player(user_id, is_banned=False, ban_reason=None)
        logger.info(f"Unbanned user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error unbanning user {user_id}: {e}")
        return False
