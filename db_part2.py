from __future__ import annotations

from db_part1 import *  # re-export shared helpers
from db_part1 import _extract_postgrest_error, _format_httpx_error, _get_headers

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
        logger.exception("Error adding to storage: %s", e)
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
        logger.exception("Error getting storage items: %s", e)
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
        logger.exception("Error taking from storage: %s", e)
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
        logger.exception("Error getting storage item: %s", e)
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
        logger.exception("Error recording death history: %s", e)
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
        logger.exception("Error getting death history: %s", e)
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
        logger.exception("Error getting death count: %s", e)
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
        logger.exception("Error getting death stats: %s", e)
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
        logger.exception("Error checking death pattern: %s", e)
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
        logger.exception("Error adding title: %s", e)
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
        logger.exception("Error getting titles: %s", e)
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
        logger.exception("Error checking title: %s", e)
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
if config.VERBOSE_DEBUG and _original_update_player and not getattr(_original_update_player, "_is_wrapped_logger", False):

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

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "db.update_player called user=%s args=%s kwargs=%s callers=%s",
                    user_id,
                    args,
                    kwargs,
                    callers,
                )

            return _original_update_player(*args, **kwargs)
        finally:
            _wrapper_state.in_update_player = False

    # マーカーを付けて二重ラップを防ぐ
    update_player._is_wrapped_logger = True  # type: ignore[attr-defined]

    # 置き換え
    globals()["update_player"] = update_player

else:
    if config.VERBOSE_DEBUG:
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
        "equipped_shield": snapshot_data.get("equipped_shield"),
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

    global _COMMAND_LOGS_SCHEMA_MODE
    
    log_data = {
        "user_id": str(user_id),
        "command": command,
        "success": success,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # legacy (command_name NOT NULL) の場合は最初から合わせる
    if _COMMAND_LOGS_SCHEMA_MODE == "legacy":
        payload = dict(log_data)
        payload["command_name"] = command
    else:
        payload = log_data

    try:
        response = await client.post(url, headers=_get_headers(), json=payload)
        response.raise_for_status()
        if _COMMAND_LOGS_SCHEMA_MODE is None:
            _COMMAND_LOGS_SCHEMA_MODE = "new"
        return True
    except Exception as e:
        # 旧スキーマ互換: command_name が NOT NULL の場合がある
        pg = _extract_postgrest_error(e)
        details = (pg or {}).get("details") if isinstance(pg, dict) else ""
        message = (pg or {}).get("message") if isinstance(pg, dict) else ""
        code = (pg or {}).get("code") if isinstance(pg, dict) else None
        haystack = f"{message} {details}"

        if code == "23502" and "command_name" in haystack:
            _COMMAND_LOGS_SCHEMA_MODE = "legacy"
            legacy_payload = dict(log_data)
            legacy_payload["command_name"] = command
            try:
                response2 = await client.post(url, headers=_get_headers(), json=legacy_payload)
                response2.raise_for_status()
                if config.VERBOSE_DEBUG:
                    logger.debug("command_logs: using legacy schema (command_name)")
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
