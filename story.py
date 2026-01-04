import discord
from discord.ui import View, button
import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("rpgbot")


_EXTERNAL_STORIES_CACHE: Optional[dict[str, Any]] = None


def validate_external_story_files(*, strict: bool = False) -> bool:
    """Validate external story JSON files at startup.

    - Checks JSON parse
    - Checks top-level structure: {"stories": {story_id: {...}}}
    - Minimal type checks for each story definition

    By default (strict=False), logs errors and returns False.
    In strict mode, raises ValueError on any error.
    """

    errors: list[str] = []
    base_dir = Path(__file__).resolve().parent

    paths: list[Path] = []
    top = base_dir / "stories.json"
    if top.exists():
        paths.append(top)
    stories_dir = base_dir / "stories"
    if stories_dir.exists() and stories_dir.is_dir():
        paths.extend(sorted(stories_dir.glob("*.json")))

    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"{path}: JSON parse failed: {e}")
            continue

        if not isinstance(data, dict):
            errors.append(f"{path}: top-level must be an object")
            continue

        stories = data.get("stories")
        if not isinstance(stories, dict):
            errors.append(f"{path}: top-level 'stories' must be an object")
            continue

        for story_id, story_def in stories.items():
            if not isinstance(story_id, str) or not story_id:
                errors.append(f"{path}: story id must be non-empty string")
                continue
            if not isinstance(story_def, dict):
                errors.append(f"{path}: story '{story_id}' must be an object")
                continue

            nodes = story_def.get("nodes")
            lines = story_def.get("lines")
            if nodes is None and lines is None:
                # allow empty story, but warn
                errors.append(f"{path}: story '{story_id}' must have 'nodes' or 'lines'")
                continue

            if nodes is not None and not isinstance(nodes, dict):
                errors.append(f"{path}: story '{story_id}': 'nodes' must be an object")
                continue

            if lines is not None and not isinstance(lines, list):
                errors.append(f"{path}: story '{story_id}': 'lines' must be a list")
                continue

            if isinstance(nodes, dict):
                for node_id, node_def in nodes.items():
                    if not isinstance(node_id, str) or not node_id:
                        errors.append(f"{path}: story '{story_id}': node id must be string")
                        continue
                    if not isinstance(node_def, dict):
                        errors.append(f"{path}: story '{story_id}': node '{node_id}' must be an object")
                        continue
                    node_lines = node_def.get("lines")
                    if node_lines is not None and not isinstance(node_lines, list):
                        errors.append(f"{path}: story '{story_id}': node '{node_id}': 'lines' must be a list")

    if errors:
        logger.error("❌ Story validation failed (%s issues)", len(errors))
        for msg in errors:
            logger.error(" - %s", msg)
        if strict:
            raise ValueError("Story validation failed; see logs")
        return False

    logger.info("✅ Story validation OK (%s files)", len(paths))
    return True


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

STORY_DATA = {}  # moved to stories/_builtin_stories.json

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

            # 先に既読フラグを立てる（メッセージ編集失敗で二重表示になるのを防ぐ）
            try:
                await db.set_story_flag(self.user_id, self.story_id)
            except Exception:
                # 既読フラグの失敗は致命ではないが、ここで落ちると選択肢が再表示されやすい
                logger.exception("set_story_flag failed story_id=%s user_id=%s", self.story_id, self.user_id)

            # 結果表示（Interactionの状態により edit_message が失敗することがあるためフォールバックする）
            try:
                await interaction.response.edit_message(embed=embed, view=None)
            except Exception:
                try:
                    if interaction.message:
                        await interaction.message.edit(embed=embed, view=None)
                except Exception:
                    pass

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
            if self.user_id in self.user_processing:
                self.user_processing[self.user_id] = False
        return callback
