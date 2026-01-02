import discord
from discord.ui import View, button
import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("rpgbot")


_EXTERNAL_STORIES_CACHE: Optional[dict[str, Any]] = None


def _load_external_stories() -> dict[str, Any]:
    """外部JSONからストーリーを読み込む。

    - `stories.json` (プロジェクトルート/このファイルと同階層) をサポート
    - `stories/*.json` もあればマージ
    """
    global _EXTERNAL_STORIES_CACHE
    if _EXTERNAL_STORIES_CACHE is not None:
        return _EXTERNAL_STORIES_CACHE

    merged: dict[str, Any] = {}
    base_dir = Path(__file__).resolve().parent

    def load_one(path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("⚠️ ストーリーJSONの読み込みに失敗: %s (%s)", path, e, exc_info=True)
            return

        stories = data.get("stories") if isinstance(data, dict) else None
        if not isinstance(stories, dict):
            logger.warning("⚠️ ストーリーJSON形式が不正: %s（トップレベルに 'stories' dict が必要）", path)
            return

        for story_id, story_def in stories.items():
            if isinstance(story_id, str) and isinstance(story_def, dict):
                merged[story_id] = story_def

    # 1) stories.json
    top = base_dir / "stories.json"
    if top.exists():
        load_one(top)

    # 2) stories/*.json
    stories_dir = base_dir / "stories"
    if stories_dir.exists() and stories_dir.is_dir():
        for p in sorted(stories_dir.glob("*.json")):
            load_one(p)

    _EXTERNAL_STORIES_CACHE = merged
    return merged


def _normalize_story_definition(raw: dict[str, Any]) -> dict[str, Any]:
    """外部JSON/内部辞書のストーリー定義を共通フォーマットに正規化する。"""
    title = str(raw.get("title") or "不明なストーリー")
    start_node = str(raw.get("start_node") or "start")

    nodes = raw.get("nodes")
    if isinstance(nodes, dict) and nodes:
        # nodes形式
        normalized_nodes: dict[str, Any] = {}
        for node_id, node_def in nodes.items():
            if not isinstance(node_id, str) or not isinstance(node_def, dict):
                continue
            lines = node_def.get("lines")
            if not isinstance(lines, list):
                lines = []
            normalized_nodes[node_id] = {
                "lines": lines,
                "choices": node_def.get("choices"),
                "minigame": node_def.get("minigame"),
                # 条件で自動遷移（ボタン無し分岐）
                # 互換のため、auto_next という別名も許可
                "transitions": node_def.get("transitions") if "transitions" in node_def else node_def.get("auto_next"),
            }
        if start_node not in normalized_nodes:
            # 最低限startノードを用意
            normalized_nodes[start_node] = {"lines": [], "choices": None, "transitions": None}
        return {
            "title": title,
            "start_node": start_node,
            "nodes": normalized_nodes,
        }

    # 従来形式: lines が直下
    lines = raw.get("lines")
    if not isinstance(lines, list):
        lines = []
    return {
        "title": title,
        "start_node": "start",
        "nodes": {
            "start": {
                "lines": lines,
                "choices": raw.get("choices"),
                "minigame": raw.get("minigame"),
                "transitions": raw.get("transitions") if "transitions" in raw else raw.get("auto_next"),
            }
        },
    }


def get_story_definition(story_id: str) -> dict[str, Any]:
    """story_id からストーリー定義を取得（外部JSON優先、無ければ STORY_DATA）。"""
    ext = _load_external_stories()
    raw = ext.get(story_id)
    if isinstance(raw, dict):
        return _normalize_story_definition(raw)

    raw2 = STORY_DATA.get(story_id)
    if isinstance(raw2, dict):
        return _normalize_story_definition(raw2)

    return _normalize_story_definition({"title": "不明なストーリー", "lines": [{"speaker": "システム", "text": "ストーリーが見つかりません。"}]})


async def _story_get_state(user_id: int) -> dict[str, Any]:
    import db
    player = await db.get_player(user_id)
    return player or {}


async def _eval_conditions(user_id: int, conditions: Any) -> bool:
    """条件リストを評価（全て満たしたらTrue）。未指定/不正はTrue扱い。"""
    if not conditions:
        return True
    if not isinstance(conditions, list):
        return True

    state = await _story_get_state(user_id)
    story_flags = state.get("story_flags", {}) if isinstance(state.get("story_flags", {}), dict) else {}
    inventory = state.get("inventory", []) if isinstance(state.get("inventory", []), list) else []
    gold = int(state.get("gold", 0) or 0)

    atk = int(state.get("atk", 0) or 0)
    defense = int(state.get("def", 0) or 0)
    distance = int(state.get("distance", 0) or 0)

    for cond in conditions:
        if not isinstance(cond, dict):
            continue
        ctype = cond.get("type")
        if ctype == "flag.has":
            key = str(cond.get("key") or "")
            if not story_flags.get(key, False):
                return False
        elif ctype == "flag.missing":
            key = str(cond.get("key") or "")
            if story_flags.get(key, False):
                return False
        elif ctype == "inventory.has":
            item = str(cond.get("item") or "")
            if item and item not in inventory:
                return False
        elif ctype == "inventory.missing":
            item = str(cond.get("item") or "")
            if item and item in inventory:
                return False
        elif ctype == "gold.gte":
            amount = int(cond.get("amount") or 0)
            if gold < amount:
                return False

        # ---- 追加: ステータス/距離条件（分岐用） ----
        elif ctype == "stat.atk.gte":
            amount = int(cond.get("amount") or 0)
            if atk < amount:
                return False
        elif ctype == "stat.atk.lte":
            amount = int(cond.get("amount") or 0)
            if atk > amount:
                return False
        elif ctype == "stat.def.gte":
            amount = int(cond.get("amount") or 0)
            if defense < amount:
                return False
        elif ctype == "stat.def.lte":
            amount = int(cond.get("amount") or 0)
            if defense > amount:
                return False
        elif ctype == "distance.gte":
            amount = int(cond.get("amount") or 0)
            if distance < amount:
                return False
        elif ctype == "distance.lte":
            amount = int(cond.get("amount") or 0)
            if distance > amount:
                return False
        else:
            # 未知条件は無視（後方互換・段階導入のため）
            continue
    return True


async def _apply_effects(user_id: int, effects: Any) -> str:
    """effects を適用し、表示用のテキストを返す。"""
    if not effects:
        return ""
    if not isinstance(effects, list):
        return ""

    import db
    state = await _story_get_state(user_id)
    story_flags = state.get("story_flags", {}) if isinstance(state.get("story_flags", {}), dict) else {}
    inventory = state.get("inventory", []) if isinstance(state.get("inventory", []), list) else []

    reward_lines: list[str] = []

    for eff in effects:
        if not isinstance(eff, dict):
            continue
        etype = eff.get("type")

        if etype == "inventory.add":
            item = str(eff.get("item") or "")
            if item:
                once = bool(eff.get("once"))
                if once and item in inventory:
                    continue
                await db.add_item_to_inventory(user_id, item)
                inventory.append(item)
                reward_lines.append(f"📦 **{item}** を手に入れた！")

        elif etype == "inventory.remove":
            item = str(eff.get("item") or "")
            if item:
                await db.remove_item_from_inventory(user_id, item)
                reward_lines.append(f"📦 **{item}** を失った…")

        elif etype == "gold.add":
            amount = int(eff.get("amount") or 0)
            if amount:
                await db.add_gold(user_id, amount)
                sign = "+" if amount > 0 else ""
                reward_lines.append(f"💰 {sign}{amount}G")

        elif etype == "player.heal":
            hp = int(eff.get("hp") or 0)
            mp = int(eff.get("mp") or 0)
            player = await db.get_player(user_id)
            if player:
                updates = {}
                if hp:
                    max_hp = int(player.get("max_hp", 50) or 50)
                    cur_hp = int(player.get("hp", 50) or 50)
                    new_hp = min(max_hp, cur_hp + hp)
                    updates["hp"] = new_hp
                    reward_lines.append(f"💚 HP +{hp}")
                if mp:
                    max_mp = int(player.get("max_mp", 20) or 20)
                    cur_mp = int(player.get("mp", 20) or 20)
                    new_mp = min(max_mp, cur_mp + mp)
                    updates["mp"] = new_mp
                    reward_lines.append(f"💙 MP +{mp}")
                if updates:
                    await db.update_player(user_id, **updates)

        elif etype == "flag.set":
            key = str(eff.get("key") or "")
            if key:
                story_flags[key] = True
                await db.update_player(user_id, story_flags=story_flags)

        elif etype == "flag.clear":
            key = str(eff.get("key") or "")
            if key and key in story_flags:
                story_flags.pop(key, None)
                await db.update_player(user_id, story_flags=story_flags)

        else:
            continue

    return "\n".join(reward_lines)


async def _apply_next_after_minigame(
    *,
    user_id: int,
    user_processing: dict,
    interaction: discord.Interaction,
    base_story_id: str,
    callback_data: dict | None,
    next_spec: dict[str, Any] | None,
) -> None:
    """minigame 結果の next に従ってストーリーを再開する。"""
    nxt = next_spec or {}
    end = bool(nxt.get("end"))
    next_story_id = nxt.get("story_id")
    next_node_id = nxt.get("node")

    if end:
        # StoryView._finish_story 相当（callback_data は StoryView 側でのみ利用される）
        import db

        await db.set_story_flag(user_id, base_story_id)

        embed = discord.Embed(
            title="📘 ストーリー完了！",
            description="物語が一区切りついた。冒険を続けよう。",
            color=discord.Color.green(),
        )
        await interaction.response.edit_message(embed=embed, view=None)
        if user_id in user_processing:
            user_processing[user_id] = False
        return

    if isinstance(next_story_id, str) and next_story_id:
        view = StoryView(user_id, next_story_id, user_processing, callback_data=callback_data, node_id=str(next_node_id) if next_node_id else None)
        await view.send_story(interaction)
        return

    if isinstance(next_node_id, str) and next_node_id:
        view = StoryView(user_id, base_story_id, user_processing, callback_data=callback_data, node_id=next_node_id)
        await view.send_story(interaction)
        return

    # next が無い場合は「何もしない」扱い（呼び出し側でフォールバックする）
    if user_id in user_processing:
        user_processing[user_id] = False

STORY_DATA = {
    "voice_1": {
        "title": "どこからか声がする",
        "lines": [
            {
                "speaker": "???",
                "text": "おい、聞こえるか…？"
            },
            {
                "speaker": "???",
                "text": "お前、まだ何も知らないのか？"
            },
            {
                "speaker": "???",
                "text": "とっとと戻れ。戻り方？頑張ってくれ。進んでもいい事ないぞ――。"
            }
        ]
    },
    "intro_2": {
        "title": "既視感",
        "lines": [
            {
                "speaker": "???",
                "text": "お前…2回目だな？なんで進んだんだ。"
            },
            {
                "speaker": "???",
                "text": "死んだ時にポイント獲得したろ？あれで己を強化できる。"
            },
            {
                "speaker": "???",
                "text": "試しに `!upgrade` してみな。!buy_upgrade <番号> を忘れずにな。"
            }
        ]
    },
    "lucky_777": {
        "title": "幸運の数字",
        "lines": [
            {
                "speaker": "???",
                "text": "777m地点…か。"
            },
            {
                "speaker": "???",
                "text": "ラッキーセブン…何かいいことがあるかもな。"
            },
            {
                "speaker": "冒険者",
                "text": "こいつ、最初の無責任なやつにどこか似ているような、気のせいか"
            }
        ]
    },
    "story_250": {
        "title": "最初の痕跡",
        "lines": [
            {
                "speaker": "冒険者",
                "text": "壁に刻まれた文字を発見した。"
            },
            {
                "speaker": "古代文字",
                "text": "「ここは始まりに過ぎない。真実は深淵の底に眠る」"
            },
            {
                "speaker": "ナレーション",
                "text": "誰がいつ、なぜこれを刻んだのだろうか…"
            }
        ]
    },
    "story_750": {
        "title": "骸骨の山",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "おびただしい数の骸骨が積み上げられている。"
            },
            {
                "speaker": "ナレーション",
                "text": "これは…冒険者たちの成れの果てか？"
            },
            {
                "speaker": "ナレーション",
                "text": "戦慄が背筋を走るが、進むしかない。"
            }
        ]
    },
    "story_1250": {
        "title": "謎の老人",
        "lines": [
            {
                "speaker": "老人",
                "text": "よう、若造。まだ生きてるのか。"
            },
            {
                "speaker": "老人",
                "text": "この先、さらに地獄が待ってるぜ。"
            },
            {
                "speaker": "老人",
                "text": "だが、お前には…何か特別なものを感じるな。頑張れよ。"
            },
            {
                "speaker": "ナレーション",
                "text": "老人はそう言うと、闇の中へ消えていった…"
            }
        ]
    },
    "story_1750": {
        "title": "幻影の声",
        "lines": [
            {
                "speaker": "???",
                "text": "…助けて…"
            },
            {
                "speaker": "ナレーション",
                "text": "どこからか助けを求める声が聞こえる。"
            },
            {
                "speaker": "ナレーション",
                "text": "しかし、周囲には誰もいない。"
            },
            {
                "speaker": "ナレーション",
                "text": "このダンジョンには、何かがいる…"
            }
        ]
    },
    "story_2250": {
        "title": "古の記録",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "古びた日記を見つけた。"
            },
            {
                "speaker": "日記",
                "text": "「100日目。もう戻れないことは分かっている」"
            },
            {
                "speaker": "日記",
                "text": "「だが、私は真実に辿り着かねばならない」"
            },
            {
                "speaker": "ナレーション",
                "text": "この冒険者は、どうなったのだろう…"
            }
        ]
    },
    "story_2750": {
        "title": "鏡の間",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "鏡張りの部屋に出た。"
            },
            {
                "speaker": "ナレーション",
                "text": "鏡に映る自分を見る…傷だらけだ。"
            },
            {
                "speaker": "鏡の中の自分",
                "text": "「お前は…本当にここまで来るべきだったのか？」"
            },
            {
                "speaker": "ナレーション",
                "text": "鏡の中の自分が語りかけてきた。幻覚か？"
            }
        ]
    },
    "story_3250": {
        "title": "封印の扉",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "巨大な扉を発見した。"
            },
            {
                "speaker": "扉の碑文",
                "text": "「この先に進む者は、覚悟を持て」"
            },
            {
                "speaker": "扉の碑文",
                "text": "「引き返すことはもはや許されぬ」"
            },
            {
                "speaker": "ナレーション",
                "text": "だが、扉は既に開いている…先人がいたのか？"
            }
        ]
    },
    "story_3750": {
        "title": "魂の囁き",
        "lines": [
            {
                "speaker": "亡霊",
                "text": "ここまで…来たか…"
            },
            {
                "speaker": "亡霊",
                "text": "私は…かつてこのダンジョンに挑んだお前だ…"
            },
            {
                "speaker": "亡霊",
                "text": "お前も……同じ運命を辿るのだろう…"
            },
            {
                "speaker": "ナレーション",
                "text": "亡霊は光となって消えていった。\n\nあいつはなんだったんだ？"
            }
        ]
    },
    "story_4250": {
        "title": "深淵への階段",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "遥か下へと続く螺旋階段を見つけた。"
            },
            {
                "speaker": "ナレーション",
                "text": "底が見えないほど深い…"
            },
            {
                "speaker": "ナレーション",
                "text": "ここから先は、真の試練が待っているのだろう。"
            }
        ]
    },
    "story_4750": {
        "title": "魔力の泉",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "神秘的な泉を発見した。"
            },
            {
                "speaker": "ナレーション",
                "text": "水面が青白く光っている。"
            },
            {
                "speaker": "ナレーション",
                "text": "水を飲むと、不思議な力が体を巡った…気がする。多分気のせい――。"
            }
        ]
    },
    "story_5250": {
        "title": "崩壊の予兆",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "ダンジョンが微かに揺れている。"
            },
            {
                "speaker": "ナレーション",
                "text": "天井から小石が落ちてきた。"
            },
            {
                "speaker": "???",
                "text": "「このダンジョンは……普通に脆いだけだ。」"
            },
            {
                "speaker": "ナレーション",
                "text": "こいつはなんなんだ…"
            }
        ]
    },
    "story_5750": {
        "title": "真実の一端",
        "lines": [
            {
                "speaker": "謎の碑文",
                "text": "「このダンジョンは昔の先人が作りし物――」"
            },
            {
                "speaker": "謎の碑文",
                "text": "「最深部には、このダンジョンの全貌が隠されている……\nby : 製作者」"
            },
            {
                "speaker": "ナレーション",
                "text": "それが本当なら、進むしかないな。"
            }
        ]
    },
    "story_6250": {
        "title": "絶望の記録",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "血で書かれたメッセージがある。"
            },
            {
                "speaker": "メッセージ",
                "text": "「この記録を見た者よ…」"
            },
            {
                "speaker": "メッセージ",
                "text": "「何回同じところを歩くんだ……？」"
            },
            {
                "speaker": "ナレーション",
                "text": "書いた者は、もういない――"
            }
        ]
    },
    "story_6750": {
        "title": "決意の刻",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "ここまで来た。"
            },
            {
                "speaker": "ナレーション",
                "text": "もう戻ることはできない。"
            },
            {
                "speaker": "ナレーション",
                "text": "最深部は近い。"
            },
            {
                "speaker": "ナレーション",
                "text": "全ての答えが、そこにある。"
            }
        ]
    },
    "story_7250": {
        "title": "光と闇の境界",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "突然、眩しい光が差し込んできた。"
            },
            {
                "speaker": "ナレーション",
                "text": "だが、その先にはさらに深い闇が広がっている。"
            },
            {
                "speaker": "???",
                "text": "「ああっ………目がっ…！目がぁぁぁぁあっ！！」"
            },
            {
                "speaker": "ナレーション",
                "text": "真実に近づいている…？あれは'バ〇ス'だったのか……"
            }
        ]
    },
    "story_7750": {
        "title": "過去の幻影",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "幻が見える…かつての戦いの記憶だ。"
            },
            {
                "speaker": "幻影の戦士",
                "text": "「私たちは…???を倒すために…」"
            },
            {
                "speaker": "幻影の戦士",
                "text": "「だが…力及ばず…」"
            },
            {
                "speaker": "ナレーション",
                "text": "幻影は消えた。倒そうとした相手は誰だったのだろう？"
            }
        ]
    },
    "story_8250": {
        "title": "岩盤の崩壊",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "岩盤に大きな穴が空いている"
            },
            {
                "speaker": "ナレーション",
                "text": "これは…誰かが叩きつけられたものか？"
            },
            {
                "speaker": "???",
                "text": "「お、お前と一緒にぃ……ひ、避難する準備だぁ！」"
            },
            {
                "speaker": "ナレーション",
                "text": "1人用の'それ'でかぁ？\n\nバカバカしい。先に進もう。"
            }
        ]
    },
    "story_8750": {
        "title": "最終決戦前夜",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "空気が重い…"
            },
            {
                "speaker": "ナレーション",
                "text": "何者かの気配を強く感じる。"
            },
            {
                "speaker": "ナレーション",
                "text": "覚悟を決める時が来た。"
            },
            {
                "speaker": "ナレーション",
                "text": "この先に、全てが待っている。"
            }
        ]
    },
    "story_9250": {
        "title": "???の間近",
        "lines": [
            {
                "speaker": "???",
                "text": "「ここまで来ちまったのか？」"
            },
            {
                "speaker": "???",
                "text": "「お前には倒せない。戦いたくないから帰ってくれ」"
            },
            {
                "speaker": "ナレーション",
                "text": "声が…直接頭に響いてくる。"
            },
            {
                "speaker": "ナレーション",
                "text": "もう後戻りはできない！"
            }
        ]
    },
    "story_9750": {
        "title": "最後の一歩",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "目の前から不穏な雰囲気が漂う"
            },
            {
                "speaker": "ナレーション",
                "text": "ここまでの全ての戦いが、この瞬間のためにあった。"
            },
            {
                "speaker": "ナレーション",
                "text": "深呼吸をする…"
            },
            {
            },
            {
                "speaker": "あなた",
                "text": "(これは…死んだ時の…)"
            },
            {
                "speaker": "泉の声",
                "text": "三度死んだお前を、私は映す"
            },
            {
                "speaker": "ナレーション",
                "text": "水面が揺れ、死体は消えた。"
            }
        ]
    },
    "boss_pre_1": {
        "title": "第一の試練",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "ダンジョンの奥から、強大な気配が感じられる。"
            },
            {
                "speaker": "ナレーション",
                "text": "これが…最初の番人か。"
            },
            {
                "speaker": "スライムキング",
                "text": "「<:emoji_1:1433867679013539851>スライムだからって、いじめるのはやめてほしいです！」"
            },
            {
                "speaker": "ナレーション",
                "text": "戦いの時が来た！"
            }
        ]
    },
    "boss_post_1": {
        "title": "最初の勝利",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "番人を倒した…！"
            },
            {
                "speaker": "ナレーション",
                "text": "これで先に進める。"
            },
            {
                "speaker": "ナレーション",
                "text": "スライムさん、すみません。"
            }
        ]
    },
    "boss_pre_2": {
        "title": "暗闇の守護者",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "深淵がさらに深まっていく…"
            },
            {
                "speaker": "謎の声",
                "text": "貴様ごときが、この『道』を越えられるとでも思ったか？\n\n失礼なやつだな"
            },
            {
                "speaker": "ナレーション",
                "text": "闇の中から、巨大な影が姿を現す！"
            }
        ]
    },
    "boss_post_2": {
        "title": "闇を超えて",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "デスロードを退けた。"
            },
            {
                "speaker": "ナレーション",
                "text": "『あんなこと言ってイキってた癖にめっちゃ弱かったな。』"
            },
            {
                "speaker": "ナレーション",
                "text": "次なる試練へと歩こう"
            }
        ]
    },
    "boss_pre_3": {
        "title": "炎の支配者",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "辺りが急激に熱くなる…"
            },
            {
                "speaker": "炎の声",
                "text": "「我が炎で、お前を灰にしてやろう！」"
            },
            {
                "speaker": "ナレーション",
                "text": "炎を纏った巨獣が立ちはだかる！"
            }
        ]
    },
    "boss_post_3": {
        "title": "炎を制す",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "炎の支配者を倒した！"
            },
            {
                "speaker": "ナレーション",
                "text": "せっかくなら残り火で焼き芋でも作ろう"
            },
            {
                "speaker": "ナレーション",
                "text": "まだ旅は続く。"
            }
        ]
    },
    "boss_pre_4": {
        "title": "見えない",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "突然、当たりが暗くなる"
            },
            {
                "speaker": "ボスらしき声",
                "text": "『さあ、我がおぞましき姿に恐れるがいい！』"
            },
            {
                "speaker": "ナレーション",
                "text": "暗くて姿が見えない。"
            }
        ]
    },
    "boss_post_4": {
        "title": "闇を打ち破って",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "闇の王を打ち破った！"
            },
            {
                "speaker": "ナレーション",
                "text": "辺りが明るくなる…"
            },
            {
                "speaker": "ナレーション",
                "text": "冒険は続く。"
            }
        ]
    },
    "boss_pre_5": {
        "title": "雷鳴の王",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "空間が震え、雷鳴が轟く。"
            },
            {
                "speaker": "雷の声",
                "text": "「我が雷撃で消し去ってやる！」"
            },
            {
                "speaker": "ナレーション",
                "text": "雷を操る王が姿を現す！"
            }
        ]
    },
    "boss_post_5": {
        "title": "雷を超えて",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "雷鳴の王を倒した！"
            },
            {
                "speaker": "ナレーション",
                "text": "久しぶりの電気だ。\n『何かに使えないかな？』"
            },
            {
                "speaker": "ナレーション",
                "text": "半分まで来た。まだまだ続く。"
            }
        ]
    },
    "boss_pre_6": {
        "title": "おねえさん",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "鼻が人参の雪だるまがいる"
            },
            {
                "speaker": "???",
                "text": "『倒してかき氷にしちゃえよ』\n天才か？"
            },
            {
                "speaker": "ナレーション",
                "text": "初めてこの声に感謝した気がする。"
            }
        ]
    },
    "boss_post_6": {
        "title": "極寒を超えて",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "氷の女王を倒した！"
            },
            {
                "speaker": "ナレーション",
                "text": "これでかき氷！"
            },
            {
                "speaker": "ナレーション",
                "text": "振り返ると、氷は溶けていた――。"
            }
        ]
    },
    "boss_pre_7": {
        "title": "獄炎の巨人",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "巨大な存在が目を覚ます…"
            },
            {
                "speaker": "ナレーション",
                "text": "巨人が立ち上がる！"
            }
        ]
    },
    "boss_post_7": {
        "title": "巨人殺し",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "巨人を討ち取った"
            },
            {
                "speaker": "ナレーション",
                "text": "『ガタイが良すぎて動けてなかったな。』"
            },
            {
                "speaker": "ナレーション",
                "text": "もう7割以上進んだ。気を引き締めよう"
            }
        ]
    },
    "boss_pre_8": {
        "title": "死神の到来",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "死の気配が濃厚になる…"
            },
            {
                "speaker": "死神",
                "text": "「お前の魂、いただくぞ…」"
            },
            {
                "speaker": "ナレーション",
                "text": "深淵の守護神が鎌を振りかざす！"
            }
        ]
    },
    "boss_post_8": {
        "title": "死を超えて",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "なんとか退けた！"
            },
            {
                "speaker": "ナレーション",
                "text": "『この魂は誰のものなんだろう』"
            },
            {
                "speaker": "ナレーション",
                "text": "ゴールもう目前だ。"
            }
        ]
    },
    "boss_pre_9": {
        "title": "カオスからの挑戦",
        "lines": [
            {
                "speaker": "龍",
                "text": "混沌こそ想像の源！！！"
            },
            {
                "speaker": "ナレーション",
                "text": "……こいつ大丈夫か？"
            },
            {
                "speaker": "龍",
                "text": "「あいつの前に、お前を倒す！」"
            },
            {
                "speaker": "ナレーション",
                "text": "やばそうな龍との戦いが始まる！"
            }
        ]
    },
    "boss_post_9": {
        "title": "最後の番人を越えて",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "カオスを倒した…！"
            },
            {
                "speaker": "ナレーション",
                "text": "龍は闇に消えた。"
            },
            {
                "speaker": "ナレーション",
                "text": "次は…ボスだ。"
            }
        ]
    },
    "boss_pre_10": {
        "title": "???との決戦",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "ついに…到達した。"
            },
            {
                "speaker": "???",
                "text": "『帰れって言ったろ？なんで来た』"
            },
            {
                "speaker": "???",
                "text": "『来たなら戦わねえと行けないから嫌なんだ……』"
            },
            {
                "speaker": "ナレーション",
                "text": "運命の戦いが、今始まる！"
            }
        ]
    },
    "boss_post_10": {
        "title": "救済……？",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "???を倒した"
            },
            {
                "speaker": "???",
                "text": "「…まさか…俺に…」"
            },
            {
                "speaker": "ナレーション",
                "text": "???は光となって消えていった。"
            },
            {
                "speaker": "ナレーション",
                "text": "あいつは何者だったんだ？"
            },
            {
                "speaker": "ナレーション",
                "text": "おめでとう、冒険者よ。"
            }
        ]
    },
    "choice_mysterious_door": {
        "title": "謎の扉",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "目の前に2つの扉が現れた。"
            },
            {
                "speaker": "ナレーション",
                "text": "左の扉からは光が漏れている。右の扉からは闇が滲み出ている。"
            }
        ],
        "choices": [
            {
                "label": "① 光の扉を開ける",
                "result": {
                    "title": "光の選択",
                    "lines": [
                        {
                            "speaker": "ナレーション",
                            "text": "光の扉を開けた。"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "温かい光に包まれ、HPが回復した！"
                        }
                    ],
                    "reward": "hp_restore"
                }
            },
            {
                "label": "② 闇の扉を開ける",
                "result": {
                    "title": "闇の選択",
                    "lines": [
                        {
                            "speaker": "ナレーション",
                            "text": "闇の扉を開けた。"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "闇から強力な武器が現れた！"
                        }
                    ],
                    "reward": "weapon_drop"
                }
            }
        ]
    },
    "choice_strange_merchant": {
        "title": "怪しい商人",
        "lines": [
            {
                "speaker": "商人",
                "text": "ようこそ、旅人よ…"
            },
            {
                "speaker": "商人",
                "text": "特別な取引をしよう。金貨100枚で、何かをあげよう。"
            },
            {
                "speaker": "商人",
                "text": "さあ、どちらを選ぶ？"
            }
        ],
        "choices": [
            {
                "label": "① 取引を受ける（-100G）",
                "result": {
                    "title": "取引成立",
                    "lines": [
                        {
                            "speaker": "商人",
                            "text": "賢い選択だ…これを受け取りたまえ。"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "謎のアイテムを手に入れた！"
                        }
                    ],
                    "reward": "item_drop",
                    "gold_cost": 100
                }
            },
            {
                "label": "② 断る",
                "result": {
                    "title": "賢明な判断",
                    "lines": [
                        {
                            "speaker": "商人",
                            "text": "ふむ…慎重だな。"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "商人は闇に消えていった…"
                        }
                    ],
                    "reward": "none"
                }
            }
        ]
    },
    "choice_fork_road": {
        "title": "分かれ道",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "道が二手に分かれている。"
            },
            {
                "speaker": "ナレーション",
                "text": "左の道は平坦で歩きやすそうだ。右の道は険しく危険そうだ。"
            }
        ],
        "choices": [
            {
                "label": "① 左の安全な道を進む",
                "result": {
                    "title": "安全第一",
                    "lines": [
                        {
                            "speaker": "ナレーション",
                            "text": "安全な道を選んだ。"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "無事に進むことができた。"
                        }
                    ],
                    "reward": "small_gold"
                }
            },
            {
                "label": "② 右の険しい道に挑む",
                "result": {
                    "title": "危険な賭け",
                    "lines": [
                        {
                            "speaker": "ナレーション",
                            "text": "険しい道を選んだ…"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "道中で傷を負ったが、貴重な宝を発見した！"
                        }
                    ],
                    "reward": "rare_item_with_damage"
                }
            }
        ]
    },
    "choice_mysterious_well": {
        "title": "神秘の井戸",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "古い井戸を見つけた。"
            },
            {
                "speaker": "???",
                "text": "「硬貨を投げ入れると、願いが叶うかもしれない…」"
            }
        ],
        "choices": [
            {
                "label": "① 金貨を投げ入れる（-50G）",
                "result": {
                    "title": "願いの代償",
                    "lines": [
                        {
                            "speaker": "ナレーション",
                            "text": "金貨を井戸に投げ入れた。"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "井戸が光り輝き、力が湧いてきた！"
                        }
                    ],
                    "reward": "max_hp_boost",
                    "gold_cost": 50
                }
            },
            {
                "label": "② 何もせず立ち去る",
                "result": {
                    "title": "現実的な判断",
                    "lines": [
                        {
                            "speaker": "ナレーション",
                            "text": "怪しい井戸には近づかないことにした。"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "無難な選択だ…"
                        }
                    ],
                    "reward": "none"
                }
            }
        ]
    },
    "choice_sleeping_dragon": {
        "title": "眠る竜",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "巨大な竜が眠っている…"
            },
            {
                "speaker": "ナレーション",
                "text": "その傍らには、光り輝く宝珠がある。"
            }
        ],
        "choices": [
            {
                "label": "① 宝珠を盗む",
                "result": {
                    "title": "危険な強奪",
                    "lines": [
                        {
                            "speaker": "ナレーション",
                            "text": "そっと宝珠を掴んだ…"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "竜が目を覚ます前に逃げ出した！"
                        }
                    ],
                    "reward": "legendary_item"
                }
            },
            {
                "label": "② 見逃して進む",
                "result": {
                    "title": "慎重な選択",
                    "lines": [
                        {
                            "speaker": "ナレーション",
                            "text": "竜を起こすのは危険だ…"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "静かにその場を後にした。"
                        }
                    ],
                    "reward": "none"
                }
            }
        ]
    },
    "choice_cursed_treasure": {
        "title": "呪われた財宝",
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "黄金の山を発見した！"
            },
            {
                "speaker": "???",
                "text": "「これは呪われている…触れれば代償を払うことになるぞ」"
            }
        ],
        "choices": [
            {
                "label": "① 黄金を奪う",
                "result": {
                    "title": "欲望の代償",
                    "lines": [
                        {
                            "speaker": "ナレーション",
                            "text": "黄金を掴んだ瞬間、激しい痛みが走る！"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "それでも大金を手に入れた…"
                        }
                    ],
                    "reward": "gold_with_damage"
                }
            },
            {
                "label": "② 誘惑に負けず去る",
                "result": {
                    "title": "克己の心",
                    "lines": [
                        {
                            "speaker": "ナレーション",
                            "text": "欲望を抑え、黄金を諦めた。"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "心が軽くなった気がする…"
                        }
                    ],
                    "reward": "mp_restore"
                }
            }
        ]
    },
    "choice_time_traveler": {
        "title": "時の旅人",
        "lines": [
            {
                "speaker": "旅人",
                "text": "君は…選ばれし者だな。"
            },
            {
                "speaker": "旅人",
                "text": "私は時を超える者。君に過去か未来、どちらかを見せてあげよう。"
            }
        ],
        "choices": [
            {
                "label": "① 過去を見る",
                "result": {
                    "title": "忘れられた記憶",
                    "lines": [
                        {
                            "speaker": "ナレーション",
                            "text": "過去のビジョンが見えた…"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "かつての勇者たちの戦いの記憶が蘇る。戦いの経験値を得た！"
                        }
                    ],
                    "reward": "attack_boost"
                }
            },
            {
                "label": "② 未来を見る",
                "result": {
                    "title": "運命の予兆",
                    "lines": [
                        {
                            "speaker": "ナレーション",
                            "text": "未来のビジョンが見えた…"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "恐ろしい敵が待ち受けている…しかし、対策法が分かった！"
                        }
                    ],
                    "reward": "defense_boost"
                }
            }
        ]
    },
    "choice_fairy_spring": {
        "title": "妖精の泉",
        "lines": [
            {
                "speaker": "妖精",
                "text": "こんにちは、冒険者さん♪"
            },
            {
                "speaker": "妖精",
                "text": "この泉には不思議な力があるの。選んで？"
            }
        ],
        "choices": [
            {
                "label": "① 力の泉に入る",
                "result": {
                    "title": "力の祝福",
                    "lines": [
                        {
                            "speaker": "妖精",
                            "text": "力の泉を選んだのね！"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "体中に力が満ちてくる！攻撃力が上昇した！"
                        }
                    ],
                    "reward": "attack_boost"
                }
            },
            {
                "label": "② 癒しの泉に入る",
                "result": {
                    "title": "癒しの祝福",
                    "lines": [
                        {
                            "speaker": "妖精",
                            "text": "癒しの泉を選んだのね！"
                        },
                        {
                            "speaker": "ナレーション",
                            "text": "温かな光に包まれ、傷が癒えていく…"
                        }
                    ],
                    "reward": "full_heal"
                }
            }
        ]
    },
}

class StoryView(View):
    def __init__(self, user_id: int, story_id: str, user_processing: dict, callback_data: dict = None, node_id: str = None):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.story_id = story_id
        self.user_processing = user_processing
        self.current_page = 0
        self.callback_data = callback_data
        self.ctx = None

        story = get_story_definition(story_id)
        self.story_title = story["title"]
        self._story_def = story
        self.current_node_id = node_id or story.get("start_node", "start")
        self._load_current_node()

    def _load_current_node(self):
        node = self._story_def.get("nodes", {}).get(self.current_node_id)
        if not isinstance(node, dict):
            node = {"lines": [{"speaker": "システム", "text": "ストーリーが見つかりません。"}], "choices": None}
        self.story_lines = node.get("lines") if isinstance(node.get("lines"), list) else [{"speaker": "システム", "text": "ストーリーが見つかりません。"}]
        self.choices = node.get("choices")
        self.minigame = node.get("minigame")
        self.transitions = node.get("transitions")
        self.current_page = 0

    def _switch_story(self, story_id: str, node_id: str | None = None) -> None:
        story = get_story_definition(story_id)
        self.story_id = story_id
        self.story_title = story["title"]
        self._story_def = story
        self.current_node_id = node_id or story.get("start_node", "start")
        self._load_current_node()

    async def _maybe_apply_transition(self) -> bool:
        """現在ノードの transitions を評価し、該当があれば遷移する。

        戻り値: 遷移が起きたら True
        """
        transitions = self.transitions
        if not isinstance(transitions, list) or not transitions:
            return False

        for tr in transitions:
            if not isinstance(tr, dict):
                continue

            if not await _eval_conditions(self.user_id, tr.get("conditions")):
                continue

            # 任意: effects
            await _apply_effects(self.user_id, tr.get("effects"))

            nxt = tr.get("next") if isinstance(tr.get("next"), dict) else {}
            end = bool(nxt.get("end"))
            next_story_id = nxt.get("story_id")
            next_node_id = nxt.get("node")

            if end:
                # end は「このノード以降を進めない」扱い
                self.transitions = None
                self.choices = None
                self.story_lines = [{"speaker": "システム", "text": "（……）"}]
                self.current_page = 0
                return True

            if isinstance(next_story_id, str) and next_story_id:
                self._switch_story(next_story_id, str(next_node_id) if next_node_id else None)
                return True

            if isinstance(next_node_id, str) and next_node_id:
                self.current_node_id = next_node_id
                self._load_current_node()
                return True

            return False

        return False

    def get_embed(self):
        if self.current_page >= len(self.story_lines):
            self.current_page = len(self.story_lines) - 1

        line = self.story_lines[self.current_page]
        speaker = line.get("speaker", "???")
        text = line.get("text", "")

        embed = discord.Embed(
            title=f"📖 {self.story_title}",
            description=f"**{speaker}**：{text}",
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"ページ {self.current_page + 1}/{len(self.story_lines)}")

        return embed

    async def _start_minigame(self, interaction: discord.Interaction, minigame_cfg: Any) -> None:
        if not isinstance(minigame_cfg, dict):
            await interaction.response.send_message("⚠️ minigame定義が不正です", ephemeral=True)
            return

        mg_type = str(minigame_cfg.get("type") or "")
        if mg_type != "emoji_rpg":
            await interaction.response.send_message(f"⚠️ 未対応のminigame type: {mg_type}", ephemeral=True)
            return

        from emoji_rpg.view import EmojiRPGView

        map_id = str(minigame_cfg.get("map_id") or "demo_11x11")
        title = str(minigame_cfg.get("title") or "ミニゲーム")

        async def on_finish(result, finish_interaction: discord.Interaction) -> None:
            outcome = getattr(result, "outcome", "lose")
            outcome_key = "on_win" if outcome == "win" else "on_lose"
            outcome_spec = minigame_cfg.get(outcome_key) if isinstance(minigame_cfg.get(outcome_key), dict) else {}

            # effects
            await _apply_effects(self.user_id, outcome_spec.get("effects"))

            next_spec = outcome_spec.get("next") if isinstance(outcome_spec.get("next"), dict) else None
            if next_spec:
                await _apply_next_after_minigame(
                    user_id=self.user_id,
                    user_processing=self.user_processing,
                    interaction=finish_interaction,
                    base_story_id=self.story_id,
                    callback_data=self.callback_data,
                    next_spec=next_spec,
                )
                return

            # フォールバック: このストーリーを終了
            await self._finish_story(finish_interaction)

        view = EmojiRPGView(user_id=self.user_id, map_id=map_id, on_finish=on_finish, title=title)
        await interaction.response.edit_message(embed=view.get_embed(), view=view)

    async def send_story(self, ctx_or_interaction):
        # ctxを保存（選択肢処理で使用）
        if hasattr(ctx_or_interaction, 'channel'):
            self.ctx = ctx_or_interaction

        embed = self.get_embed()

        if hasattr(ctx_or_interaction, 'channel'):
            self.message = await ctx_or_interaction.channel.send(embed=embed, view=self)
        else:
            await ctx_or_interaction.response.edit_message(embed=embed, view=self)
            self.message = await ctx_or_interaction.original_response()

    @button(label="◀ BACK", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これはあなたのストーリーではありません！", ephemeral=True)
            return

        if self.current_page > 0:
            self.current_page -= 1

        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @button(label="NEXT ▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これはあなたのストーリーではありません！", ephemeral=True)
            return

        if self.current_page < len(self.story_lines) - 1:
            self.current_page += 1
            embed = self.get_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            import db

            # まず「ボタン無し分岐（条件自動遷移）」があるなら適用
            if await self._maybe_apply_transition():
                embed = self.get_embed()
                await interaction.response.edit_message(embed=embed, view=self)
                return

            # ミニゲームがある場合は起動（choices より優先）
            if getattr(self, "minigame", None):
                await self._start_minigame(interaction, self.minigame)
                return

            # 選択肢がある場合は選択Viewを表示
            if self.choices:
                choice_view = await StoryChoiceView.create(
                    self.user_id,
                    self.story_id,
                    self.current_node_id,
                    self._story_def,
                    self.choices,
                    self.user_processing,
                    self.ctx,
                    callback_data=self.callback_data,
                )

                # 条件に合致する選択肢が1つもない場合は完了扱い
                if getattr(choice_view, "_visible_choice_count", 0) <= 0:
                    await self._finish_story(interaction)
                    return
                embed = discord.Embed(
                    title=f"🔮 {self.story_title}",
                    description="どちらを選びますか？",
                    color=discord.Color.gold()
                )
                await interaction.response.edit_message(embed=embed, view=choice_view)
                return

            # 選択肢がない場合は通常通り完了
            await self._finish_story(interaction)

    async def _finish_story(self, interaction: discord.Interaction):
        import db

        await db.set_story_flag(self.user_id, self.story_id)

        embed = discord.Embed(
            title="📘 ストーリー完了！",
            description="物語が一区切りついた。冒険を続けよう。",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=None)

        # boss_battle コールバック互換
        if self.callback_data and self.callback_data.get('type') == 'boss_battle':
            import asyncio
            await asyncio.sleep(1.5)

            import game
            from views import BossBattleView, FinalBossBattleView

            boss_stage = self.callback_data['boss_stage']
            ctx = self.callback_data['ctx']

            boss = game.get_boss(boss_stage)
            if boss:
                player = await db.get_player(self.user_id)
                player_data = {
                    "hp": player.get("hp", 50),
                    "attack": player.get("atk", 5),
                    "defense": player.get("def", 2),
                    "inventory": player.get("inventory", []),
                    "distance": player.get("distance", 0),
                    "user_id": self.user_id
                }

                if boss_stage == 10:
                    embed = discord.Embed(
                        title="⚔️ ラスボス出現！",
                        description=f"**{boss['name']}** が最後の戦いに臨む！\n\nこれが最終決戦だ…！",
                        color=discord.Color.dark_gold()
                    )
                    await ctx.channel.send(embed=embed)
                    await asyncio.sleep(2)

                    view = await FinalBossBattleView.create(ctx, player_data, boss, self.user_processing, boss_stage)
                    await view.send_initial_embed()
                else:
                    embed = discord.Embed(
                        title="⚠️ ボス出現！",
                        description=f"**{boss['name']}** が立ちはだかる！",
                        color=discord.Color.dark_red()
                    )
                    await ctx.channel.send(embed=embed)
                    await asyncio.sleep(1.5)

                    view = await BossBattleView.create(ctx, player_data, boss, self.user_processing, boss_stage)
                    await view.send_initial_embed()
        else:
            if self.user_id in self.user_processing:
                self.user_processing[self.user_id] = False


class StoryChoiceView(View):
    """ストーリー選択肢View"""
    def __init__(self, user_id: int, story_id: str, node_id: str, story_def: dict, choices: list, user_processing: dict, ctx, callback_data: dict = None):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.story_id = story_id
        self.node_id = node_id
        self.story_def = story_def
        self.choices = choices
        self.user_processing = user_processing
        self.ctx = ctx
        self.callback_data = callback_data

        self._visible_choice_count: int = 0

    @classmethod
    async def create(cls, user_id: int, story_id: str, node_id: str, story_def: dict, choices: list, user_processing: dict, ctx, callback_data: dict = None) -> "StoryChoiceView":
        view = cls(user_id, story_id, node_id, story_def, choices, user_processing, ctx, callback_data=callback_data)

        visible_idx: list[int] = []
        for idx, choice in enumerate(choices):
            if not isinstance(choice, dict):
                visible_idx.append(idx)
                continue
            if await _eval_conditions(user_id, choice.get("conditions")):
                visible_idx.append(idx)

        view._visible_choice_count = len(visible_idx)

        for button_pos, idx in enumerate(visible_idx):
            choice = choices[idx]
            label = str(choice.get("label") or f"choice_{idx}") if isinstance(choice, dict) else f"choice_{idx}"
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary if button_pos == 0 else discord.ButtonStyle.secondary,
                custom_id=f"choice_{idx}"
            )
            btn.callback = view.create_choice_callback(idx)
            view.add_item(btn)

        return view

    def create_choice_callback(self, choice_idx):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("これはあなたの選択ではありません！", ephemeral=True)
                return

            import db
            import game
            import random

            choice = self.choices[choice_idx]
            if not isinstance(choice, dict):
                await interaction.response.send_message("⚠️ 選択肢データが不正です", ephemeral=True)
                return

            # 条件チェック（満たさない場合は弾く）
            if not await _eval_conditions(self.user_id, choice.get("conditions")):
                await interaction.response.send_message("⚠️ 条件を満たしていないため、その選択肢は選べません", ephemeral=True)
                return

            result = choice.get("result") if isinstance(choice.get("result"), dict) else {}
            result_title = str(result.get("title") or "結果")
            result_lines = result.get("lines") if isinstance(result.get("lines"), list) else []

            if result_lines:
                lines_text = "\n".join([f"**{line.get('speaker','???')}**：{line.get('text','')}" for line in result_lines if isinstance(line, dict)])
            else:
                lines_text = ""

            embed = discord.Embed(
                title=f"✨ {result_title}",
                description=lines_text or "（……）",
                color=discord.Color.gold()
            )

            battle = choice.get("battle") if isinstance(choice.get("battle"), dict) else None
            minigame = choice.get("minigame") if isinstance(choice.get("minigame"), dict) else None

            # 1) 新方式: effects
            reward_text = await _apply_effects(self.user_id, choice.get("effects"))

            # 2) 互換: 旧方式 reward（従来のハードコード報酬）
            player = await db.get_player(self.user_id)
            if isinstance(result, dict) and result.get("reward"):
                if result.get("reward") == "hp_restore":
                    max_hp = player.get("max_hp", 50)
                    heal_amount = int(max_hp * 1)
                    new_hp = min(max_hp, player.get("hp", 50) + heal_amount)
                    await db.update_player(self.user_id, hp=new_hp)
                    reward_text = (reward_text + "\n" if reward_text else "") + f"💚 HP +{heal_amount} 回復！"
                elif result.get("reward") == "weapon_drop":
                    weapons = [w for w, info in game.ITEMS_DATABASE.items() if info.get('type') == 'weapon']
                    if weapons:
                        weapon = random.choice(weapons)
                        await db.add_item_to_inventory(self.user_id, weapon)
                        reward_text = (reward_text + "\n" if reward_text else "") + f"⚔️ **{weapon}** を手に入れた！"
                elif result.get("reward") == "small_gold":
                    gold_amount = random.randint(50, 100)
                    await db.add_gold(self.user_id, gold_amount)
                    reward_text = (reward_text + "\n" if reward_text else "") + f"💰 {gold_amount}G を手に入れた！"

            if reward_text:
                embed.description += "\n\n" + reward_text

            # minigame がある場合は結果表示より先に開始（ストーリー側で演出したい場合はノードlinesを使う）
            if minigame:
                from emoji_rpg.view import EmojiRPGView

                mg_type = str(minigame.get("type") or "")
                if mg_type != "emoji_rpg":
                    await interaction.response.send_message(f"⚠️ 未対応のminigame type: {mg_type}", ephemeral=True)
                    return

                map_id = str(minigame.get("map_id") or "demo_11x11")
                title = str(minigame.get("title") or "ミニゲーム")

                async def on_finish(result, finish_interaction: discord.Interaction) -> None:
                    outcome = getattr(result, "outcome", "lose")
                    outcome_key = "on_win" if outcome == "win" else "on_lose"
                    outcome_spec = minigame.get(outcome_key) if isinstance(minigame.get(outcome_key), dict) else {}

                    await _apply_effects(self.user_id, outcome_spec.get("effects"))

                    next_spec = outcome_spec.get("next") if isinstance(outcome_spec.get("next"), dict) else None
                    if next_spec:
                        await _apply_next_after_minigame(
                            user_id=self.user_id,
                            user_processing=self.user_processing,
                            interaction=finish_interaction,
                            base_story_id=self.story_id,
                            callback_data=self.callback_data,
                            next_spec=next_spec,
                        )
                        return

                    # フォールバック: 完了扱い
                    if self.user_id in self.user_processing:
                        self.user_processing[self.user_id] = False

                view = EmojiRPGView(user_id=self.user_id, map_id=map_id, on_finish=on_finish, title=title)
                await interaction.response.edit_message(embed=view.get_embed(), view=view)
                return

            await interaction.response.edit_message(embed=embed, view=None)

            # 現ストーリーは既読扱いにする（従来互換）
            await db.set_story_flag(self.user_id, self.story_id)

            # 戦闘開始（選択肢に battle がある場合）
            if battle:
                import asyncio
                from types import SimpleNamespace
                from views import BattleView, BossBattleView, FinalBossBattleView

                await asyncio.sleep(1.0)

                # StoryView経由で Interaction が ctx として渡ってくるケースがあるため、
                # battle view が期待する (ctx.send / ctx.author) を満たすラッパを用意
                ctx_like = self.ctx
                if not hasattr(ctx_like, "send") or not hasattr(ctx_like, "author"):
                    if interaction.channel is None:
                        return
                    ctx_like = SimpleNamespace(
                        author=interaction.user,
                        channel=interaction.channel,
                        guild=interaction.guild,
                        send=interaction.channel.send,
                    )

                player = await db.get_player(self.user_id)
                if not player:
                    await ctx_like.send("⚠️ プレイヤーデータが見つかりません")
                    return

                player_data = {
                    "hp": player.get("hp", 50),
                    "max_hp": player.get("max_hp", 50),
                    "mp": player.get("mp", 20),
                    "max_mp": player.get("max_mp", 20),
                    "attack": player.get("atk", 5),
                    "defense": player.get("def", 2),
                    "inventory": player.get("inventory", []),
                    "distance": player.get("distance", 0),
                    "user_id": self.user_id,
                }

                btype = str(battle.get("type") or "enemy")
                if btype in {"enemy", "normal"}:
                    enemy = battle.get("enemy") if isinstance(battle.get("enemy"), dict) else None
                    if not enemy:
                        enemy = {"name": "みはり", "hp": 60, "atk": 8, "def": 3}

                    enemy_data = {
                        "name": str(enemy.get("name") or "みはり"),
                        "hp": int(enemy.get("hp") or 60),
                        "atk": int(enemy.get("atk") or 8),
                        "def": int(enemy.get("def") or 3),
                    }

                    story_meta = battle.get("story") if isinstance(battle.get("story"), dict) else None
                    story_id = str(story_meta.get("story_id") or self.story_id) if story_meta else self.story_id
                    on_win_node = str(story_meta.get("on_win_node") or "") if story_meta else ""
                    on_lose_node = str(story_meta.get("on_lose_node") or "") if story_meta else ""
                    on_lose_half_node = str(story_meta.get("on_lose_half_node") or "") if story_meta else ""
                    lose_half_ratio = float(story_meta.get("lose_half_ratio") or 0.5) if story_meta else 0.5
                    heal_on_end = bool(story_meta.get("heal_on_end")) if story_meta and "heal_on_end" in story_meta else False
                    allow_flee = bool(story_meta.get("allow_flee")) if story_meta and "allow_flee" in story_meta else True

                    async def post_battle_hook(*, outcome: str, enemy_hp: int, enemy_max_hp: int) -> None:
                        import db

                        # 勝敗で遷移先ノードを決める
                        next_node = None
                        if outcome == "win" and on_win_node:
                            next_node = on_win_node
                        elif outcome == "lose":
                            # みはりの仕様: 敵HPが半分以下まで削れていれば「敗北(半分削る)」
                            if on_lose_half_node and enemy_max_hp > 0 and enemy_hp <= int(enemy_max_hp * lose_half_ratio):
                                next_node = on_lose_half_node
                            elif on_lose_node:
                                next_node = on_lose_node

                        # 回復（勝利/敗北(半分)のとき）
                        if heal_on_end and next_node in {on_win_node, on_lose_half_node}:
                            player = await db.get_player(self.user_id)
                            if player:
                                max_hp = int(player.get("max_hp", 50) or 50)
                                max_mp = int(player.get("max_mp", 20) or 20)
                                await db.update_player(self.user_id, hp=max_hp, mp=max_mp)

                        if next_node:
                            view = StoryView(self.user_id, story_id, self.user_processing, node_id=next_node)
                            await view.send_story(ctx_like)

                        if getattr(ctx_like, "author", None) is not None:
                            if ctx_like.author.id in self.user_processing:
                                self.user_processing[ctx_like.author.id] = False

                    view = await BattleView.create(
                        ctx_like,
                        player_data,
                        enemy_data,
                        self.user_processing,
                        post_battle_hook=post_battle_hook,
                        enemy_max_hp=int(enemy_data.get("hp") or 0),
                        allow_flee=allow_flee,
                    )
                    await view.send_initial_embed()
                    return

                if btype in {"boss", "boss_stage"}:
                    boss_stage = int(battle.get("boss_stage") or 1)
                    boss = game.get_boss(boss_stage)
                    if not boss:
                        await ctx_like.send("⚠️ ボス情報が見つかりません")
                        return

                    if boss_stage == 10:
                        view = await FinalBossBattleView.create(ctx_like, player_data, boss, self.user_processing, boss_stage)
                    else:
                        view = await BossBattleView.create(ctx_like, player_data, boss, self.user_processing, boss_stage)
                    await view.send_initial_embed()
                    return

            # 次への分岐（任意）
            nxt = choice.get("next") if isinstance(choice.get("next"), dict) else None
            if nxt:
                import asyncio
                await asyncio.sleep(1.0)

                next_story_id = nxt.get("story_id")
                next_node_id = nxt.get("node")
                end = bool(nxt.get("end"))

                if end:
                    # 完全終了
                    if self.callback_data and self.callback_data.get('type') == 'boss_battle':
                        # boss_pre等で使う場合に備え、終了後はStoryView側のfinishに寄せたいが、互換優先で単純に解除
                        pass
                    if self.user_id in self.user_processing:
                        self.user_processing[self.user_id] = False
                    return

                # story_id指定があれば別ストーリーへ
                if isinstance(next_story_id, str) and next_story_id:
                    view = StoryView(self.user_id, next_story_id, self.user_processing, node_id=str(next_node_id) if next_node_id else None)
                    await view.send_story(self.ctx)
                    return

                # nodeのみ指定なら同一ストーリー内の別ノードへ
                if isinstance(next_node_id, str) and next_node_id:
                    view = StoryView(self.user_id, self.story_id, self.user_processing, node_id=next_node_id)
                    await view.send_story(self.ctx)
                    return

            # 分岐が無ければ終了（従来と同じ）
            if self.user_id in self.user_processing:
                self.user_processing[self.user_id] = False

        return callback
