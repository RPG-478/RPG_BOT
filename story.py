import discord
from discord.ui import View, button
import json
from pathlib import Path
from typing import Any, Optional


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
            print(f"⚠️ ストーリーJSONの読み込みに失敗: {path} ({e})")
            return

        stories = data.get("stories") if isinstance(data, dict) else None
        if not isinstance(stories, dict):
            print(f"⚠️ ストーリーJSON形式が不正: {path}（トップレベルに 'stories' dict が必要）")
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
    loop_requirement = int(raw.get("loop_requirement") or 0)
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
            }
        if start_node not in normalized_nodes:
            # 最低限startノードを用意
            normalized_nodes[start_node] = {"lines": [], "choices": None}
        return {
            "title": title,
            "loop_requirement": loop_requirement,
            "start_node": start_node,
            "nodes": normalized_nodes,
        }

    # 従来形式: lines が直下
    lines = raw.get("lines")
    if not isinstance(lines, list):
        lines = []
    return {
        "title": title,
        "loop_requirement": loop_requirement,
        "start_node": "start",
        "nodes": {
            "start": {
                "lines": lines,
                "choices": raw.get("choices"),
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

    reward_lines: list[str] = []

    for eff in effects:
        if not isinstance(eff, dict):
            continue
        etype = eff.get("type")

        if etype == "inventory.add":
            item = str(eff.get("item") or "")
            if item:
                await db.add_item_to_inventory(user_id, item)
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

STORY_DATA = {
    "voice_1": {
        "title": "どこからか声がする",
        "loop_requirement": 0,
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
        "loop_requirement": 1,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
                "speaker": "ナレーション",
                "text": "考えてても始まらない！"
            }
        ]
    },
    "story_250_loop2": {
        "title": "既視感の文字",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "壁の文字を見つけた…これは前にも見た。"
            },
            {
                "speaker": "古代文字",
                "text": "「ここは始まりに過ぎない。真実は深淵の底に眠る」"
            },
            {
                "speaker": "あなた",
                "text": "（やはり同じ文字だ…これは繰り返しなのか？）"
            }
        ]
    },
    "story_750_loop2": {
        "title": "変わらぬ骸骨",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "また、あの骸骨の山だ…"
            },
            {
                "speaker": "あなた",
                "text": "（前回もここで見た。少し増えているような…）"
            },
            {
                "speaker": "ナレーション",
                "text": "不気味な既視感が襲ってくる。"
            }
        ]
    },
    "story_1250_loop2": {
        "title": "老人の忠告",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "老人",
                "text": "また会ったな…お前、気づいているか？"
            },
            {
                "speaker": "老人",
                "text": "この世界は…何度も繰り返されている。"
            },
            {
                "speaker": "老人",
                "text": "だが、お前は強くなっている。それが希望だ。"
            },
            {
                "speaker": "ナレーション",
                "text": "老人の言葉が心に残る…"
            }
        ]
    },
    "story_250_loop3": {
        "title": "真実に近づく",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "また同じ文字…だが、今回は何かが違う。"
            },
            {
                "speaker": "古代文字",
                "text": "「繰り返す者よ、真実はお前の中にある」"
            },
            {
                "speaker": "あなた",
                "text": "（文字が…変わった？なぜ？）"
            }
        ]
    },
    "story_750_loop3": {
        "title": "骸骨の真実",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "骸骨の山…だが、今回はよく見える。"
            },
            {
                "speaker": "ナレーション",
                "text": "これは…全て同じ人物の骨だ。"
            },
            {
                "speaker": "あなた",
                "text": "（まさか…これは全て、私…？）"
            },
            {
                "speaker": "ナレーション",
                "text": "恐ろしい妄想が浮かび上がる。"
            }
        ]
    },
    "story_1250_loop3": {
        "title": "老人の正体",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "老人",
                "text": "3回目…か。よくここまで来た。"
            },
            {
                "speaker": "老人",
                "text": "実はな…私もお前だ。遥か未来のな。"
            },
            {
                "speaker": "あなた",
                "text": "（何を言っている…？）"
            },
            {
                "speaker": "老人",
                "text": "いつか分かる。その時まで、諦めるな。"
            },
            {
                "speaker": "ナレーション",
                "text": "老人は煙のように消えていった…"
            }
        ]
    },
    "story_250_loop4": {
        "title": "文字が語りかける",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "壁の文字が微かに光り、声が聞こえる。"
            },
            {
                "speaker": "古代文字",
                "text": "「四度目の訪問者よ」"
            },
            {
                "speaker": "あなた",
                "text": "(この文字…私を数えている…？)"
            },
            {
                "speaker": "古代文字",
                "text": "「お前は、何度ここに来る？」"
            }
        ]
    },
    "story_250_loop5": {
        "title": "文字の反転",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "文字が壁から剥がれ、空中に浮かび始める。"
            },
            {
                "speaker": "ナレーション",
                "text": "そして…逆さまになった。"
            },
            {
                "speaker": "古代文字",
                "text": "「゜るれ流に逆が間時」"
            },
            {
                "speaker": "あなた",
                "text": "(時間が逆に…流れてる…？)"
            },
            {
                "speaker": "ナレーション",
                "text": "文字が一つずつ、元に戻っていく。"
            }
        ]
    },
    "story_250_loop6": {
        "title": "無言の記録",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "壁の文字が次々と変化し、自分の死因を列挙していく。"
            },
            {
                "speaker": "ナレーション",
                "text": "スライムに。ゴブリンに。罠に。飢えに。絶望に。"
            },
            {
                "speaker": "ナレーション",
                "text": "六つの死が、静かに刻まれている。"
            },
            {
                "speaker": "ナレーション",
                "text": "何も言えない。ただ見つめることしかできない。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "やがて、文字は消えた。"
            }
        ]
    },
    "story_250_loop7": {
        "title": "文字との対話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "文字が質問を投げかけてくる。"
            },
            {
                "speaker": "古代文字",
                "text": "「なぜ進む？」"
            },
            {
                "speaker": "あなた",
                "text": "(…答えを知りたいからだ)"
            },
            {
                "speaker": "古代文字",
                "text": "「七度も死んだというのに？」"
            },
            {
                "speaker": "あなた",
                "text": "(だからこそ、だ)"
            }
        ]
    },
    "story_250_loop8": {
        "title": "文字が示す真実",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "文字が一瞬、ダンジョンの全体図を浮かび上がらせる。"
            },
            {
                "speaker": "ナレーション",
                "text": "100の階層。10,000mの深淵。そして…最深部に何かがいる。"
            },
            {
                "speaker": "古代文字",
                "text": "「この迷宮は誰が作った？」"
            },
            {
                "speaker": "あなた",
                "text": "(それを…知るために進む…)"
            },
            {
                "speaker": "古代文字",
                "text": "「ならば進め。八度目の挑戦者よ」"
            }
        ]
    },
    "story_250_loop9": {
        "title": "文字の祝福",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "文字が金色に輝き、道を照らす。"
            },
            {
                "speaker": "古代文字",
                "text": "「九度…」"
            },
            {
                "speaker": "ナレーション",
                "text": "文字が途切れる。"
            },
            {
                "speaker": "古代文字",
                "text": "「…よくぞ、ここまで」"
            },
            {
                "speaker": "あなた",
                "text": "(ここまで来た…もう止まれない…)"
            }
        ]
    },
    "story_250_loop10": {
        "title": "文字の沈黙",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "文字が静かに消えていく。"
            },
            {
                "speaker": "ナレーション",
                "text": "壁には何も残らない。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(全ての答えは…最深部にある…)"
            },
            {
                "speaker": "ナレーション",
                "text": "静寂の中、ただ前へ進む。"
            }
        ]
    },
    "story_750_loop4": {
        "title": "動く骸骨",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "骸骨の一つが、カタカタと動き出す。"
            },
            {
                "speaker": "骸骨",
                "text": "ああ…お前か…四度目だな…"
            },
            {
                "speaker": "あなた",
                "text": "(骸骨が…喋った…？)"
            },
            {
                "speaker": "骸骨",
                "text": "何度来ても…結末は同じだぞ…"
            }
        ]
    },
    "story_750_loop5": {
        "title": "骸骨の合唱",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "骸骨たちが一斉にカタカタと音を立て始める。"
            },
            {
                "speaker": "骸骨",
                "text": "五度目 五度目 五度目"
            },
            {
                "speaker": "ナレーション",
                "text": "音が重なり、不協和音になっていく。"
            },
            {
                "speaker": "あなた",
                "text": "(時間が…何度も重なっている…)"
            },
            {
                "speaker": "ナレーション",
                "text": "やがて、音は止んだ。"
            }
        ]
    },
    "story_750_loop6": {
        "title": "骸骨の沈黙",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "骸骨たちが一斉に顔を向ける。"
            },
            {
                "speaker": "ナレーション",
                "text": "全てが自分の骸骨だ。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "六つの死体。六つの失敗。六つの終わり。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "何も言えない。"
            }
        ]
    },
    "story_750_loop7": {
        "title": "骸骨との会話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "一つの骸骨が立ち上がり、こちらを見つめる。"
            },
            {
                "speaker": "過去の自分",
                "text": "七度目…か。諦めないんだな…"
            },
            {
                "speaker": "あなた",
                "text": "(お前は…諦めたのか？)"
            },
            {
                "speaker": "過去の自分",
                "text": "…いや。お前に託した。"
            },
            {
                "speaker": "ナレーション",
                "text": "骸骨は静かに崩れ落ちた。"
            }
        ]
    },
    "story_750_loop8": {
        "title": "骸骨の疑問",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "骸骨たちが口々に囁く。"
            },
            {
                "speaker": "骸骨",
                "text": "なぜ…誰が…この運命を…"
            },
            {
                "speaker": "あなた",
                "text": "(それを知るために…進む…)"
            },
            {
                "speaker": "骸骨",
                "text": "八度も死んで…まだ…"
            },
            {
                "speaker": "あなた",
                "text": "(八度死んだから、だ)"
            }
        ]
    },
    "story_750_loop9": {
        "title": "骸骨の道標",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "骸骨たちが一斉に奥を指差す。"
            },
            {
                "speaker": "骸骨",
                "text": "行け…九度目の自分…お前なら…"
            },
            {
                "speaker": "あなた",
                "text": "(全ての自分が…待っている…)"
            },
            {
                "speaker": "ナレーション",
                "text": "骸骨の山が、道を開く。"
            }
        ]
    },
    "story_750_loop10": {
        "title": "骸骨の祈り",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "骸骨たちが静かに崩れ落ちていく。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(十度目…これが最後になる…)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "静寂の中、骸骨の山を越えて進む。"
            }
        ]
    },
    "story_1250_loop4": {
        "title": "老人の記憶",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "老人が杖で地面に数字を書く。「4」だ。"
            },
            {
                "speaker": "老人",
                "text": "四度目だな…学習が遅い…"
            },
            {
                "speaker": "あなた",
                "text": "(この人…全て覚えている…)"
            },
            {
                "speaker": "老人",
                "text": "私も…何百度と会ったからな…"
            }
        ]
    },
    "story_1250_loop5": {
        "title": "老人の分裂",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "老人の姿が二つに分かれる。"
            },
            {
                "speaker": "老人",
                "text": "五度も死ねば…"
            },
            {
                "speaker": "老人",
                "text": "…現実も歪む…"
            },
            {
                "speaker": "ナレーション",
                "text": "二人の老人が、同じ動きで杖を突く。"
            },
            {
                "speaker": "あなた",
                "text": "(どちらが…本物…？)"
            }
        ]
    },
    "story_1250_loop6": {
        "title": "老人の正体",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "老人の顔が、自分の顔に変わっていく。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "老人",
                "text": "気づいてしまったか…"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(未来の…自分…？)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_1250_loop7": {
        "title": "老人との対話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "老人が立ち上がり、こちらに歩み寄る。"
            },
            {
                "speaker": "老人",
                "text": "七度目で…気づくとは。早い方だ。"
            },
            {
                "speaker": "あなた",
                "text": "(あなたは…何度挑戦したんです？)"
            },
            {
                "speaker": "老人",
                "text": "百度目で、諦めた。"
            },
            {
                "speaker": "あなた",
                "text": "(…私は、あなたにはならない)"
            }
        ]
    },
    "story_1250_loop8": {
        "title": "老人の警告",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "老人が杖を強く突く。部屋が震える。"
            },
            {
                "speaker": "老人",
                "text": "真実を知れば…後悔する…"
            },
            {
                "speaker": "あなた",
                "text": "(それでも…知りたい…)"
            },
            {
                "speaker": "老人",
                "text": "では問おう。誰が、この迷宮を作った？"
            },
            {
                "speaker": "あなた",
                "text": "(…それを知るために、進む)"
            }
        ]
    },
    "story_1250_loop9": {
        "title": "老人の別れ",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "老人が静かに扉を指差す。"
            },
            {
                "speaker": "老人",
                "text": "九度目か…超えるかもしれんな…私を…"
            },
            {
                "speaker": "あなた",
                "text": "(もう…引き返さない…)"
            },
            {
                "speaker": "老人",
                "text": "ならば行け。全てを…終わらせろ…"
            }
        ]
    },
    "story_1250_loop10": {
        "title": "老人の消滅",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "老人が光となって消えていく。"
            },
            {
                "speaker": "老人",
                "text": "十度目の挑戦者よ…"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "老人",
                "text": "…全てを終わらせろ…"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "部屋には誰もいない。ただ前へ進む。"
            }
        ]
    },
    "story_1750_loop2": {
        "title": "聞き覚えのある声",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "また同じ声が聞こえる…前にも聞いた気がする。"
            },
            {
                "speaker": "謎の声",
                "text": "助けて…また来たのか…？"
            },
            {
                "speaker": "あなた",
                "text": "(この声…どこかで…)"
            },
            {
                "speaker": "謎の声",
                "text": "二度目…だな…"
            }
        ]
    },
    "story_1750_loop3": {
        "title": "声の主の痕跡",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "声のする方へ進むと、壁に血で書かれたメッセージがある。"
            },
            {
                "speaker": "血文字",
                "text": "助けて 過去の自分"
            },
            {
                "speaker": "あなた",
                "text": "(これは…私の筆跡…？)"
            },
            {
                "speaker": "ナレーション",
                "text": "血はまだ乾いていない。"
            }
        ]
    },
    "story_1750_loop4": {
        "title": "声の主の正体",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "声の主が姿を現した。青白い幽霊だ。"
            },
            {
                "speaker": "幽霊",
                "text": "お前…何度目だ？もう数えるのをやめた…"
            },
            {
                "speaker": "あなた",
                "text": "(こいつ…私のことを知っている…)"
            },
            {
                "speaker": "幽霊",
                "text": "四度目だ。まだ気づかないのか？"
            }
        ]
    },
    "story_1750_loop5": {
        "title": "声の逆再生",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "声が二つ、三つ…無数に重なり始める。"
            },
            {
                "speaker": "謎の声",
                "text": "助けて…助けて…助けて…"
            },
            {
                "speaker": "ナレーション",
                "text": "そして突然、声が逆再生され始めた。"
            },
            {
                "speaker": "謎の声",
                "text": "…てけ助…てけ助…てけ助"
            },
            {
                "speaker": "あなた",
                "text": "(時間が…巻き戻ってる…？)"
            }
        ]
    },
    "story_1750_loop6": {
        "title": "声の正体",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "幽霊の顔が、自分の顔に変わっていく。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "幽霊",
                "text": "助けてくれ…未来の自分…"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(これは…過去の自分が…死ぬ直前に…)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_1750_loop7": {
        "title": "過去との対話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "過去の自分の幻影が、こちらを見つめている。"
            },
            {
                "speaker": "過去の自分",
                "text": "なぜ進む？何度死んでも…意味がないのに…"
            },
            {
                "speaker": "あなた",
                "text": "(…あなたは諦めたのか？)"
            },
            {
                "speaker": "過去の自分",
                "text": "…いや。お前に託した。"
            },
            {
                "speaker": "あなた",
                "text": "(ならば、進む)"
            }
        ]
    },
    "story_1750_loop8": {
        "title": "真実を知る声",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "幻影が突然、冷たい目でこちらを見た。"
            },
            {
                "speaker": "過去の自分",
                "text": "誰が…この世界を作った？なぜ私たちは…"
            },
            {
                "speaker": "あなた",
                "text": "(それを知るために…進むんだ…)"
            },
            {
                "speaker": "過去の自分",
                "text": "八度目で気づくとは…遅いな…"
            },
            {
                "speaker": "あなた",
                "text": "(…それでも、進む)"
            }
        ]
    },
    "story_1750_loop9": {
        "title": "声の導き",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "幻影が奥へと指を差す。声はもう聞こえない。"
            },
            {
                "speaker": "過去の自分",
                "text": "…行け。お前なら…たどり着けるかもしれない…"
            },
            {
                "speaker": "あなた",
                "text": "(もう…引き返せない…)"
            },
            {
                "speaker": "ナレーション",
                "text": "幻影が微笑んだ。"
            }
        ]
    },
    "story_1750_loop10": {
        "title": "静寂の中の決意",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "声は完全に消えた。幻影も静かに消えていく。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(全ての自分が…この先を望んでいる…)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "静寂の中、ただ一歩を踏み出す。"
            }
        ]
    },
    "story_2250_loop2": {
        "title": "日記の既視感",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "日記を開くと…前に読んだページがある気がする。"
            },
            {
                "speaker": "日記",
                "text": "「また同じ場所に戻ってしまった」"
            },
            {
                "speaker": "あなた",
                "text": "(この文章…見覚えがある…)"
            },
            {
                "speaker": "日記",
                "text": "「二度目だ。なぜだ」"
            }
        ]
    },
    "story_2250_loop3": {
        "title": "日記の追記",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "最後のページに、新しいインクで書かれた文字がある。"
            },
            {
                "speaker": "日記",
                "text": "「三度目。また死ぬのか」"
            },
            {
                "speaker": "あなた",
                "text": "(この筆跡…)"
            },
            {
                "speaker": "ナレーション",
                "text": "自分のものだ。間違いない。"
            }
        ]
    },
    "story_2250_loop4": {
        "title": "増えるページ",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "日記のページが…前より増えている。"
            },
            {
                "speaker": "日記",
                "text": "「四度目の挑戦。今度こそ」"
            },
            {
                "speaker": "あなた",
                "text": "(私が…書いたのか…？)"
            },
            {
                "speaker": "日記",
                "text": "「いや、書かされている」"
            }
        ]
    },
    "story_2250_loop5": {
        "title": "勝手にめくれる日記",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "日記が宙に浮き、ページが勝手にめくれていく。"
            },
            {
                "speaker": "ナレーション",
                "text": "前から。後ろから。同時に。"
            },
            {
                "speaker": "日記",
                "text": "「五度死んだ。数えるのもばかばかしい」"
            },
            {
                "speaker": "あなた",
                "text": "(時間が…狂っている…)"
            },
            {
                "speaker": "ナレーション",
                "text": "ページが破れ、宙を舞う。"
            }
        ]
    },
    "story_2250_loop6": {
        "title": "死の詳細",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "日記に、自分の死が詳細に記録されている。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "日記",
                "text": "「六度目。スライムに。ゴブリンに。罠に。飢えに。絶望に。そして…」"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "最後の一つは、まだ書かれていない。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_2250_loop7": {
        "title": "日記の筆跡",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "日記の全てのページが、自分の筆跡になっている。"
            },
            {
                "speaker": "日記",
                "text": "「七度目。自分が自分を記録している」"
            },
            {
                "speaker": "あなた",
                "text": "(これは…全部私が書いたのか…？)"
            },
            {
                "speaker": "日記",
                "text": "「いや、書かされている。誰に？」"
            },
            {
                "speaker": "あなた",
                "text": "(…それを知るために、進む)"
            }
        ]
    },
    "story_2250_loop8": {
        "title": "日記の問いかけ",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "日記の最後のページに、質問が書かれている。"
            },
            {
                "speaker": "日記",
                "text": "「なぜ、この日記を書き続けるのか？」"
            },
            {
                "speaker": "日記",
                "text": "「忘れたくないから？」"
            },
            {
                "speaker": "日記",
                "text": "「それとも、忘れられないから？」"
            },
            {
                "speaker": "あなた",
                "text": "(…どちらも、だ)"
            }
        ]
    },
    "story_2250_loop9": {
        "title": "空白のページ",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "日記の最後のページは空白だ。ペンが一本、置いてある。"
            },
            {
                "speaker": "あなた",
                "text": "(次は…私が書くのか…？)"
            },
            {
                "speaker": "ナレーション",
                "text": "ペンを取る。そして、置く。"
            },
            {
                "speaker": "あなた",
                "text": "(…いや。もう書かない)"
            },
            {
                "speaker": "ナレーション",
                "text": "先へ進む。"
            }
        ]
    },
    "story_2250_loop10": {
        "title": "未完の記録",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "日記が静かに閉じる。表紙に「未完」と刻まれている。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(この物語を…完結させる…)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "日記を置いて、最深部へ向かう。"
            }
        ]
    },
    "story_2750_loop2": {
        "title": "鏡の違和感",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "鏡の中の自分が…微かに笑っている気がする。"
            },
            {
                "speaker": "鏡の中の自分",
                "text": "また来たんだ…"
            },
            {
                "speaker": "あなた",
                "text": "(鏡が…喋った…？)"
            },
            {
                "speaker": "鏡の中の自分",
                "text": "二度目だね"
            }
        ]
    },
    "story_2750_loop3": {
        "title": "鏡の前のメモ",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "鏡の前に、メモが置いてある。"
            },
            {
                "speaker": "メモ",
                "text": "「鏡を見るな。三度目だ」"
            },
            {
                "speaker": "あなた",
                "text": "(私が…書いたのか…)"
            },
            {
                "speaker": "ナレーション",
                "text": "だが、もう見てしまった。"
            }
        ]
    },
    "story_2750_loop4": {
        "title": "鏡との対話",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "鏡の中の自分が、動きと無関係に話しかけてくる。"
            },
            {
                "speaker": "鏡の中の自分",
                "text": "四度目…か。学習しないね…"
            },
            {
                "speaker": "あなた",
                "text": "(鏡の中の私が…独立している…？)"
            },
            {
                "speaker": "鏡の中の自分",
                "text": "私はお前。お前は私。でも…違う"
            }
        ]
    },
    "story_2750_loop5": {
        "title": "鏡の反転世界",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "鏡の中の景色が歪み、全てが反転し始める。"
            },
            {
                "speaker": "ナレーション",
                "text": "右が左に。上が下に。"
            },
            {
                "speaker": "鏡の中の自分",
                "text": "。た見を死たし度も五…"
            },
            {
                "speaker": "あなた",
                "text": "(言葉まで…逆に…？)"
            },
            {
                "speaker": "ナレーション",
                "text": "やがて、元に戻った。"
            }
        ]
    },
    "story_2750_loop6": {
        "title": "鏡からの脱出",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "鏡の中の自分が、鏡から手を伸ばしてくる。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "鏡の中の自分",
                "text": "助けて…私も…外に出たい…"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(これは…過去の自分の残留思念…？)"
            },
            {
                "speaker": "ナレーション",
                "text": "手を引っ込める。"
            }
        ]
    },
    "story_2750_loop7": {
        "title": "鏡との入れ替わり",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "鏡に触れた瞬間、自分と鏡の中の自分が入れ替わる。"
            },
            {
                "speaker": "鏡の中の自分",
                "text": "お前は…私だ。私は…お前だ…"
            },
            {
                "speaker": "あなた",
                "text": "(どっちが…本物なんだ…？)"
            },
            {
                "speaker": "鏡の中の自分",
                "text": "どちらも本物で、どちらも偽物だ"
            },
            {
                "speaker": "ナレーション",
                "text": "また入れ替わる。"
            }
        ]
    },
    "story_2750_loop8": {
        "title": "鏡の真実",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "鏡が割れ、中から無数の自分が溢れ出る。"
            },
            {
                "speaker": "鏡の中の自分",
                "text": "これが…お前の死の数だ…"
            },
            {
                "speaker": "あなた",
                "text": "(こんなに…何度も…)"
            },
            {
                "speaker": "鏡の中の自分",
                "text": "八度どころじゃない。もっと…もっと…"
            },
            {
                "speaker": "あなた",
                "text": "(…それでも、進む)"
            }
        ]
    },
    "story_2750_loop9": {
        "title": "鏡の導き",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "鏡が奥への扉を映し出す。"
            },
            {
                "speaker": "鏡の中の自分",
                "text": "行け…九度目の自分…終わらせろ…"
            },
            {
                "speaker": "あなた",
                "text": "(全ての自分が…待っている…)"
            },
            {
                "speaker": "鏡の中の自分",
                "text": "私たちは…お前を信じている"
            }
        ]
    },
    "story_2750_loop10": {
        "title": "鏡の消滅",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "鏡が光となって消えていく。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(もう…鏡は要らない…)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "自分を信じて、前へ進む。"
            }
        ]
    },
    "story_3250_loop2": {
        "title": "開いた扉",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉が…微かに開いている。"
            },
            {
                "speaker": "あなた",
                "text": "(前は…閉まっていた気が…)"
            },
            {
                "speaker": "???",
                "text": "また来たのか…"
            },
            {
                "speaker": "ナレーション",
                "text": "扉の隙間から、声が漏れる。"
            }
        ]
    },
    "story_3250_loop3": {
        "title": "扉の前の装備",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉の前に、自分の装備が散乱している。"
            },
            {
                "speaker": "あなた",
                "text": "(これは…死んだ時の…)"
            },
            {
                "speaker": "血文字",
                "text": "開けるな"
            },
            {
                "speaker": "ナレーション",
                "text": "だが、扉は既に開きかけている。"
            }
        ]
    },
    "story_3250_loop4": {
        "title": "扉の向こう",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉の隙間から、何かが覗いている。"
            },
            {
                "speaker": "???",
                "text": "四度目だな…もうすぐ開く…"
            },
            {
                "speaker": "あなた",
                "text": "(何が…出てくる…？)"
            },
            {
                "speaker": "???",
                "text": "お前だよ"
            }
        ]
    },
    "story_3250_loop5": {
        "title": "扉の開閉",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉が開く。閉じる。開く。閉じる。"
            },
            {
                "speaker": "ナレーション",
                "text": "繰り返す。繰り返す。繰り返す。"
            },
            {
                "speaker": "???",
                "text": "五度…五度…五度…"
            },
            {
                "speaker": "あなた",
                "text": "(時間が…ループしている…)"
            },
            {
                "speaker": "ナレーション",
                "text": "やがて、扉は止まった。半開きのまま。"
            }
        ]
    },
    "story_3250_loop6": {
        "title": "扉の中の自分",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉の隙間から、自分の顔が覗いている。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "扉の中の自分",
                "text": "助けて…出して…"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(これは…何度も死んだ自分…？)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_3250_loop7": {
        "title": "扉を開く",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉を押す。重い。だが、開いていく。"
            },
            {
                "speaker": "扉の中の自分",
                "text": "ありがとう…七度目の自分…"
            },
            {
                "speaker": "ナレーション",
                "text": "中から、無数の自分が溢れ出る。"
            },
            {
                "speaker": "あなた",
                "text": "(これが…全ての死…)"
            },
            {
                "speaker": "ナレーション",
                "text": "幻影たちは、奥へと消えていく。"
            }
        ]
    },
    "story_3250_loop8": {
        "title": "扉の問いかけ",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉に刻まれた文字が光る。"
            },
            {
                "speaker": "古代文字",
                "text": "「なぜ封印を解く？」"
            },
            {
                "speaker": "あなた",
                "text": "(閉じ込めておくわけにはいかない)"
            },
            {
                "speaker": "古代文字",
                "text": "「解放すれば、真実に近づく」"
            },
            {
                "speaker": "あなた",
                "text": "(ならば、開ける)"
            }
        ]
    },
    "story_3250_loop9": {
        "title": "完全に開いた扉",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉が完全に開いた。"
            },
            {
                "speaker": "ナレーション",
                "text": "中には…何もない。"
            },
            {
                "speaker": "古代文字",
                "text": "「九度目にして、解放」"
            },
            {
                "speaker": "あなた",
                "text": "(封印されていたのは…何も…？)"
            },
            {
                "speaker": "古代文字",
                "text": "「いや。お前自身だ」"
            }
        ]
    },
    "story_3250_loop10": {
        "title": "扉の消滅",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉が光となって消えていく。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(もう…封印は要らない…)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "解放されたまま、前へ進む。"
            }
        ]
    },
    "story_3750_loop2": {
        "title": "既知の囁き",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "囁き声が…前より大きくなっている。"
            },
            {
                "speaker": "囁き声",
                "text": "また来た…また来た…"
            },
            {
                "speaker": "あなた",
                "text": "(この声…聞いたことがある…)"
            },
            {
                "speaker": "囁き声",
                "text": "二度目だ…"
            }
        ]
    },
    "story_3750_loop3": {
        "title": "囁きの正体",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "囁き声の一つが、はっきりと聞こえる。"
            },
            {
                "speaker": "囁き声",
                "text": "戻れ…過去の自分…"
            },
            {
                "speaker": "あなた",
                "text": "(これは…私の声…？)"
            },
            {
                "speaker": "ナレーション",
                "text": "自分の声が、無数に重なっている。"
            }
        ]
    },
    "story_3750_loop4": {
        "title": "囁きの記憶",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "囁き声が、過去の記憶を語り始める。"
            },
            {
                "speaker": "囁き声",
                "text": "四度目…スライムに…ゴブリンに…罠に…"
            },
            {
                "speaker": "あなた",
                "text": "(全ての死を…覚えている…)"
            },
            {
                "speaker": "囁き声",
                "text": "忘れられない…忘れたくない…"
            }
        ]
    },
    "story_3750_loop5": {
        "title": "囁きの合唱",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "囁き声が一斉に同じ言葉を繰り返す。"
            },
            {
                "speaker": "囁き声",
                "text": "五度 五度 五度 五度 五度"
            },
            {
                "speaker": "ナレーション",
                "text": "そして突然、逆から。"
            },
            {
                "speaker": "囁き声",
                "text": "度五 度五 度五 度五 度五"
            },
            {
                "speaker": "あなた",
                "text": "(時間が…往復している…)"
            }
        ]
    },
    "story_3750_loop6": {
        "title": "囁きの亡霊",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "囁き声が形を持ち始める。青白い亡霊たちだ。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "亡霊",
                "text": "私たちは…お前の死だ…"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(六つの…死んだ自分…)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_3750_loop7": {
        "title": "囁きとの対話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "亡霊の一人が、こちらに近づいてくる。"
            },
            {
                "speaker": "亡霊",
                "text": "なぜ進む？七度も死んだのに…"
            },
            {
                "speaker": "あなた",
                "text": "(あなたたちのため、だ)"
            },
            {
                "speaker": "亡霊",
                "text": "…ありがとう。"
            },
            {
                "speaker": "ナレーション",
                "text": "亡霊は微笑んで消えた。"
            }
        ]
    },
    "story_3750_loop8": {
        "title": "囁きの真実",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "囁き声が、真実を語り始める。"
            },
            {
                "speaker": "囁き声",
                "text": "この世界は…誰かが作った…"
            },
            {
                "speaker": "囁き声",
                "text": "私たちは…何度も殺された…"
            },
            {
                "speaker": "あなた",
                "text": "(誰が…？)"
            },
            {
                "speaker": "囁き声",
                "text": "それは…最深部で…"
            }
        ]
    },
    "story_3750_loop9": {
        "title": "囁きの祝福",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "囁き声が静まり、一つの声だけが残る。"
            },
            {
                "speaker": "囁き声",
                "text": "行け…九度目の自分…全てを終わらせて…"
            },
            {
                "speaker": "あなた",
                "text": "(必ず…)"
            },
            {
                "speaker": "ナレーション",
                "text": "声は消えた。"
            }
        ]
    },
    "story_3750_loop10": {
        "title": "囁きの沈黙",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "全ての囁き声が消えた。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "完全な静寂。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "静寂の中、ただ前へ進む。"
            }
        ]
    },
    "story_4250_loop2": {
        "title": "無限の階段",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "階段を下りる。下りる。下りる。"
            },
            {
                "speaker": "あなた",
                "text": "(前にも…ここを…)"
            },
            {
                "speaker": "???",
                "text": "二度目だ。また同じ階段を…"
            },
            {
                "speaker": "ナレーション",
                "text": "振り返ると、上も見えない。"
            }
        ]
    },
    "story_4250_loop3": {
        "title": "階段の血痕",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "階段に、血の足跡がついている。"
            },
            {
                "speaker": "あなた",
                "text": "(これは…私の…)"
            },
            {
                "speaker": "血文字",
                "text": "三度目"
            },
            {
                "speaker": "ナレーション",
                "text": "足跡は、下へ下へと続いている。"
            }
        ]
    },
    "story_4250_loop4": {
        "title": "階段の記憶",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "階段の途中で、幻影が立っている。"
            },
            {
                "speaker": "幻影",
                "text": "四度目か…まだ下りるのか？"
            },
            {
                "speaker": "あなた",
                "text": "(下りなければ…進めない)"
            },
            {
                "speaker": "幻影",
                "text": "では、また会おう。五度目に"
            }
        ]
    },
    "story_4250_loop5": {
        "title": "階段の逆行",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "階段を下りているはずなのに…"
            },
            {
                "speaker": "ナレーション",
                "text": "上っている？"
            },
            {
                "speaker": "あなた",
                "text": "(どっちに…進んでいる…？)"
            },
            {
                "speaker": "???",
                "text": "五度死ねば、上下も分からなくなる"
            },
            {
                "speaker": "ナレーション",
                "text": "やがて、階段は正常に戻った。"
            }
        ]
    },
    "story_4250_loop6": {
        "title": "階段の終わり",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "階段が…終わった。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "平地に出る。だが、また階段が現れた。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(終わらない…永遠に…)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_4250_loop7": {
        "title": "階段との対話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "階段の途中で、過去の自分が座っている。"
            },
            {
                "speaker": "過去の自分",
                "text": "疲れた…もう下りたくない…"
            },
            {
                "speaker": "あなた",
                "text": "(…休んでいい。私が進む)"
            },
            {
                "speaker": "過去の自分",
                "text": "ありがとう…七度目の自分…"
            },
            {
                "speaker": "ナレーション",
                "text": "幻影は消えた。"
            }
        ]
    },
    "story_4250_loop8": {
        "title": "階段の真実",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "階段の壁に、文字が刻まれている。"
            },
            {
                "speaker": "古代文字",
                "text": "「この階段に終わりはない」"
            },
            {
                "speaker": "あなた",
                "text": "(なら…どうすれば…)"
            },
            {
                "speaker": "古代文字",
                "text": "「ただ進め。八度目の挑戦者よ」"
            },
            {
                "speaker": "あなた",
                "text": "(…分かった)"
            }
        ]
    },
    "story_4250_loop9": {
        "title": "階段の光",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "階段の先に、光が見える。"
            },
            {
                "speaker": "あなた",
                "text": "(あれが…出口…？)"
            },
            {
                "speaker": "???",
                "text": "九度目にして、たどり着くとは…"
            },
            {
                "speaker": "ナレーション",
                "text": "光に向かって、下り続ける。"
            }
        ]
    },
    "story_4250_loop10": {
        "title": "階段を越えて",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "階段が終わった。本当に。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(十度目…ようやく…)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "平地に立ち、前へ進む。"
            }
        ]
    },
    "story_4750_loop2": {
        "title": "泉の変化",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "泉の色が…前より濃くなっている気がする。"
            },
            {
                "speaker": "あなた",
                "text": "(この泉…見覚えが…)"
            },
            {
                "speaker": "泉の声",
                "text": "また来たのか…"
            },
            {
                "speaker": "ナレーション",
                "text": "水面に、自分の顔が映る。"
            }
        ]
    },
    "story_4750_loop3": {
        "title": "泉に映る死",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "水面を覗くと、自分の死体が映っている。"
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
    "story_4750_loop4": {
        "title": "泉の記憶",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "泉の水が、過去の記憶を映し出す。"
            },
            {
                "speaker": "泉の声",
                "text": "四度目の訪問…全て覚えている…"
            },
            {
                "speaker": "あなた",
                "text": "(この泉…全てを記録している…)"
            },
            {
                "speaker": "泉の声",
                "text": "私は忘れない。お前が何度死のうとも"
            }
        ]
    },
    "story_4750_loop5": {
        "title": "泉が血に",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "泉の水が、青から赤に変わっていく。"
            },
            {
                "speaker": "ナレーション",
                "text": "血だ。"
            },
            {
                "speaker": "泉の声",
                "text": "五度死んだお前の…血だ…"
            },
            {
                "speaker": "あなた",
                "text": "(こんなに…流した…)"
            },
            {
                "speaker": "ナレーション",
                "text": "やがて、水は青に戻った。"
            }
        ]
    },
    "story_4750_loop6": {
        "title": "泉の沈黙",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "泉が完全に静止している。波一つ立たない。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "水面には、六つの死体が映っている。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "全て、自分だ。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_4750_loop7": {
        "title": "泉との対話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "水面から、過去の自分が現れる。"
            },
            {
                "speaker": "過去の自分",
                "text": "七度目…まだ諦めないのか…"
            },
            {
                "speaker": "あなた",
                "text": "(諦めたら…あなたたちが報われない)"
            },
            {
                "speaker": "過去の自分",
                "text": "…ありがとう。"
            },
            {
                "speaker": "ナレーション",
                "text": "水面が揺れ、幻影は消えた。"
            }
        ]
    },
    "story_4750_loop8": {
        "title": "泉の真実",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "泉の水が、ダンジョンの全体図を映し出す。"
            },
            {
                "speaker": "泉の声",
                "text": "この迷宮の正体を…知りたいか？"
            },
            {
                "speaker": "あなた",
                "text": "(…知りたい)"
            },
            {
                "speaker": "泉の声",
                "text": "ならば進め。八度目の挑戦者よ"
            },
            {
                "speaker": "ナレーション",
                "text": "地図は消えた。"
            }
        ]
    },
    "story_4750_loop9": {
        "title": "泉の祝福",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "泉の水が、金色に輝き始める。"
            },
            {
                "speaker": "泉の声",
                "text": "九度目…よくぞここまで…"
            },
            {
                "speaker": "あなた",
                "text": "(もう少し…もう少しだ…)"
            },
            {
                "speaker": "ナレーション",
                "text": "水が、道を照らしてくれる。"
            }
        ]
    },
    "story_4750_loop10": {
        "title": "泉の消滅",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "泉の水が、全て蒸発していく。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "泉の声",
                "text": "十度目の挑戦者よ…全てを終わらせて…"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "泉は消えた。前へ進む。"
            }
        ]
    },
    "story_5250_loop2": {
        "title": "揺れの増幅",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "揺れが…前より激しくなっている。"
            },
            {
                "speaker": "あなた",
                "text": "(この感覚…前にも…)"
            },
            {
                "speaker": "???",
                "text": "二度目だ。また崩れる…"
            },
            {
                "speaker": "ナレーション",
                "text": "天井から、石が落ちてくる。"
            }
        ]
    },
    "story_5250_loop3": {
        "title": "崩壊の痕跡",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "壁に、ひび割れが走っている。"
            },
            {
                "speaker": "あなた",
                "text": "(前は…なかった気が…)"
            },
            {
                "speaker": "血文字",
                "text": "三度目 崩壊"
            },
            {
                "speaker": "ナレーション",
                "text": "ひび割れが、どんどん広がっていく。"
            }
        ]
    },
    "story_5250_loop4": {
        "title": "世界の崩壊",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "壁が崩れ落ち始める。"
            },
            {
                "speaker": "???",
                "text": "四度死ねば、世界も崩れる…"
            },
            {
                "speaker": "あなた",
                "text": "(私のせい…？)"
            },
            {
                "speaker": "???",
                "text": "いや、元から壊れていた。お前が気づいただけだ"
            }
        ]
    },
    "story_5250_loop5": {
        "title": "崩壊の連鎖",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "天井が、床が、壁が、全てが崩れていく。"
            },
            {
                "speaker": "ナレーション",
                "text": "だが、自分は無傷だ。"
            },
            {
                "speaker": "???",
                "text": "五度目…お前だけが残る…"
            },
            {
                "speaker": "あなた",
                "text": "(なぜ…私だけ…)"
            },
            {
                "speaker": "ナレーション",
                "text": "やがて、崩壊は止まった。"
            }
        ]
    },
    "story_5250_loop6": {
        "title": "崩壊の真実",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "崩壊した瓦礫の中に、文字が浮かび上がる。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "古代文字",
                "text": "「この世界は偽物だ」"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(偽物…？)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_5250_loop7": {
        "title": "崩壊との対話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "瓦礫の中から、過去の自分が現れる。"
            },
            {
                "speaker": "過去の自分",
                "text": "七度目…気づいたか？"
            },
            {
                "speaker": "あなた",
                "text": "(この世界は…偽物…？)"
            },
            {
                "speaker": "過去の自分",
                "text": "そうだ。全ては…誰かが作った…"
            },
            {
                "speaker": "あなた",
                "text": "(誰が…？)"
            }
        ]
    },
    "story_5250_loop8": {
        "title": "崩壊の問いかけ",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "崩壊した世界の中で、声が響く。"
            },
            {
                "speaker": "???",
                "text": "誰が、この世界を作った？"
            },
            {
                "speaker": "???",
                "text": "なぜ、お前は何度も死ぬ？"
            },
            {
                "speaker": "あなた",
                "text": "(それを…知るために…)"
            },
            {
                "speaker": "???",
                "text": "ならば進め。真実は近い"
            }
        ]
    },
    "story_5250_loop9": {
        "title": "崩壊の終わり",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "崩壊が止まる。世界が、元に戻り始める。"
            },
            {
                "speaker": "???",
                "text": "九度目…もうすぐ全てが明らかになる…"
            },
            {
                "speaker": "あなた",
                "text": "(もう少し…)"
            },
            {
                "speaker": "ナレーション",
                "text": "世界は完全に修復された。"
            }
        ]
    },
    "story_5250_loop10": {
        "title": "崩壊の静寂",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "揺れが完全に止まった。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "完全な静寂。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "静寂の中、ただ前へ進む。"
            }
        ]
    },
    "story_5750_loop2": {
        "title": "石板の記録",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "石板に、文字が浮かび上がる。"
            },
            {
                "speaker": "石板",
                "text": "「二度目の訪問者よ」"
            },
            {
                "speaker": "あなた",
                "text": "(この石板…私を覚えている…)"
            },
            {
                "speaker": "石板",
                "text": "「まだ真実を知る資格はない」"
            }
        ]
    },
    "story_5750_loop3": {
        "title": "石板の試練",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "石板が質問を投げかける。"
            },
            {
                "speaker": "石板",
                "text": "「三度死んだお前に問う。なぜ進む？」"
            },
            {
                "speaker": "あなた",
                "text": "(真実を…知るため)"
            },
            {
                "speaker": "石板",
                "text": "「まだ足りない。もっと死ね」"
            }
        ]
    },
    "story_5750_loop4": {
        "title": "石板の変化",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "石板の文字が、複雑になっていく。"
            },
            {
                "speaker": "石板",
                "text": "「四度目…少し見えてきたか？」"
            },
            {
                "speaker": "あなた",
                "text": "(この世界は…偽物…？)"
            },
            {
                "speaker": "石板",
                "text": "「正解。だが、なぜ偽物だ？」"
            }
        ]
    },
    "story_5750_loop5": {
        "title": "石板の反転",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "石板が回転し、裏面が現れる。"
            },
            {
                "speaker": "ナレーション",
                "text": "そこには、ダンジョンの設計図が。"
            },
            {
                "speaker": "石板",
                "text": "「五度死ねば、見える。この世界の正体が」"
            },
            {
                "speaker": "あなた",
                "text": "(これは…誰が作った…？)"
            },
            {
                "speaker": "ナレーション",
                "text": "石板は元に戻った。"
            }
        ]
    },
    "story_5750_loop6": {
        "title": "石板の真実",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "石板が割れ、中から光が溢れ出る。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "石板",
                "text": "「六度目。真実を語ろう」"
            },
            {
                "speaker": "石板",
                "text": "「この世界は、実験だ」"
            },
            {
                "speaker": "あなた",
                "text": "(実験…？)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_5750_loop7": {
        "title": "石板との対話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "石板から、声が聞こえる。"
            },
            {
                "speaker": "石板",
                "text": "「七度死んだお前は、特別だ」"
            },
            {
                "speaker": "あなた",
                "text": "(何が…特別なんです？)"
            },
            {
                "speaker": "石板",
                "text": "「諦めなかったこと、だ」"
            },
            {
                "speaker": "あなた",
                "text": "(それだけ…？)"
            }
        ]
    },
    "story_5750_loop8": {
        "title": "石板の問いかけ",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "石板が最後の質問をする。"
            },
            {
                "speaker": "石板",
                "text": "「誰が、この実験を始めた？」"
            },
            {
                "speaker": "あなた",
                "text": "(…最深部にいる?)"
            },
            {
                "speaker": "石板",
                "text": "「正解。行け、八度目の挑戦者よ」"
            },
            {
                "speaker": "ナレーション",
                "text": "石板が道を照らす。"
            }
        ]
    },
    "story_5750_loop9": {
        "title": "石板の祝福",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "石板が金色に輝く。"
            },
            {
                "speaker": "石板",
                "text": "「九度目…もうすぐだ…」"
            },
            {
                "speaker": "あなた",
                "text": "(もう少し…真実まで…)"
            },
            {
                "speaker": "石板",
                "text": "「全てを終わらせろ。実験を」"
            }
        ]
    },
    "story_5750_loop10": {
        "title": "石板の消滅",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "石板が光となって消えていく。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "石板",
                "text": "「十度目の挑戦者よ…全てを知れ…」"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "石板は消えた。前へ進む。"
            }
        ]
    },
    "story_6250_loop2": {
        "title": "増える血文字",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "血文字が…前より増えている。"
            },
            {
                "speaker": "血文字",
                "text": "「二度目 また来た また死ぬ」"
            },
            {
                "speaker": "あなた",
                "text": "(この文字…見覚えが…)"
            },
            {
                "speaker": "ナレーション",
                "text": "自分の筆跡だ。"
            }
        ]
    },
    "story_6250_loop3": {
        "title": "絶叫の記録",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "血文字が、絶叫を綴っている。"
            },
            {
                "speaker": "血文字",
                "text": "「三度目 もう嫌だ 助けて 誰か」"
            },
            {
                "speaker": "あなた",
                "text": "(これは…過去の私が…)"
            },
            {
                "speaker": "ナレーション",
                "text": "指で書いたのだろう。爪が剥がれている。"
            }
        ]
    },
    "story_6250_loop4": {
        "title": "狂気の蓄積",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "血文字が、無秩序に壁を埋め尽くしている。"
            },
            {
                "speaker": "血文字",
                "text": "「四度 四度 四度 四度 四度 四度」"
            },
            {
                "speaker": "あなた",
                "text": "(こんなに…追い詰められていた…)"
            },
            {
                "speaker": "血文字",
                "text": "「狂う 狂う 狂う 狂う 狂う」"
            }
        ]
    },
    "story_6250_loop5": {
        "title": "血文字の動き",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "血文字が、壁の上を這い回り始める。"
            },
            {
                "speaker": "ナレーション",
                "text": "文字が文字を食べ、増殖していく。"
            },
            {
                "speaker": "血文字",
                "text": "五 五 五 五 五 五 五 五 五 五"
            },
            {
                "speaker": "あなた",
                "text": "(狂気が…伝染する…)"
            },
            {
                "speaker": "ナレーション",
                "text": "やがて、文字は止まった。"
            }
        ]
    },
    "story_6250_loop6": {
        "title": "絶望の極み",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "壁全体が血で覆われている。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "血文字",
                "text": "「六度死んだ もう人間じゃない」"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(…違う。まだ人間だ)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_6250_loop7": {
        "title": "狂気との対話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "血文字の中から、過去の自分の声が聞こえる。"
            },
            {
                "speaker": "過去の自分",
                "text": "助けて…七度目の自分…"
            },
            {
                "speaker": "あなた",
                "text": "(大丈夫。もうすぐ終わる)"
            },
            {
                "speaker": "過去の自分",
                "text": "本当に…？"
            },
            {
                "speaker": "あなた",
                "text": "(…必ず)"
            }
        ]
    },
    "story_6250_loop8": {
        "title": "狂気の真実",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "血文字が、最後のメッセージを綴る。"
            },
            {
                "speaker": "血文字",
                "text": "「八度死んだ。気づいた。」"
            },
            {
                "speaker": "血文字",
                "text": "「これは実験だ。私たちは…」"
            },
            {
                "speaker": "あなた",
                "text": "(実験…誰の…？)"
            },
            {
                "speaker": "血文字",
                "text": "「最深部に…全ての答えが…」"
            }
        ]
    },
    "story_6250_loop9": {
        "title": "狂気の終焉",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "血文字が、静かに消えていく。"
            },
            {
                "speaker": "血文字",
                "text": "「九度目…もう…大丈夫…」"
            },
            {
                "speaker": "あなた",
                "text": "(もうすぐ…全てが終わる…)"
            },
            {
                "speaker": "ナレーション",
                "text": "壁が、元の白さを取り戻す。"
            }
        ]
    },
    "story_6250_loop10": {
        "title": "狂気の浄化",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "全ての血文字が消えた。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "壁は、真っ白だ。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "浄化された部屋を出て、前へ進む。"
            }
        ]
    },
    "story_6750_loop2": {
        "title": "既知の選択",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "また同じ分かれ道だ。"
            },
            {
                "speaker": "???",
                "text": "二度目だな。また進むのか？"
            },
            {
                "speaker": "あなた",
                "text": "(当然だ)"
            },
            {
                "speaker": "???",
                "text": "ならば行け"
            }
        ]
    },
    "story_6750_loop3": {
        "title": "血の道標",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "分かれ道に、血の矢印が書かれている。"
            },
            {
                "speaker": "血文字",
                "text": "戻れ"
            },
            {
                "speaker": "あなた",
                "text": "(これは…過去の私からの警告…)"
            },
            {
                "speaker": "ナレーション",
                "text": "だが、進む。"
            }
        ]
    },
    "story_6750_loop4": {
        "title": "選択の記憶",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "分かれ道の前に、幻影が立っている。"
            },
            {
                "speaker": "幻影",
                "text": "四度目…まだ進むのか？"
            },
            {
                "speaker": "あなた",
                "text": "(もう戻れない)"
            },
            {
                "speaker": "幻影",
                "text": "そうか。ならば、祝福を"
            },
            {
                "speaker": "ナレーション",
                "text": "幻影は消えた。"
            }
        ]
    },
    "story_6750_loop5": {
        "title": "道の分裂",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "道が二つ、四つ、八つ…無数に分かれていく。"
            },
            {
                "speaker": "???",
                "text": "五度死ねば、道も分からなくなる"
            },
            {
                "speaker": "あなた",
                "text": "(どれが…正しい…？)"
            },
            {
                "speaker": "???",
                "text": "全てだ。そして、どれでもない"
            },
            {
                "speaker": "ナレーション",
                "text": "やがて、道は一つに戻った。"
            }
        ]
    },
    "story_6750_loop6": {
        "title": "決意の確認",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "分かれ道の前で、立ち止まる。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(六度死んだ。でも、進む)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "迷いはない。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_6750_loop7": {
        "title": "決意との対話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "分かれ道で、過去の自分が待っている。"
            },
            {
                "speaker": "過去の自分",
                "text": "七度目…本当に進むのか？"
            },
            {
                "speaker": "あなた",
                "text": "(あなたのため、だ)"
            },
            {
                "speaker": "過去の自分",
                "text": "…ありがとう。行ってくれ"
            },
            {
                "speaker": "ナレーション",
                "text": "幻影は微笑んで消えた。"
            }
        ]
    },
    "story_6750_loop8": {
        "title": "決意の理由",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "分かれ道に、文字が刻まれている。"
            },
            {
                "speaker": "古代文字",
                "text": "「なぜ進む？八度も死んだのに」"
            },
            {
                "speaker": "あなた",
                "text": "(真実を知りたいから)"
            },
            {
                "speaker": "古代文字",
                "text": "「それだけか？」"
            },
            {
                "speaker": "あなた",
                "text": "(…それだけだ)"
            }
        ]
    },
    "story_6750_loop9": {
        "title": "決意の完成",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "分かれ道が、一つの道に変わる。"
            },
            {
                "speaker": "???",
                "text": "九度目…もう迷わないのだな"
            },
            {
                "speaker": "あなた",
                "text": "(迷う理由がない)"
            },
            {
                "speaker": "ナレーション",
                "text": "まっすぐな道を、進む。"
            }
        ]
    },
    "story_6750_loop10": {
        "title": "決意の道",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "分かれ道は消えた。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "ただ一本の道が、前へ続いている。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "迷わず、前へ進む。"
            }
        ]
    },
    "story_7250_loop2": {
        "title": "揺らぐ境界",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "境界線が揺らいでいる。"
            },
            {
                "speaker": "???",
                "text": "二度目だ。また選ぶのか？"
            },
            {
                "speaker": "あなた",
                "text": "(前は…どちらを選んだ？)"
            },
            {
                "speaker": "???",
                "text": "忘れたのか？ならば、また選べ"
            }
        ]
    },
    "story_7250_loop3": {
        "title": "境界の痕跡",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "境界線上に、血の足跡がある。"
            },
            {
                "speaker": "あなた",
                "text": "(これは…私の…)"
            },
            {
                "speaker": "血文字",
                "text": "どちらも同じ"
            },
            {
                "speaker": "ナレーション",
                "text": "足跡は、両方の道に続いている。"
            }
        ]
    },
    "story_7250_loop4": {
        "title": "境界の記憶",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "境界線の前で、幻影が二つ現れる。"
            },
            {
                "speaker": "光の幻影",
                "text": "こちらへ…"
            },
            {
                "speaker": "闇の幻影",
                "text": "いや、こちらへ…"
            },
            {
                "speaker": "あなた",
                "text": "(四度目…どちらを…)"
            }
        ]
    },
    "story_7250_loop5": {
        "title": "境界の崩壊",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "境界線が、波打ち始める。"
            },
            {
                "speaker": "ナレーション",
                "text": "光が闇に。闇が光に。"
            },
            {
                "speaker": "???",
                "text": "五度死ねば、境界も曖昧になる"
            },
            {
                "speaker": "あなた",
                "text": "(どちらが…現実…？)"
            },
            {
                "speaker": "ナレーション",
                "text": "やがて、境界は元に戻った。"
            }
        ]
    },
    "story_7250_loop6": {
        "title": "境界の真実",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "境界線が消える。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "???",
                "text": "六度目にして気づいたか"
            },
            {
                "speaker": "???",
                "text": "光も闇も、同じものだと"
            },
            {
                "speaker": "あなた",
                "text": "(どちらでも…いい…)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_7250_loop7": {
        "title": "境界との対話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "境界線の前で、過去の自分が立っている。"
            },
            {
                "speaker": "過去の自分",
                "text": "七度目…まだ選べないのか？"
            },
            {
                "speaker": "あなた",
                "text": "(もう選ばない。どちらも同じだから)"
            },
            {
                "speaker": "過去の自分",
                "text": "正解だ"
            },
            {
                "speaker": "ナレーション",
                "text": "幻影は消えた。"
            }
        ]
    },
    "story_7250_loop8": {
        "title": "境界の問いかけ",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "境界線が質問する。"
            },
            {
                "speaker": "???",
                "text": "光と闇、どちらが真実だ？"
            },
            {
                "speaker": "あなた",
                "text": "(…どちらでもない)"
            },
            {
                "speaker": "???",
                "text": "では何が真実だ？"
            },
            {
                "speaker": "あなた",
                "text": "(進むこと、だ)"
            }
        ]
    },
    "story_7250_loop9": {
        "title": "境界の統合",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "光と闇が混ざり合い、灰色の道になる。"
            },
            {
                "speaker": "???",
                "text": "九度目…統合されたな"
            },
            {
                "speaker": "あなた",
                "text": "(もう…迷わない)"
            },
            {
                "speaker": "ナレーション",
                "text": "灰色の道を、進む。"
            }
        ]
    },
    "story_7250_loop10": {
        "title": "境界の消滅",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "境界線が完全に消えた。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "光も闇もない。ただの道だ。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "その道を、ただ前へ進む。"
            }
        ]
    },
    "story_7750_loop2": {
        "title": "戦いの記憶",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "戦いの痕跡が…前より深くなっている。"
            },
            {
                "speaker": "あなた",
                "text": "(ここで…戦った記憶が…)"
            },
            {
                "speaker": "???",
                "text": "二度戦った。二度負けた"
            },
            {
                "speaker": "ナレーション",
                "text": "血痕が、壁を這っている。"
            }
        ]
    },
    "story_7750_loop3": {
        "title": "戦いの再現",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "突然、過去の戦いが幻影となって再生される。"
            },
            {
                "speaker": "あなた",
                "text": "(これは…私が…戦っている…)"
            },
            {
                "speaker": "ナレーション",
                "text": "そして、死ぬ。"
            },
            {
                "speaker": "ナレーション",
                "text": "幻影は消えた。"
            }
        ]
    },
    "story_7750_loop4": {
        "title": "戦いの敵",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "幻影の中で、敵の姿が見える。"
            },
            {
                "speaker": "あなた",
                "text": "(あれは…誰だ…？)"
            },
            {
                "speaker": "???",
                "text": "お前だ"
            },
            {
                "speaker": "あなた",
                "text": "(…私が、私と戦った？)"
            },
            {
                "speaker": "???",
                "text": "四度もな"
            }
        ]
    },
    "story_7750_loop5": {
        "title": "戦いの連鎖",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "幻影が無数に現れ、全員が戦い始める。"
            },
            {
                "speaker": "ナレーション",
                "text": "自分vs自分。自分vs自分。自分vs自分。"
            },
            {
                "speaker": "???",
                "text": "五度戦い、五度死んだ"
            },
            {
                "speaker": "あなた",
                "text": "(なぜ…私は私と…)"
            },
            {
                "speaker": "ナレーション",
                "text": "やがて、幻影は消えた。"
            }
        ]
    },
    "story_7750_loop6": {
        "title": "戦いの真実",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "最後の幻影が、こちらを見つめる。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "過去の自分",
                "text": "分かったか？"
            },
            {
                "speaker": "過去の自分",
                "text": "敵は、いつも自分自身だった"
            },
            {
                "speaker": "あなた",
                "text": "(…なぜ？)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_7750_loop7": {
        "title": "戦いとの和解",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "幻影の自分が、手を差し伸べる。"
            },
            {
                "speaker": "過去の自分",
                "text": "七度目…もう戦わなくていい"
            },
            {
                "speaker": "あなた",
                "text": "(…ありがとう)"
            },
            {
                "speaker": "ナレーション",
                "text": "手を取る。幻影は微笑んで消えた。"
            }
        ]
    },
    "story_7750_loop8": {
        "title": "戦いの問いかけ",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "戦いの痕跡が、文字を形作る。"
            },
            {
                "speaker": "血文字",
                "text": "なぜ自分と戦った？"
            },
            {
                "speaker": "あなた",
                "text": "(…分からない)"
            },
            {
                "speaker": "血文字",
                "text": "ならば進め。答えは最深部に"
            },
            {
                "speaker": "あなた",
                "text": "(…必ず)"
            }
        ]
    },
    "story_7750_loop9": {
        "title": "戦いの終焉",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "戦いの痕跡が、静かに消えていく。"
            },
            {
                "speaker": "???",
                "text": "九度目…もう戦う必要はない"
            },
            {
                "speaker": "あなた",
                "text": "(もう…終わりにする)"
            },
            {
                "speaker": "ナレーション",
                "text": "部屋が、元の静けさを取り戻す。"
            }
        ]
    },
    "story_7750_loop10": {
        "title": "戦いの浄化",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "全ての痕跡が消えた。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "部屋は、真っ白だ。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "浄化された部屋を出て、前へ進む。"
            }
        ]
    },
    "story_8250_loop2": {
        "title": "広がるひび",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "ひび割れが…前より大きくなっている。"
            },
            {
                "speaker": "あなた",
                "text": "(前にも…ここに…)"
            },
            {
                "speaker": "???",
                "text": "二度目だ。また崩れる"
            },
            {
                "speaker": "ナレーション",
                "text": "石が、一つ落ちてきた。"
            }
        ]
    },
    "story_8250_loop3": {
        "title": "崩壊の予兆",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "岩盤が軋む音がする。"
            },
            {
                "speaker": "あなた",
                "text": "(もう…限界…)"
            },
            {
                "speaker": "???",
                "text": "三度目。お前が来るたびに崩れる"
            },
            {
                "speaker": "ナレーション",
                "text": "大きな石が、落ちてきた。"
            }
        ]
    },
    "story_8250_loop4": {
        "title": "岩盤の崩壊",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "岩盤が崩れ始める。"
            },
            {
                "speaker": "???",
                "text": "四度目…また始まるぞ…"
            },
            {
                "speaker": "あなた",
                "text": "(私のせい…？)"
            },
            {
                "speaker": "???",
                "text": "いや、元から壊れていた"
            },
            {
                "speaker": "ナレーション",
                "text": "崩壊が止まった。"
            }
        ]
    },
    "story_8250_loop5": {
        "title": "時間の逆行",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "崩れた岩盤が、元に戻り始める。"
            },
            {
                "speaker": "ナレーション",
                "text": "落ちた石が、天井に戻っていく。"
            },
            {
                "speaker": "???",
                "text": "五度死ねば、時間も戻る"
            },
            {
                "speaker": "あなた",
                "text": "(時間が…逆に…)"
            },
            {
                "speaker": "ナレーション",
                "text": "やがて、時間は正常に戻った。"
            }
        ]
    },
    "story_8250_loop6": {
        "title": "崩壊の真実",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "岩盤が完全に崩壊する。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "だが、落ちてこない。空中で止まっている。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "???",
                "text": "六度目。もう現実じゃない"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_8250_loop7": {
        "title": "崩壊との対話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "空中の岩が、過去の自分の形を作る。"
            },
            {
                "speaker": "過去の自分",
                "text": "七度目…崩壊が怖くないのか？"
            },
            {
                "speaker": "あなた",
                "text": "(もう慣れた)"
            },
            {
                "speaker": "過去の自分",
                "text": "そうか…ならば行け"
            },
            {
                "speaker": "ナレーション",
                "text": "岩は崩れ落ちた。"
            }
        ]
    },
    "story_8250_loop8": {
        "title": "崩壊の問いかけ",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "崩れた岩が、文字を形作る。"
            },
            {
                "speaker": "岩文字",
                "text": "なぜ崩れる？"
            },
            {
                "speaker": "あなた",
                "text": "(…この世界が偽物だから)"
            },
            {
                "speaker": "岩文字",
                "text": "正解。ならば進め"
            },
            {
                "speaker": "ナレーション",
                "text": "岩は消えた。"
            }
        ]
    },
    "story_8250_loop9": {
        "title": "崩壊の終わり",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "岩盤が完全に修復される。"
            },
            {
                "speaker": "???",
                "text": "九度目…もう崩れない"
            },
            {
                "speaker": "あなた",
                "text": "(もうすぐ…全てが終わる)"
            },
            {
                "speaker": "ナレーション",
                "text": "天井は、完璧だ。"
            }
        ]
    },
    "story_8250_loop10": {
        "title": "崩壊の静寂",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "岩盤は、もう崩れない。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "完全な安定。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "安定した部屋を出て、前へ進む。"
            }
        ]
    },
    "story_8750_loop2": {
        "title": "不穏な静寂",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "静寂が…前より重い。"
            },
            {
                "speaker": "あなた",
                "text": "(この感覚…前にも…)"
            },
            {
                "speaker": "???",
                "text": "二度目だ。また来たのか"
            },
            {
                "speaker": "ナレーション",
                "text": "空気が、張り詰めている。"
            }
        ]
    },
    "story_8750_loop3": {
        "title": "静寂の痕跡",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "部屋の隅に、血痕がある。"
            },
            {
                "speaker": "あなた",
                "text": "(これは…)"
            },
            {
                "speaker": "血文字",
                "text": "ここで待った 三度"
            },
            {
                "speaker": "ナレーション",
                "text": "誰かが、ここで覚悟を決めた。"
            }
        ]
    },
    "story_8750_loop4": {
        "title": "静寂の記憶",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "部屋の中央に、幻影が座っている。"
            },
            {
                "speaker": "幻影",
                "text": "四度目…またここで待つのか？"
            },
            {
                "speaker": "あなた",
                "text": "(待つ必要はない)"
            },
            {
                "speaker": "幻影",
                "text": "そうか…ならば行け"
            },
            {
                "speaker": "ナレーション",
                "text": "幻影は消えた。"
            }
        ]
    },
    "story_8750_loop5": {
        "title": "静寂の歪み",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "静寂が音を持ち始める。"
            },
            {
                "speaker": "ナレーション",
                "text": "ザワザワ…ザワザワ…"
            },
            {
                "speaker": "???",
                "text": "五度目…静寂さえ歪む…"
            },
            {
                "speaker": "あなた",
                "text": "(何の…音…？)"
            },
            {
                "speaker": "ナレーション",
                "text": "やがて、音は消えた。"
            }
        ]
    },
    "story_8750_loop6": {
        "title": "静寂の決意",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "部屋で、静かに立ち止まる。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(六度死んだ。でも、進む)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "覚悟は、決まっている。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_8750_loop7": {
        "title": "静寂との対話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "静寂の中で、過去の自分が現れる。"
            },
            {
                "speaker": "過去の自分",
                "text": "七度目…怖くないのか？"
            },
            {
                "speaker": "あなた",
                "text": "(怖い。でも、進む)"
            },
            {
                "speaker": "過去の自分",
                "text": "…強いな。行ってくれ"
            },
            {
                "speaker": "ナレーション",
                "text": "幻影は消えた。"
            }
        ]
    },
    "story_8750_loop8": {
        "title": "静寂の問いかけ",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "静寂が、問いかける。"
            },
            {
                "speaker": "静寂",
                "text": "最深部で、何を見る？"
            },
            {
                "speaker": "あなた",
                "text": "(…真実を)"
            },
            {
                "speaker": "静寂",
                "text": "覚悟はあるか？"
            },
            {
                "speaker": "あなた",
                "text": "(ある)"
            }
        ]
    },
    "story_8750_loop9": {
        "title": "静寂の祝福",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "静寂が、柔らかくなる。"
            },
            {
                "speaker": "???",
                "text": "九度目…よくぞここまで…"
            },
            {
                "speaker": "あなた",
                "text": "(もう…すぐそこだ)"
            },
            {
                "speaker": "ナレーション",
                "text": "静寂が、背中を押してくれる。"
            }
        ]
    },
    "story_8750_loop10": {
        "title": "静寂の完成",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "完全な静寂。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "全てが、静まり返っている。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "静寂の中、最後の一歩を踏み出す。"
            }
        ]
    },
    "story_9250_loop2": {
        "title": "魔王の気配",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "気配が…前より強くなっている。"
            },
            {
                "speaker": "あなた",
                "text": "(前にも…感じた…)"
            },
            {
                "speaker": "魔王の声",
                "text": "また来たのか…"
            },
            {
                "speaker": "ナレーション",
                "text": "声が、四方から響く。"
            }
        ]
    },
    "story_9250_loop3": {
        "title": "魔王の痕跡",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "床に、巨大な爪痕がある。"
            },
            {
                "speaker": "あなた",
                "text": "(これは…戦った跡…)"
            },
            {
                "speaker": "血文字",
                "text": "三度 負けた"
            },
            {
                "speaker": "ナレーション",
                "text": "血痕が、爪痕を埋めている。"
            }
        ]
    },
    "story_9250_loop4": {
        "title": "魔王の幻影",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "暗闇の中に、巨大な影が見える。"
            },
            {
                "speaker": "魔王",
                "text": "四度目…か。学習が遅いな"
            },
            {
                "speaker": "あなた",
                "text": "(今度は…勝つ)"
            },
            {
                "speaker": "魔王",
                "text": "ほう…？では来い"
            },
            {
                "speaker": "ナレーション",
                "text": "影は消えた。"
            }
        ]
    },
    "story_9250_loop5": {
        "title": "魔王の笑い声",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "笑い声が響く。低く、不気味に。"
            },
            {
                "speaker": "魔王",
                "text": "ハハハ…五度目…五度目…"
            },
            {
                "speaker": "ナレーション",
                "text": "笑い声が重なり、不協和音になる。"
            },
            {
                "speaker": "あなた",
                "text": "(笑っていられるのも…今のうちだ)"
            },
            {
                "speaker": "ナレーション",
                "text": "やがて、笑い声は止んだ。"
            }
        ]
    },
    "story_9250_loop6": {
        "title": "魔王の正体",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "暗闇の中に、魔王の姿がはっきりと見える。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "魔王",
                "text": "六度目…よく来たな"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(あなたが…全ての元凶…)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_9250_loop7": {
        "title": "魔王との対話",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "魔王が、ゆっくりと近づいてくる。"
            },
            {
                "speaker": "魔王",
                "text": "七度目…強くなったな"
            },
            {
                "speaker": "あなた",
                "text": "(あなたを倒すために)"
            },
            {
                "speaker": "魔王",
                "text": "では問おう。私を倒して、何が変わる？"
            },
            {
                "speaker": "あなた",
                "text": "(…全てが)"
            }
        ]
    },
    "story_9250_loop8": {
        "title": "魔王の問いかけ",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "魔王が、最後の質問をする。"
            },
            {
                "speaker": "魔王",
                "text": "私が誰だか、分かるか？"
            },
            {
                "speaker": "あなた",
                "text": "(…この世界を作った者)"
            },
            {
                "speaker": "魔王",
                "text": "半分正解だ。では、もう半分は？"
            },
            {
                "speaker": "あなた",
                "text": "(それは…最深部で知る)"
            }
        ]
    },
    "story_9250_loop9": {
        "title": "魔王の認識",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "魔王が、静かに頷く。"
            },
            {
                "speaker": "魔王",
                "text": "九度目…よくぞここまで来た"
            },
            {
                "speaker": "あなた",
                "text": "(もう…すぐそこだ)"
            },
            {
                "speaker": "魔王",
                "text": "ならば来い。最深部で待っている"
            },
            {
                "speaker": "ナレーション",
                "text": "魔王の気配が消える。"
            }
        ]
    },
    "story_9250_loop10": {
        "title": "魔王の静寂",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "魔王の気配が完全に消えた。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "だが、確かにいる。最深部に。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "最後の道を、ただ前へ進む。"
            }
        ]
    },
    "story_9750_loop2": {
        "title": "既知の扉",
        "loop_requirement": 2,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉が…前より大きく見える。"
            },
            {
                "speaker": "あなた",
                "text": "(前にも…ここまで来た…)"
            },
            {
                "speaker": "???",
                "text": "二度目だ。また開けるのか？"
            },
            {
                "speaker": "あなた",
                "text": "(当然だ)"
            }
        ]
    },
    "story_9750_loop3": {
        "title": "扉の前の祈り",
        "loop_requirement": 3,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉の前に、血文字で書かれた祈りがある。"
            },
            {
                "speaker": "血文字",
                "text": "三度目 どうか成功を"
            },
            {
                "speaker": "あなた",
                "text": "(これは…過去の私の…)"
            },
            {
                "speaker": "ナレーション",
                "text": "祈りは、聞き届けられなかった。"
            }
        ]
    },
    "story_9750_loop4": {
        "title": "扉の記憶",
        "loop_requirement": 4,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉の前で、幻影が立っている。"
            },
            {
                "speaker": "過去の自分",
                "text": "四度目…また挑むのか？"
            },
            {
                "speaker": "あなた",
                "text": "(あなたの分まで)"
            },
            {
                "speaker": "過去の自分",
                "text": "…ありがとう。頼んだ"
            },
            {
                "speaker": "ナレーション",
                "text": "幻影は消えた。"
            }
        ]
    },
    "story_9750_loop5": {
        "title": "扉の震え",
        "loop_requirement": 5,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉が微かに震えている。"
            },
            {
                "speaker": "ナレーション",
                "text": "開く。閉じる。開く。閉じる。"
            },
            {
                "speaker": "???",
                "text": "五度…何度開けた？何度閉じた？"
            },
            {
                "speaker": "あなた",
                "text": "(もう数えない。ただ開ける)"
            },
            {
                "speaker": "ナレーション",
                "text": "扉は止まった。"
            }
        ]
    },
    "story_9750_loop6": {
        "title": "扉の真実",
        "loop_requirement": 6,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉に、文字が浮かび上がる。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "古代文字",
                "text": "「六度目の挑戦者よ。この先に真実がある」"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "あなた",
                "text": "(覚悟は…できている)"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            }
        ]
    },
    "story_9750_loop7": {
        "title": "扉との別れ",
        "loop_requirement": 7,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉の前で、全ての過去の自分が現れる。"
            },
            {
                "speaker": "過去の自分たち",
                "text": "七度目…頼む…終わらせてくれ…"
            },
            {
                "speaker": "あなた",
                "text": "(…必ず)"
            },
            {
                "speaker": "過去の自分たち",
                "text": "信じている"
            },
            {
                "speaker": "ナレーション",
                "text": "幻影たちは微笑んで消えた。"
            }
        ]
    },
    "story_9750_loop8": {
        "title": "扉の問いかけ",
        "loop_requirement": 8,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉が、最後の質問をする。"
            },
            {
                "speaker": "扉",
                "text": "真実を知って、後悔しないか？"
            },
            {
                "speaker": "あなた",
                "text": "(後悔しない)"
            },
            {
                "speaker": "扉",
                "text": "では行け。八度目の挑戦者よ"
            },
            {
                "speaker": "ナレーション",
                "text": "扉が、ゆっくりと開き始める。"
            }
        ]
    },
    "story_9750_loop9": {
        "title": "扉の祝福",
        "loop_requirement": 9,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉が金色に輝く。"
            },
            {
                "speaker": "扉",
                "text": "九度目…よくぞここまで来た"
            },
            {
                "speaker": "あなた",
                "text": "(全ての自分が…待っている)"
            },
            {
                "speaker": "扉",
                "text": "全てを終わらせろ。この実験を"
            },
            {
                "speaker": "ナレーション",
                "text": "扉が完全に開く。"
            }
        ]
    },
    "story_9750_loop10": {
        "title": "最後の一歩",
        "loop_requirement": 10,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "扉の向こうに、光が見える。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "十度目の挑戦。これが最後。"
            },
            {
                "speaker": "ナレーション",
                "text": ""
            },
            {
                "speaker": "ナレーション",
                "text": "深く息を吸い、最後の一歩を踏み出す。"
            }
        ]
    },
    "boss_pre_1": {
        "title": "第一の試練",
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
        "loop_requirement": 0,
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
    "story_250_loop1": {
        "title": "壁に刻まれた謎",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "壁一面に、見たこともない文字が刻まれている。"
            },
            {
                "speaker": "古代文字",
                "text": "「始まりは終わり、終わりは始まり」"
            },
            {
                "speaker": "あなた",
                "text": "(これは…何の意味だ？)"
            }
        ]
    },
    "story_750_loop1": {
        "title": "死者の山",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "部屋の中央に、無数の骸骨が山のように積まれている。"
            },
            {
                "speaker": "あなた",
                "text": "(こんなに…多くの冒険者が…)"
            },
            {
                "speaker": "???",
                "text": "お前も…仲間入りするのか…"
            }
        ]
    },
    "story_1250_loop1": {
        "title": "洞窟の隠者",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "薄暗い部屋の隅に、老人が座っている。"
            },
            {
                "speaker": "老人",
                "text": "ほう…久しぶりに客人か…"
            },
            {
                "speaker": "あなた",
                "text": "(この人は…何者だ？)"
            }
        ]
    },
    "story_1750_loop1": {
        "title": "助けを求める声",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "暗闇の奥から、か細い声が聞こえる。"
            },
            {
                "speaker": "謎の声",
                "text": "誰か…助けて…"
            },
            {
                "speaker": "あなた",
                "text": "(誰だ…？この声は…)"
            }
        ]
    },
    "story_2250_loop1": {
        "title": "忘れられた日記",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "床に散乱した日記を見つける。インクは古びている。"
            },
            {
                "speaker": "日記",
                "text": "「100日目。もう戻れないことは分かっている」"
            },
            {
                "speaker": "あなた",
                "text": "(誰の…記録だろう？)"
            }
        ]
    },
    "story_2750_loop1": {
        "title": "鏡に映る自分",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "部屋の中央に大きな鏡が立っている。"
            },
            {
                "speaker": "鏡の中の自分",
                "text": "…"
            },
            {
                "speaker": "あなた",
                "text": "(ただの…鏡か？)"
            }
        ]
    },
    "story_3250_loop1": {
        "title": "巨大な扉",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "部屋の奥に、巨大な扉が立っている。"
            },
            {
                "speaker": "古代文字",
                "text": "「封印。開くなかれ」"
            },
            {
                "speaker": "あなた",
                "text": "(何が…封印されている？)"
            }
        ]
    },
    "story_3750_loop1": {
        "title": "囁き声",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "無数の囁き声が、四方八方から聞こえる。"
            },
            {
                "speaker": "囁き声",
                "text": "進むな…戻れ…"
            },
            {
                "speaker": "あなた",
                "text": "(誰の…声だ？)"
            }
        ]
    },
    "story_4250_loop1": {
        "title": "下り続ける階段",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "延々と続く階段。底が見えない。"
            },
            {
                "speaker": "あなた",
                "text": "(どこまで…続くんだ？)"
            },
            {
                "speaker": "???",
                "text": "永遠に…"
            }
        ]
    },
    "story_4750_loop1": {
        "title": "青く光る泉",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "部屋の中央に、青く光る泉がある。"
            },
            {
                "speaker": "あなた",
                "text": "(美しい…だが、不気味だ)"
            },
            {
                "speaker": "???",
                "text": "飲むか…？"
            }
        ]
    },
    "story_5250_loop1": {
        "title": "揺れる大地",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "突然、地面が揺れ始めた。"
            },
            {
                "speaker": "あなた",
                "text": "(地震…？)"
            },
            {
                "speaker": "???",
                "text": "崩れ始めている…この世界が…"
            }
        ]
    },
    "story_5750_loop1": {
        "title": "光る石板",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "部屋の中央に、光る石板が立っている。"
            },
            {
                "speaker": "石板",
                "text": "「真実を知りたいか？」"
            },
            {
                "speaker": "あなた",
                "text": "(…知りたい)"
            }
        ]
    },
    "story_6250_loop1": {
        "title": "狂気の壁",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "壁一面に、血文字で書かれた文章がある。"
            },
            {
                "speaker": "血文字",
                "text": "「助けて 助けて 助けて 助けて」"
            },
            {
                "speaker": "あなた",
                "text": "(誰が…書いた…？)"
            }
        ]
    },
    "story_6750_loop1": {
        "title": "分かれ道",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "道が二つに分かれている。"
            },
            {
                "speaker": "???",
                "text": "戻るか？進むか？"
            },
            {
                "speaker": "あなた",
                "text": "(…進む)"
            }
        ]
    },
    "story_7250_loop1": {
        "title": "境界線",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "部屋の中央に、光と闇の境界線がある。"
            },
            {
                "speaker": "あなた",
                "text": "(どちらに…進めばいい？)"
            },
            {
                "speaker": "???",
                "text": "選べ"
            }
        ]
    },
    "story_7750_loop1": {
        "title": "戦いの痕跡",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "部屋に、激しい戦いの痕跡がある。"
            },
            {
                "speaker": "あなた",
                "text": "(ここで…誰かが戦った…)"
            },
            {
                "speaker": "???",
                "text": "お前だよ"
            }
        ]
    },
    "story_8250_loop1": {
        "title": "ひび割れた岩盤",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "天井の岩盤に、大きなひび割れがある。"
            },
            {
                "speaker": "あなた",
                "text": "(崩れそう…)"
            },
            {
                "speaker": "???",
                "text": "崩れる。もうすぐ"
            }
        ]
    },
    "story_8750_loop1": {
        "title": "静寂の部屋",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "何もない部屋。完全な静寂。"
            },
            {
                "speaker": "あなた",
                "text": "(嵐の前の…静けさ…)"
            },
            {
                "speaker": "???",
                "text": "その通りだ"
            }
        ]
    },
    "story_9250_loop1": {
        "title": "暗黒の気配",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "空気が重い。圧倒的な気配を感じる。"
            },
            {
                "speaker": "あなた",
                "text": "(何かが…いる…)"
            },
            {
                "speaker": "???",
                "text": "魔王だ"
            }
        ]
    },
    "story_9750_loop1": {
        "title": "最深部の入口",
        "loop_requirement": 1,
        "lines": [
            {
                "speaker": "ナレーション",
                "text": "巨大な扉が、目の前にある。"
            },
            {
                "speaker": "あなた",
                "text": "(これが…最後…)"
            },
            {
                "speaker": "???",
                "text": "開けるか？"
            }
        ]
    }
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
        self.current_page = 0

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

            await interaction.response.edit_message(embed=embed, view=None)

            # 現ストーリーは既読扱いにする（従来互換）
            await db.set_story_flag(self.user_id, self.story_id)

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
