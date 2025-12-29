"""
Exploration Event Determination Module
神関数 `!move` から切り出したイベント決定ロジック

Purpose:
- UIとロジックの分離（Discord依存を排除）
- 単体テスト可能な純粋関数化
- main.py の可読性向上

Architecture:
- EventResult: イベント結果を表すデータクラス（type + data）
- determine_event: 距離・状態から発生イベントを決定する純粋関数
- passed_through: 距離通過判定のヘルパー関数

Event Priority (高い順):
1. BOSS: 1000m毎のボス戦
2. SPECIAL: 500m毎の特殊イベント（鍛冶屋・商人）
3. STORY: 250m毎のストーリーイベント
4. CHOICE_STORY: 0.1%の選択肢分岐ストーリー
5. TRAP_CHEST: 1%のトラップ宝箱
6. CHEST: 9%の通常宝箱
7. BATTLE: 30%の敵エンカウント
8. NONE: 何もなし

Design Principles:
- Stateless: DBアクセス不要（引数で全情報を受け取る）
- Testable: 乱数以外は決定論的
- Extensible: 新イベントタイプは EventResult.type に追加するだけ
"""

import random
from dataclasses import dataclass
from typing import Optional, Dict, Any, List


@dataclass
class EventResult:
    """イベント決定の結果を表すデータクラス"""
    type: str  # "BOSS", "SPECIAL", "STORY", "CHOICE_STORY", "TRAP_CHEST", "CHEST", "BATTLE", "NONE"
    data: Dict[str, Any]  # イベント固有のパラメータ


def passed_through(previous_distance: int, current_distance: int, event_distance: int) -> bool:
    """
    前回の距離から今回の距離の間にevent_distanceを通過したか判定
    
    Args:
        previous_distance: 前回の移動後の距離
        current_distance: 今回の移動後の距離
        event_distance: イベント発生距離
    
    Returns:
        通過した場合 True
    """
    return previous_distance < event_distance <= current_distance


async def determine_event(
    current_distance: int,
    previous_distance: int,
    loop_count: int,
    story_flags: Dict[str, bool],
    available_choice_stories: List[str]
) -> EventResult:
    """
    現在の距離とプレイヤー状態から、発生すべきイベントを決定する
    
    Args:
        current_distance: 現在の総移動距離
        previous_distance: 前回の総移動距離
        loop_count: 現在の周回数
        story_flags: 既読ストーリーのフラグ辞書
        available_choice_stories: 未体験の選択肢ストーリーIDリスト
    
    Returns:
        EventResult: 発生するイベントの種類とパラメータ
    """
    
    # ==========================
    # 優先度1: ボス戦（1000m毎）- 最優先
    # ==========================
    boss_distances = [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]
    for boss_distance in boss_distances:
        if passed_through(previous_distance, current_distance, boss_distance):
            boss_stage = boss_distance // 1000
            story_id = f"boss_pre_{boss_stage}"
            
            return EventResult(
                type="BOSS",
                data={
                    "boss_stage": boss_stage,
                    "boss_distance": boss_distance,
                    "story_id": story_id,
                    "story_shown": story_flags.get(story_id, False)
                }
            )
    
    # ==========================
    # 優先度2: 500m毎の特殊イベント（鍛冶屋・商人・レイドボス・ストーリー）
    # ==========================
    special_distances = [500, 1500, 2500, 3500, 4500, 5500, 6500, 7500, 8500, 9500]
    for special_distance in special_distances:
        if passed_through(previous_distance, current_distance, special_distance):
            return EventResult(
                type="SPECIAL",
                data={"special_distance": special_distance}
            )
    
    # ==========================
    # 優先度3: 距離ベースストーリー（250m, 750m, 1250m, etc.）
    # ==========================
    story_distances = [250, 750, 1250, 1750, 2250, 2750, 3250, 3750, 4250, 4750, 
                      5250, 5750, 6250, 6750, 7250, 7750, 8250, 8750, 9250, 9750]
    for story_distance in story_distances:
        if passed_through(previous_distance, current_distance, story_distance):
            # 周回数に応じたストーリーIDを生成
            story_id = f"story_{story_distance}"
            if loop_count >= 2:
                loop_story_id = f"story_{story_distance}_loop{loop_count}"
                # 周回専用ストーリーが存在するかチェック（フラグが未設定なら新規）
                if loop_story_id not in story_flags:
                    story_id = loop_story_id
            
            # 既読チェック
            if story_id not in story_flags:
                return EventResult(
                    type="STORY",
                    data={"story_id": story_id}
                )
    
    # ==========================
    # 優先度4: 超低確率で選択肢分岐ストーリー（0.1%）
    # ==========================
    choice_story_roll = random.random() * 100
    if choice_story_roll < 0.1 and available_choice_stories:
        selected_story_id = random.choice(available_choice_stories)
        return EventResult(
            type="CHOICE_STORY",
            data={"story_id": selected_story_id}
        )
    
    # ==========================
    # 優先度5: 通常イベント抽選（60%何もなし/30%敵/9%宝箱/1%トラップ宝箱）
    # ==========================
    event_roll = random.random() * 100
    
    # 1% トラップ宝箱
    if event_roll < 1:
        return EventResult(type="TRAP_CHEST", data={})
    
    # 9% 宝箱（1～10%）
    elif event_roll < 10:
        return EventResult(type="CHEST", data={})
    
    # 30% 敵との遭遇（10～40%）
    elif event_roll < 40:
        return EventResult(type="BATTLE", data={})
    
    # ==========================
    # 何もなし（60%）
    # ==========================
    return EventResult(type="NONE", data={})
