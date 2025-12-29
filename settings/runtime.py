"""Runtime settings (safe to import).

このモジュールは SUPABASE_URL/SUPABASE_KEY のような必須環境変数に依存しないため、
どのタイミングでも安全に import できます。

ハードコードされがちな Discord ID / チャンネルID / 管理者ID / UIタイムアウト などをここに集約します。
"""

from __future__ import annotations

import os
from typing import Iterable, List, Optional


def _safe_int_env(name: str, default: Optional[int] = None) -> Optional[int]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _safe_int_list_env(name: str, default: Iterable[int]) -> List[int]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return list(default)

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    values: List[int] = []
    for part in parts:
        try:
            values.append(int(part))
        except Exception:
            continue

    return values or list(default)


# -------------------------
# Discord IDs / Channels
# -------------------------

# 通知チャンネル（死亡/ボス撃破などのログ出力）
NOTIFY_CHANNEL_ID: Optional[int] = _safe_int_env("NOTIFY_CHANNEL_ID", 1424712515396305007)

# admin_notifications.py が使う通知チャンネル
ADMIN_NOTIFICATION_CHANNEL_ID: Optional[int] = _safe_int_env(
    "ADMIN_NOTIFICATION_CHANNEL_ID",
    1423275896445603953,
)

# debug/admin系の許可ユーザー
DEBUG_ADMIN_IDS: List[int] = _safe_int_list_env(
    "DEBUG_ADMIN_IDS",
    default=[1301416493401243694, 785051117323026463],
)

# main.py などで使う開発者ID（文字列で比較している箇所があるため str も保持）
DEVELOPER_ID_STR: str = (os.getenv("DEVELOPER_ID") or "1301416493401243694").strip()
DEVELOPER_ID: Optional[int] = _safe_int_env("DEVELOPER_ID", None)


# -------------------------
# UI / View settings
# -------------------------
# すべて挙動互換のため、現状の数値をそのまま定数化。

VIEW_TIMEOUT_TREASURE: int = int(os.getenv("VIEW_TIMEOUT_TREASURE") or 30)
VIEW_TIMEOUT_SHORT: int = int(os.getenv("VIEW_TIMEOUT_SHORT") or 60)
VIEW_TIMEOUT_MEDIUM: int = int(os.getenv("VIEW_TIMEOUT_MEDIUM") or 120)
VIEW_TIMEOUT_LONG: int = int(os.getenv("VIEW_TIMEOUT_LONG") or 300)
VIEW_TIMEOUT_TUTORIAL: int = int(os.getenv("VIEW_TIMEOUT_TUTORIAL") or 600)

# Discord select / option limits
SELECT_MAX_OPTIONS: int = int(os.getenv("SELECT_MAX_OPTIONS") or 25)
SELECT_MAX_POTION_OPTIONS: int = int(os.getenv("SELECT_MAX_POTION_OPTIONS") or 15)

# 表示用の文字数トリム（Embed/Select description）
DESC_TRIM_SHORT: int = int(os.getenv("DESC_TRIM_SHORT") or 80)
DESC_TRIM_LONG: int = int(os.getenv("DESC_TRIM_LONG") or 100)
