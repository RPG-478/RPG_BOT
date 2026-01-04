from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import discord
from discord.ui import View, button


@dataclass
class EmojiRPGResult:
    outcome: str  # "win" | "lose" | "timeout"


@dataclass
class EmojiRPGObject:
    id: str
    x: int
    y: int
    emoji: str
    label: str
    action_type: str  # "talk" | "enter" | "portal" | "inspect"
    text: str = ""
    to_map: str | None = None
    to_x: int | None = None
    to_y: int | None = None


def _load_map(map_id: str) -> dict[str, Any]:
    base_dir = Path(__file__).resolve().parent
    maps_dir = base_dir / "maps"
    path = maps_dir / f"{map_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("map json must be an object")
    return data


def _validate_map_data(map_id: str, data: dict[str, Any]) -> None:
    grid = data.get("grid")
    if not isinstance(grid, list) or not grid:
        raise ValueError(f"map_id={map_id}: grid must be a non-empty list")
    if not all(isinstance(r, str) for r in grid):
        raise ValueError(f"map_id={map_id}: grid rows must be strings")

    h = len(grid)
    w = len(grid[0])
    if any(len(r) != w for r in grid):
        raise ValueError(f"map_id={map_id}: grid must be rectangular")

    # width/height は任意だが、あれば整合性をチェック
    if "width" in data:
        try:
            if int(data.get("width")) != w:
                raise ValueError(f"map_id={map_id}: width does not match grid")
        except Exception:
            raise ValueError(f"map_id={map_id}: width must be int")
    if "height" in data:
        try:
            if int(data.get("height")) != h:
                raise ValueError(f"map_id={map_id}: height does not match grid")
        except Exception:
            raise ValueError(f"map_id={map_id}: height must be int")

    # region_level（地域レベル）は任意。入れるなら1以上。
    if "region_level" in data:
        try:
            if int(data.get("region_level")) < 1:
                raise ValueError(f"map_id={map_id}: region_level must be >= 1")
        except Exception:
            raise ValueError(f"map_id={map_id}: region_level must be int")


class EmojiRPGView(View):
    """絵文字RPG（最小版 → 拡張版）。

    - JSONマップ（大マップ）
    - 上下左右ボタン
    - 周囲15×15（上下左右7マス）だけを表示
    - 近接（マンハッタン距離1以内）でアクションボタン有効化
    - セーフティゾーン外で確率エンカウント（仮: 通知のみ）
    - ゴール到達で勝利
    """

    def __init__(
        self,
        *,
        user_id: int,
        map_id: str,
        on_finish: Callable[[EmojiRPGResult, discord.Interaction], Awaitable[None]],
        on_encounter: Callable[[discord.Interaction], Awaitable[None]] | None = None,
        title: str = "ミニゲーム",
        timeout: float = 300,
    ):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.map_id = map_id
        self.on_finish = on_finish
        self.on_encounter = on_encounter
        self.title = title

        self._map = _load_map(map_id)
        _validate_map_data(map_id, self._map)
        self._grid = self._parse_grid(self._map)
        self._h = len(self._grid)
        self._w = len(self._grid[0]) if self._h else 0

        self._player_x, self._player_y = self._find_start(self._grid)

        # 地域レベル（敵の強さ抽選に使用）
        try:
            self.region_level = int(self._map.get("region_level", 1) or 1)
        except Exception:
            self.region_level = 1
        if self.region_level < 1:
            self.region_level = 1

        # 近接オブジェクト
        self._objects = self._parse_objects(self._map)
        self._near_object: EmojiRPGObject | None = None

        # エンカウント設定
        self._encounter_chance = self._parse_encounter_chance(self._map)
        self._safe_rects = self._parse_safe_rects(self._map)

        # render chars -> emojis
        legend = self._map.get("legend") if isinstance(self._map.get("legend"), dict) else {}
        self._legend = {
            "#": str(legend.get("#") or "⬛"),
            ".": str(legend.get(".") or "⬜"),
            "G": str(legend.get("G") or "🏁"),
            "S": str(legend.get("S") or "⬜"),
            # Bridge: black-looking but walkable (see _can_move_to)
            "B": str(legend.get("B") or "⬛"),
        }
        self._player_emoji = str(legend.get("P") or "🟦")

        # ビューポート（上下左右7マス = 15×15）
        self._view_radius = 7

        self._finished = False

        # 初期状態のアクションボタン更新
        self._refresh_near_object_and_buttons()

    @staticmethod
    def _parse_grid(map_data: dict[str, Any]) -> list[list[str]]:
        grid = map_data.get("grid")
        if not isinstance(grid, list) or not grid:
            raise ValueError("map.grid must be a non-empty list")
        rows: list[list[str]] = []
        for row in grid:
            if not isinstance(row, str):
                raise ValueError("map.grid rows must be strings")
            rows.append(list(row))
        width = len(rows[0])
        if any(len(r) != width for r in rows):
            raise ValueError("map.grid must be rectangular")
        return rows

    @staticmethod
    def _find_start(grid: list[list[str]]) -> tuple[int, int]:
        for y, row in enumerate(grid):
            for x, ch in enumerate(row):
                if ch == "S":
                    return x, y
        return 0, 0

    @staticmethod
    def _parse_objects(map_data: dict[str, Any]) -> list[EmojiRPGObject]:
        raw = map_data.get("objects")
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise ValueError("map.objects must be a list")
        out: list[EmojiRPGObject] = []
        for i, obj in enumerate(raw):
            if not isinstance(obj, dict):
                raise ValueError("map.objects entries must be objects")
            oid = str(obj.get("id") or f"obj_{i}")
            x = int(obj.get("x"))
            y = int(obj.get("y"))
            emoji = str(obj.get("emoji") or "❔")
            label = str(obj.get("label") or oid)
            action = obj.get("action") if isinstance(obj.get("action"), dict) else {}
            action_type = str(action.get("type") or "inspect")
            text = str(action.get("text") or "")
            to_map = action.get("to_map")
            to_x = action.get("to_x")
            to_y = action.get("to_y")
            out.append(
                EmojiRPGObject(
                    id=oid,
                    x=x,
                    y=y,
                    emoji=emoji,
                    label=label,
                    action_type=action_type,
                    text=text,
                    to_map=str(to_map) if to_map is not None else None,
                    to_x=int(to_x) if to_x is not None else None,
                    to_y=int(to_y) if to_y is not None else None,
                )
            )
        return out

    @staticmethod
    def _parse_encounter_chance(map_data: dict[str, Any]) -> float:
        enc = map_data.get("encounter") if isinstance(map_data.get("encounter"), dict) else {}
        enabled = bool(enc.get("enabled", False))
        if not enabled:
            return 0.0
        try:
            chance = float(enc.get("chance", 0.15))
        except (TypeError, ValueError):
            chance = 0.15
        return max(0.0, min(1.0, chance))

    @staticmethod
    def _parse_safe_rects(map_data: dict[str, Any]) -> list[tuple[int, int, int, int]]:
        enc = map_data.get("encounter") if isinstance(map_data.get("encounter"), dict) else {}
        safe = enc.get("safe_zone") if isinstance(enc.get("safe_zone"), dict) else {}
        rects = safe.get("rects")
        if rects is None:
            return []
        if not isinstance(rects, list):
            raise ValueError("encounter.safe_zone.rects must be a list")
        out: list[tuple[int, int, int, int]] = []
        for r in rects:
            if not isinstance(r, dict):
                continue
            x1 = int(r.get("x1", 0))
            y1 = int(r.get("y1", 0))
            x2 = int(r.get("x2", -1))
            y2 = int(r.get("y2", -1))
            if x2 < x1 or y2 < y1:
                continue
            out.append((x1, y1, x2, y2))
        return out

    def _is_in_safe_zone(self, x: int, y: int) -> bool:
        for x1, y1, x2, y2 in self._safe_rects:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return True
        return False

    def _find_near_object(self) -> EmojiRPGObject | None:
        best: EmojiRPGObject | None = None
        best_d = 999
        for obj in self._objects:
            d = abs(obj.x - self._player_x) + abs(obj.y - self._player_y)
            if d <= 1 and d < best_d:
                best = obj
                best_d = d
        return best

    def _refresh_near_object_and_buttons(self) -> None:
        self._near_object = self._find_near_object()
        # アクションボタンの表示/文言
        if hasattr(self, "action"):
            if self._near_object is None:
                self.action.disabled = True
                self.action.label = "ACTION"
            else:
                self.action.disabled = False
                verb = {
                    "talk": "話す",
                    "enter": "入る",
                    "portal": "移動",
                    "inspect": "調べる",
                }.get(self._near_object.action_type, "調べる")
                self.action.label = f"{verb}: {self._near_object.label}"

    def _render_viewport(self) -> str:
        # 端は中心がずれてOK: ウィンドウをマップ範囲にクランプ
        r = self._view_radius
        x0 = max(0, self._player_x - r)
        y0 = max(0, self._player_y - r)
        x1 = min(self._w, self._player_x + r + 1)
        y1 = min(self._h, self._player_y + r + 1)

        # オブジェクト座標→emoji（viewport内のみ）
        obj_map: dict[tuple[int, int], str] = {}
        for obj in self._objects:
            if x0 <= obj.x < x1 and y0 <= obj.y < y1:
                obj_map[(obj.x, obj.y)] = obj.emoji

        lines: list[str] = []
        for y in range(y0, y1):
            row_emoji: list[str] = []
            for x in range(x0, x1):
                if x == self._player_x and y == self._player_y:
                    row_emoji.append(self._player_emoji)
                    continue
                if (x, y) in obj_map:
                    row_emoji.append(obj_map[(x, y)])
                    continue
                ch = self._grid[y][x]
                row_emoji.append(self._legend.get(ch, "⬜"))
            lines.append("".join(row_emoji))
        return "\n".join(lines)

    def get_embed(self) -> discord.Embed:
        safe = self._is_in_safe_zone(self._player_x, self._player_y)
        safe_label = "SAFE" if safe else "DANGER"
        embed = discord.Embed(
            title=f"🎮 {self.title}",
            description=self._render_viewport(),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"座標: ({self._player_x},{self._player_y}) / {safe_label} / Lv{self.region_level}")
        return embed

    async def _finish(self, interaction: discord.Interaction, outcome: str) -> None:
        if self._finished:
            return
        self._finished = True
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True
        await self.on_finish(EmojiRPGResult(outcome=outcome), interaction)

    def _can_move_to(self, x: int, y: int) -> bool:
        if x < 0 or y < 0 or x >= self._w or y >= self._h:
            return False
        # "#" is wall (impassable). "B" is bridge tile (passable).
        return self._grid[y][x] != "#"

    async def _move(self, interaction: discord.Interaction, dx: int, dy: int) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これはあなたのミニゲームではありません！", ephemeral=True)
            return
        if self._finished:
            return

        nx = self._player_x + dx
        ny = self._player_y + dy
        moved = False
        if self._can_move_to(nx, ny):
            self._player_x, self._player_y = nx, ny
            moved = True

        # 近接オブジェクト更新
        self._refresh_near_object_and_buttons()

        # 勝利判定: ゴール到達
        if self._grid[self._player_y][self._player_x] == "G":
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
            await self._finish(interaction, "win")
            return

        await interaction.response.edit_message(embed=self.get_embed(), view=self)

        # セーフティゾーン外なら確率でエンカウント（仮）
        if moved and self._encounter_chance > 0 and (not self._is_in_safe_zone(self._player_x, self._player_y)):
            if random.random() < self._encounter_chance:
                if self.on_encounter is not None:
                    try:
                        await self.on_encounter(interaction)
                    except Exception:
                        pass
                else:
                    try:
                        await interaction.followup.send("⚔️ 敵とエンカウント！（仮実装）", ephemeral=True)
                    except Exception:
                        pass

    async def on_timeout(self) -> None:
        # timeout時は interaction が無いので、ここではUIを確定できない。
        # 次にボタンが押されたときに finished 扱いにならないように、状態だけ持つ。
        self._finished = True

    @button(label="ACTION", style=discord.ButtonStyle.secondary, disabled=True, row=0)
    async def action(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これはあなたのミニゲームではありません！", ephemeral=True)
            return
        if self._finished:
            return

        obj = self._near_object
        if obj is None:
            await interaction.response.send_message("近くに何もないみたい。", ephemeral=True)
            return

        # portal（地図移動）
        if obj.action_type == "portal" and obj.to_map:
            try:
                self.map_id = obj.to_map
                self._map = _load_map(obj.to_map)
                _validate_map_data(obj.to_map, self._map)
                self._grid = self._parse_grid(self._map)
                self._h = len(self._grid)
                self._w = len(self._grid[0]) if self._h else 0
                self._objects = self._parse_objects(self._map)
                self._encounter_chance = self._parse_encounter_chance(self._map)
                self._safe_rects = self._parse_safe_rects(self._map)

                try:
                    self.region_level = int(self._map.get("region_level", self.region_level) or self.region_level)
                except Exception:
                    pass
                if self.region_level < 1:
                    self.region_level = 1

                # 位置（指定があればそこへ。なければSへ）
                if obj.to_x is not None and obj.to_y is not None:
                    self._player_x = max(0, min(self._w - 1, obj.to_x))
                    self._player_y = max(0, min(self._h - 1, obj.to_y))
                else:
                    self._player_x, self._player_y = self._find_start(self._grid)

                # legend更新（マップごとに違う可能性）
                legend = self._map.get("legend") if isinstance(self._map.get("legend"), dict) else {}
                self._legend = {
                    "#": str(legend.get("#") or "⬛"),
                    ".": str(legend.get(".") or "⬜"),
                    "G": str(legend.get("G") or "🏁"),
                    "S": str(legend.get("S") or "⬜"),
                }
                self._player_emoji = str(legend.get("P") or self._player_emoji)

                self._refresh_near_object_and_buttons()
                await interaction.response.edit_message(embed=self.get_embed(), view=self)
            except Exception as e:
                await interaction.response.send_message(f"移動に失敗しました: {e}", ephemeral=True)
            return

        # talk / enter / inspect
        msg = obj.text or f"{obj.label} を{obj.action_type}（未実装）"
        await interaction.response.send_message(msg, ephemeral=True)

    @button(label="↑", style=discord.ButtonStyle.primary, row=0)
    async def up(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._move(interaction, 0, -1)

    @button(label="←", style=discord.ButtonStyle.primary, row=1)
    async def left(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._move(interaction, -1, 0)

    @button(label="↓", style=discord.ButtonStyle.primary, row=1)
    async def down(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._move(interaction, 0, 1)

    @button(label="→", style=discord.ButtonStyle.primary, row=1)
    async def right(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._move(interaction, 1, 0)
