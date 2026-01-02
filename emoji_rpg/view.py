from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import discord
from discord.ui import View, button


@dataclass
class EmojiRPGResult:
    outcome: str  # "win" | "lose" | "timeout"


def _load_map(map_id: str) -> dict[str, Any]:
    base_dir = Path(__file__).resolve().parent
    maps_dir = base_dir / "maps"
    path = maps_dir / f"{map_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("map json must be an object")
    return data


class EmojiRPGView(View):
    """11×11の絵文字RPG（最小版）。

    - JSONマップ
    - 上下左右ボタン
    - 壁衝突
    - ゴール到達で勝利
    """

    def __init__(
        self,
        *,
        user_id: int,
        map_id: str,
        on_finish: Callable[[EmojiRPGResult, discord.Interaction], Awaitable[None]],
        title: str = "ミニゲーム",
        timeout: float = 300,
    ):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.map_id = map_id
        self.on_finish = on_finish
        self.title = title

        self._map = _load_map(map_id)
        self._grid = self._parse_grid(self._map)
        self._h = len(self._grid)
        self._w = len(self._grid[0]) if self._h else 0

        self._player_x, self._player_y = self._find_start(self._grid)

        # render chars -> emojis
        legend = self._map.get("legend") if isinstance(self._map.get("legend"), dict) else {}
        self._legend = {
            "#": str(legend.get("#") or "⬛"),
            ".": str(legend.get(".") or "⬜"),
            "G": str(legend.get("G") or "🏁"),
            "S": str(legend.get("S") or "⬜"),
        }
        self._player_emoji = str(legend.get("P") or "🟦")

        self._finished = False

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

    def _render(self) -> str:
        lines: list[str] = []
        for y in range(self._h):
            row_emoji: list[str] = []
            for x in range(self._w):
                if x == self._player_x and y == self._player_y:
                    row_emoji.append(self._player_emoji)
                    continue
                ch = self._grid[y][x]
                row_emoji.append(self._legend.get(ch, "⬜"))
            lines.append("".join(row_emoji))
        return "\n".join(lines)

    def get_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"🎮 {self.title}",
            description=self._render(),
            color=discord.Color.blurple(),
        )
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
        return self._grid[y][x] != "#"

    async def _move(self, interaction: discord.Interaction, dx: int, dy: int) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これはあなたのミニゲームではありません！", ephemeral=True)
            return
        if self._finished:
            return

        nx = self._player_x + dx
        ny = self._player_y + dy
        if self._can_move_to(nx, ny):
            self._player_x, self._player_y = nx, ny

        # 勝利判定: ゴール到達
        if self._grid[self._player_y][self._player_x] == "G":
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
            await self._finish(interaction, "win")
            return

        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def on_timeout(self) -> None:
        # timeout時は interaction が無いので、ここではUIを確定できない。
        # 次にボタンが押されたときに finished 扱いにならないように、状態だけ持つ。
        self._finished = True

    @button(label="↑", style=discord.ButtonStyle.primary)
    async def up(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._move(interaction, 0, -1)

    @button(label="←", style=discord.ButtonStyle.primary)
    async def left(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._move(interaction, -1, 0)

    @button(label="→", style=discord.ButtonStyle.primary)
    async def right(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._move(interaction, 1, 0)

    @button(label="↓", style=discord.ButtonStyle.primary)
    async def down(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._move(interaction, 0, 1)
