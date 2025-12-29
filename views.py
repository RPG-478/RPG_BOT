"""互換レイヤー: 旧 views.py の再エクスポート。

実体は ui/ 配下へ分割済みです。既存コードの `import views` / `from views import ...`
を壊さないため、このファイルは公開シンボルを ui/*.py から再公開します。
"""

from ui.intro import NameRequestView, NameModal
from ui.storage import StorageSelectView
from ui.tutorial import TutorialView
from ui.reset import ResetConfirmView, ResetFinalConfirmView
from ui.treasure import TreasureView, TrapChestView
from ui.events import SpecialEventView, FinalBossClearView
from ui.battle import FinalBossBattleView, BossBattleView, BattleView
from ui.inventory import status_embed, InventorySelectView, EquipmentSelectView
from ui.shops import BlacksmithView, MaterialMerchantView
from ui.common import handle_death_with_triggers

__all__ = [
    "NameRequestView",
    "NameModal",
    "StorageSelectView",
    "TutorialView",
    "ResetConfirmView",
    "ResetFinalConfirmView",
    "TreasureView",
    "TrapChestView",
    "SpecialEventView",
    "FinalBossClearView",
    "FinalBossBattleView",
    "BossBattleView",
    "BattleView",
    "status_embed",
    "InventorySelectView",
    "EquipmentSelectView",
    "BlacksmithView",
    "MaterialMerchantView",
    "handle_death_with_triggers",
]
