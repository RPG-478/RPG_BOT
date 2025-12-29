import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from urllib.parse import urlparse

# ローカル開発用: `.env` があれば読み込む（デプロイ環境では通常 `.env` を置かない想定）
# 1) このファイルと同じディレクトリの `.env`
# 2) それが無ければ、cwd から親ディレクトリを辿って `.env` を探索
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=str(env_path), override=False)
else:
    found = find_dotenv(usecwd=True)
    if found:
        load_dotenv(dotenv_path=found, override=False)

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip()
SUPABASE_KEY = (os.getenv("SUPABASE_KEY") or "").strip()

# -------------------------
# 戦闘バランス（ATK/DEF計算モデル）
# -------------------------
# legacy: 現行の「差分（raw - def）」
# lol:   LoL系の「def=Armorとして被ダメ倍率」(damage / (1 + armor/100))
# poe:   PoE系の「ヒットの大きさ依存」(damage * 5*damage / (armor + 5*damage))
DAMAGE_MODEL = (os.getenv("DAMAGE_MODEL") or "legacy").strip().lower()

def _safe_float_env(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except Exception:
        return default

# 数値スケーリング（現行のステ値が小さいため、LoL/PoE式に合わせて倍率調整できるようにする）
ATTACK_SCALE = _safe_float_env("ATTACK_SCALE", 1.0)
DEFENSE_SCALE = _safe_float_env("DEFENSE_SCALE", 1.0)

# PoE式で使う係数（標準は 5.0）
POE_ARMOUR_FACTOR = _safe_float_env("POE_ARMOUR_FACTOR", 5.0)

if SUPABASE_URL and not SUPABASE_URL.startswith(("http://", "https://")):
    # 例: your-project.supabase.co を https://your-project.supabase.co に正規化
    SUPABASE_URL = "https://" + SUPABASE_URL.lstrip("/")

def _looks_like_jwt(value: str) -> bool:
    # JWTっぽい: "eyJ" で始まり、ドット区切りが2つ以上
    return value.startswith("eyJ") and value.count(".") >= 2

if SUPABASE_KEY and (" " in SUPABASE_KEY or "\t" in SUPABASE_KEY or "\n" in SUPABASE_KEY):
    raise ValueError("❌ SUPABASE_KEY に空白/改行が含まれています。`.env` の値を1行にして下さい")

if _looks_like_jwt(SUPABASE_KEY) and len(SUPABASE_KEY) < 80:
    raise ValueError(
        "❌ SUPABASE_KEY が短すぎます（途中で切れている可能性）。`.env` で改行されていないか確認してください\n"
        "python-dotenv の 'could not parse statement' 警告が出ている場合、KEYが複数行に割れていることが多いです"
    )

if " " in SUPABASE_URL or "\t" in SUPABASE_URL or "\n" in SUPABASE_URL:
    raise ValueError("❌ SUPABASE_URL に空白/改行が含まれています。`.env` の値を確認してください")

if SUPABASE_URL and _looks_like_jwt(SUPABASE_URL):
    raise ValueError(
        "❌ SUPABASE_URL がURLではなくKEY(JWT)っぽい値です。SUPABASE_URL と SUPABASE_KEY を入れ替えていませんか？\n"
        "例) SUPABASE_URL=https://xxxx.supabase.co\n"
        "    SUPABASE_KEY=eyJ..."
    )

if SUPABASE_KEY.startswith(("http://", "https://")):
    raise ValueError(
        "❌ SUPABASE_KEY がURLっぽい値です。SUPABASE_URL と SUPABASE_KEY を入れ替えていませんか？\n"
        "例) SUPABASE_URL=https://xxxx.supabase.co\n"
        "    SUPABASE_KEY=eyJ..."
    )

if SUPABASE_URL:
    parsed = urlparse(SUPABASE_URL)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"❌ SUPABASE_URL の形式が不正です: {SUPABASE_URL!r}")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError(
        "❌ 環境変数 SUPABASE_URL と SUPABASE_KEY を設定してください\n"
        "例) SUPABASE_URL=https://xxxx.supabase.co\n"
        "    SUPABASE_KEY=xxxxxxxx"
    )
