from __future__ import annotations

from db_http import *

async def get_player(user_id):
    """プレイヤーデータを取得"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/players"
    params = {"user_id": f"eq.{str(user_id)}", "select": "*"}

    if config.VERBOSE_DEBUG:
        logger.debug("db.get_player: user_id=%s", user_id)
    try:
        response = await _request_with_retry(
            "GET",
            url,
            headers=_get_headers(),
            params=params,
            op="db.get_player",
            context={"user_id": str(user_id)},
        )
        data = response.json()
        if config.VERBOSE_DEBUG:
            logger.debug("db.get_player: user_id=%s found=%s", user_id, bool(data))
        return data[0] if data else None
    except Exception as e:
        logger.warning("db.get_player failed: user_id=%s err=%s", user_id, _format_httpx_error(e))
        raise

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
    
    if config.VERBOSE_DEBUG:
        logger.debug("db.create_player: user_id=%s", user_id)
    try:
        response = await client.post(url, headers=_get_headers(), json=player_data)
        response.raise_for_status()
        if config.VERBOSE_DEBUG:
            logger.debug("db.create_player: user_id=%s ok", user_id)
        return response.json()
    except Exception as e:
        logger.warning("db.create_player failed: user_id=%s err=%s", user_id, _format_httpx_error(e))
        raise

async def update_player(user_id, **kwargs):
    """プレイヤーデータを更新"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/players"
    params = {"user_id": f"eq.{str(user_id)}"}

    if config.VERBOSE_DEBUG:
        logger.debug("db.update_player: user_id=%s keys=%s", user_id, sorted(kwargs.keys()))
    def _looks_like_missing_column_error(text: str) -> bool:
        # Supabase(PostgREST)はカラム不一致等で400を返すことがある
        t = (text or "").lower()
        return any(s in t for s in ["column", "does not exist", "schema cache", "pgrst"])

    payload = dict(kwargs)

    # Compatibility: if we already know some columns are missing, strip them up-front.
    missing_cols = _get_missing_columns("players")
    if missing_cols:
        for c in list(missing_cols):
            payload.pop(c, None)

    try:
        response = await _request_with_retry(
            "PATCH",
            url,
            headers=_get_headers(),
            params=params,
            json=payload,
            op="db.update_player",
            context={"user_id": str(user_id), "keys": sorted(payload.keys())},
        )
        if config.VERBOSE_DEBUG:
            logger.debug("db.update_player: user_id=%s ok", user_id)
        return response.json()
    except httpx.HTTPStatusError as e:
        # Compatibility: missing columns (old schema). Cache and retry without them.
        try:
            body = e.response.text
        except Exception:
            body = ""

        if e.response is not None and e.response.status_code == 400 and _looks_like_missing_column_error(body):
            # Try to detect which column is missing, then retry without it.
            # Limit retries to avoid infinite loops.
            table = "players"
            for _ in range(3):
                missing = _detect_missing_column_from_body(body)
                if not missing:
                    # If we can't parse the column name, fall back to old behavior for equipped_shield only.
                    if "equipped_shield" in payload:
                        missing = "equipped_shield"
                    else:
                        break

                if missing not in payload:
                    break

                payload.pop(missing, None)
                _get_missing_columns(table).add(missing)
                key = (table, missing)
                if key not in _MISSING_COLUMNS_LOGGED:
                    _MISSING_COLUMNS_LOGGED.add(key)
                    logger.warning(
                        "db.update_player: missing column detected; caching and retrying without it table=%s col=%s user_id=%s",
                        table,
                        missing,
                        user_id,
                    )

                if not payload:
                    # Nothing left to update; treat as no-op.
                    return []

                try:
                    response2 = await _request_with_retry(
                        "PATCH",
                        url,
                        headers=_get_headers(),
                        params=params,
                        json=payload,
                        op="db.update_player.retry_without_missing_column",
                        context={"user_id": str(user_id), "keys": sorted(payload.keys()), "dropped": missing},
                    )
                    return response2.json()
                except httpx.HTTPStatusError as e2:
                    # If another missing column exists, loop again; else rethrow.
                    if e2.response is not None and e2.response.status_code == 400:
                        try:
                            body = e2.response.text
                        except Exception:
                            body = ""
                        if _looks_like_missing_column_error(body):
                            continue
                    raise

        logger.warning("db.update_player failed: user_id=%s err=%s", user_id, _format_httpx_error(e))
        raise
    except Exception as e:
        logger.warning("db.update_player failed: user_id=%s err=%s", user_id, _format_httpx_error(e))
        raise

async def delete_player(user_id):
    """プレイヤーデータを削除（レイドステータスは保持）"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/players"
    params = {"user_id": f"eq.{str(user_id)}"}
    
    if config.VERBOSE_DEBUG:
        logger.debug("db.delete_player: user_id=%s", user_id)
    try:
        response = await client.delete(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        if config.VERBOSE_DEBUG:
            logger.debug("db.delete_player: user_id=%s ok", user_id)
    except Exception as e:
        logger.warning("db.delete_player failed: user_id=%s err=%s", user_id, _format_httpx_error(e))
        raise


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

    if config.VERBOSE_DEBUG:
        logger.debug("db.get_guild_settings: guild_id=%s", guild_id)
    try:
        response = await client.get(url, headers=_get_headers(), params=params)
        if response.status_code >= 400:
            logger.warning("db.get_guild_settings failed: guild_id=%s status=%s body=%r", guild_id, response.status_code, (response.text or "")[:800])
            return None
        data = response.json()
        if config.VERBOSE_DEBUG:
            logger.debug("db.get_guild_settings: guild_id=%s found=%s", guild_id, bool(data))
        return data[0] if data else None
    except Exception as e:
        logger.warning("db.get_guild_settings exception: guild_id=%s err=%s", guild_id, _format_httpx_error(e))
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

    if config.VERBOSE_DEBUG:
        logger.debug("db.set_guild_adventure_parent_channel: guild_id=%s channel_id=%s", guild_id, channel_id)
    try:
        response = await client.post(
            url,
            headers=headers,
            params={"on_conflict": "guild_id"},
            json=payload,
        )
        if response.status_code >= 400:
            logger.warning(
                "db.set_guild_adventure_parent_channel failed: guild_id=%s channel_id=%s status=%s body=%r",
                guild_id,
                channel_id,
                response.status_code,
                (response.text or "")[:800],
            )
            return False
        if config.VERBOSE_DEBUG:
            logger.debug("db.set_guild_adventure_parent_channel: guild_id=%s ok", guild_id)
        return True
    except Exception as e:
        logger.warning("db.set_guild_adventure_parent_channel exception: guild_id=%s err=%s", guild_id, _format_httpx_error(e))
        return False


async def clear_guild_settings(guild_id: int) -> bool:
    """ギルド設定を削除（`!set off` 用）。"""
    client = await get_client()
    url = f"{config.SUPABASE_URL}/rest/v1/guild_settings"
    params = {"guild_id": f"eq.{str(guild_id)}"}
    if config.VERBOSE_DEBUG:
        logger.debug("db.clear_guild_settings: guild_id=%s", guild_id)
    try:
        response = await client.delete(url, headers=_get_headers(), params=params)
        if response.status_code >= 400:
            logger.warning(
                "db.clear_guild_settings failed: guild_id=%s status=%s body=%r",
                guild_id,
                response.status_code,
                (response.text or "")[:800],
            )
            return False
        if config.VERBOSE_DEBUG:
            logger.debug("db.clear_guild_settings: guild_id=%s ok", guild_id)
        return True
    except Exception as e:
        logger.warning("db.clear_guild_settings exception: guild_id=%s err=%s", guild_id, _format_httpx_error(e))
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

async def equip_shield(user_id, shield_name):
    """盾を装備"""
    await update_player(user_id, equipped_shield=shield_name)

async def get_equipped_items(user_id):
    """装備中のアイテムを取得"""
    player = await get_player(user_id)
    if player:
        weapon = player.get("equipped_weapon")
        armor = player.get("equipped_armor")
        shield = player.get("equipped_shield")

        # 互換: 以前は盾が防具枠(equipped_armor)で保存されていた
        if (not shield) and isinstance(armor, str) and "盾" in armor:
            shield = armor
            armor = None
            try:
                await update_player(user_id, equipped_shield=shield, equipped_armor=None)
            except Exception:
                # 取得時の互換は維持しつつ、更新失敗は握りつぶす
                pass

        return {"weapon": weapon, "armor": armor, "shield": shield}
    return {"weapon": None, "armor": None, "shield": None}

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

        # 死亡時リセット：基本は全アイテム消失。
        # ただしストーリー要件により、特定アイテムは死亡で消えない（例: 魔法のランタン）。
        persistent_items_on_death = {"魔法のランタン"}
        current_inventory = player.get("inventory", []) if isinstance(player.get("inventory", []), list) else []
        preserved_inventory = [i for i in current_inventory if i in persistent_items_on_death]

        # 死亡時リセット：装備解除、ゴールドリセット、ゲームクリア状態リセット
        # 重要: ストーリー既読フラグは死亡でリセットしない。
        current_story_flags = player.get("story_flags", {}) if isinstance(player.get("story_flags", {}), dict) else {}
        await update_player(user_id, 
                      hp=player.get("max_hp", 50),
                      mp=player.get("max_mp", 50),
                      distance=0, 
                      current_floor=0, 
                      current_stage=0,
                  inventory=preserved_inventory,
                      equipped_weapon=None,
                      equipped_armor=None,
                      equipped_shield=None,
                      gold=0,
                      story_flags=current_story_flags,
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

async def set_story_flag_key(user_id, key: str, value: bool = True):
    """story_flags に任意キーを保存（チュートリアル等の進行管理用）。"""
    if not key:
        return
    player = await get_player(user_id)
    if player:
        flags = player.get("story_flags", {})
        if not isinstance(flags, dict):
            flags = {}
        flags[str(key)] = bool(value)
        await update_player(user_id, story_flags=flags)

async def clear_story_flags(user_id):
    """ストーリーフラグをクリア"""
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
        logger.exception("Error incrementing weapon count: %s", e)
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
