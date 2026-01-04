from __future__ import annotations

import asyncio
import inspect
import json
import logging
import random
import re
import threading
from typing import Any, Callable, Dict, List, Optional

import httpx

import config

logger = logging.getLogger("rpgbot")

__all__ = [
    "httpx",
    "config",
    "logger",
    "_COMMAND_LOGS_SCHEMA_MODE",
    "_MISSING_COLUMNS_BY_TABLE",
    "_MISSING_COLUMNS_LOGGED",
    "_get_timeout",
    "_retry_settings",
    "_compute_backoff",
    "_classify_http_error",
    "_should_retry",
    "_request_with_retry",
    "_get_headers",
    "_format_httpx_error",
    "_get_missing_columns",
    "_detect_missing_column_from_body",
    "_extract_postgrest_error",
    "get_client",
    "close_client",
]

# command_logs のスキーマ差分を一度検出したらキャッシュして無駄な失敗/警告を出さない
# None: 未判定 / "new": command でOK / "legacy": command_name が必須
_COMMAND_LOGS_SCHEMA_MODE: Optional[str] = None

# Missing-column compatibility cache (table -> set(columns))
_MISSING_COLUMNS_BY_TABLE: dict[str, set[str]] = {}
_MISSING_COLUMNS_LOGGED: set[tuple[str, str]] = set()

_http_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()


def _get_timeout() -> float:
    try:
        return float(getattr(config, "SUPABASE_HTTP_TIMEOUT", 30.0))
    except Exception:
        return 30.0


def _retry_settings() -> tuple[int, float, float]:
    """Returns (max_attempts, base_delay, max_delay) with safe defaults."""
    try:
        max_attempts = int(getattr(config, "SUPABASE_RETRY_MAX_ATTEMPTS", 3))
    except Exception:
        max_attempts = 3
    try:
        base_delay = float(getattr(config, "SUPABASE_RETRY_BASE_DELAY", 0.5))
    except Exception:
        base_delay = 0.5
    try:
        max_delay = float(getattr(config, "SUPABASE_RETRY_MAX_DELAY", 3.0))
    except Exception:
        max_delay = 3.0

    max_attempts = max(1, min(10, max_attempts))
    base_delay = max(0.05, base_delay)
    max_delay = max(0.1, max_delay)
    return max_attempts, base_delay, max_delay


def _compute_backoff(attempt: int, base_delay: float, max_delay: float) -> float:
    # attempt: 1..N (retry attempt count)
    delay = base_delay * (2 ** max(0, attempt - 1))
    delay = min(delay, max_delay)
    jitter = delay * random.uniform(0.0, 0.2)
    return min(max_delay, delay + jitter)


def _classify_http_error(exc: Exception) -> str:
    if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout)):
        return "timeout"
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
        return "network"
    if isinstance(exc, httpx.HTTPStatusError):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 429:
            return "rate_limited"
        if status in (401, 403):
            return "permission"
        if status and 500 <= int(status) <= 599:
            return "server_error"
        data = _extract_postgrest_error(exc)
        msg = (str(data.get("message")) if isinstance(data, dict) else "").lower()
        details = (str(data.get("details")) if isinstance(data, dict) else "").lower()
        combined = (msg + " " + details).strip()
        if any(s in combined for s in ["does not exist", "column", "schema cache"]):
            return "schema_mismatch"
        if status == 400:
            return "invalid_input"
        return "http_error"
    return "other"


def _should_retry(exc: Exception) -> bool:
    if isinstance(
        exc,
        (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.PoolTimeout,
            httpx.ConnectError,
            httpx.NetworkError,
        ),
    ):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
        if status == 429:
            return True
        if status and 500 <= int(status) <= 599:
            return True
        return False
    return False


async def _request_with_retry(
    method: str,
    url: str,
    *,
    headers: Dict[str, str],
    params: Optional[dict] = None,
    json: Any = None,
    op: str = "db.request",
    context: Optional[dict] = None,
) -> httpx.Response:
    """Conservative retry wrapper for Supabase REST calls.

    Retries only on: 429 / 5xx / network & timeout errors.
    For 4xx (except 429), no retry.
    """

    client = await get_client()
    max_attempts, base_delay, max_delay = _retry_settings()
    ctx = context or {}

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = await client.request(method, url, headers=headers, params=params, json=json)
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_exc = e
            category = _classify_http_error(e)
            retryable = _should_retry(e)

            # Keep logs useful but not too noisy: warn on first + last attempt, debug otherwise.
            level = logging.WARNING if (attempt == 1 or attempt == max_attempts) else logging.DEBUG
            logger.log(
                level,
                "%s failed attempt=%s/%s category=%s ctx=%s err=%s",
                op,
                attempt,
                max_attempts,
                category,
                ctx,
                _format_httpx_error(e),
            )

            if not retryable or attempt >= max_attempts:
                break
            await asyncio.sleep(_compute_backoff(attempt, base_delay, max_delay))

    assert last_exc is not None
    raise last_exc


def _get_headers() -> Dict[str, str]:
    """Supabase REST API用のヘッダーを取得"""
    return {
        "apikey": config.SUPABASE_KEY or "",
        "Authorization": f"Bearer {config.SUPABASE_KEY or ''}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",  # INSERT/UPDATEでデータを返す
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


def _get_missing_columns(table: str) -> set[str]:
    s = _MISSING_COLUMNS_BY_TABLE.get(table)
    if s is None:
        s = set()
        _MISSING_COLUMNS_BY_TABLE[table] = s
    return s


def _detect_missing_column_from_body(body: str) -> Optional[str]:
    """Try to detect missing column name from PostgREST error body."""
    text = (body or "").strip()
    if not text:
        return None
    # Common patterns:
    # - column "equipped_shield" of relation "players" does not exist
    # - Could not find the 'equipped_shield' column of 'players'
    patterns = [
        r'column\s+"(?P<col>[a-zA-Z0-9_]+)"\s+of\s+relation\s+"[a-zA-Z0-9_]+"\s+does\s+not\s+exist',
        r"could\s+not\s+find\s+the\s+'(?P<col>[a-zA-Z0-9_]+)'\s+column",
        r"column\s+(?P<col>[a-zA-Z0-9_]+)\s+does\s+not\s+exist",
    ]
    lower = text.lower()
    for pat in patterns:
        m = re.search(pat, lower, flags=re.IGNORECASE)
        if m:
            col = m.groupdict().get("col")
            if col:
                return str(col)
    return None


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
                _http_client = httpx.AsyncClient(timeout=_get_timeout())
                logger.info("✅ HTTPクライアントを初期化しました")

    return _http_client


async def close_client():
    """HTTPクライアントをクローズ（Bot終了時に呼び出し）"""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.info("✅ HTTPクライアントをクローズしました")
