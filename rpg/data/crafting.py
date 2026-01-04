from __future__ import annotations
MATERIAL_PRICES = {
    "蜘蛛の糸": 30,
    "腐った肉": 20,
    "悪魔の角": 40,
    "竜の牙": 50,
    "魔界の結晶": 50,
    "竜王の牙": 60,
    "古竜の心臓": 100,
    "闇の宝珠": 80,
    "地獄犬の牙": 60,
    "吸血鬼の牙": 60,
    "魔導書の欠片": 80,
    "闇の宝石": 80,
    "巨獣の皮": 80,
    "影の欠片": 100,
    "混沌の欠片": 90,
    "不死鳥の羽": 90,
    "破壊の核": 120,
    "深淵の結晶": 100,
    "元素の核": 100,
    "神の鉱石": 120,
    "闇の聖典": 110,
    "海皇の鱗": 120,
    "三首の牙": 130,
    "幻王の魂": 140,
    "竜帝の心臓": 140,
    "神殺しの結晶": 150,
    "死皇の冠": 150,
    "魔王の指輪": 500
}

CRAFTING_RECIPES = {
    "蜘蛛の短剣": {
        "materials": {"蜘蛛の糸": 2},
        "result_type": "weapon",
        "attack": 7,
        "ability": "毒付与（10%の確率で追加ダメージ）",
        "description": "蜘蛛の糸から作られた短剣。強力な毒を持つ。"
    },
    "悪魔の剣": {
        "materials": {"悪魔の角": 2, "闇の宝珠": 1},
        "result_type": "weapon",
        "attack": 15,
        "ability": "闇属性（闇の敵に+60%ダメージ）",
        "description": "悪魔の角から鍛えられた剣。邪悪な力を宿す。"
    },
    "竜牙の剣": {
        "materials": {"竜の牙": 1, "悪魔の角": 2},
        "result_type": "weapon",
        "attack": 11,
        "ability": "竜の力（全ステータス+25%）",
        "description": "竜の牙から作られた伝説の剣。"
    },
    "闇の盾": {
        "materials": {"闇の宝珠": 1, "腐った肉": 3},
        "result_type": "armor",
        "defense": 15,
        "ability": "闇耐性+60%",
        "description": "闇の力が込められた盾。"
    },
    "蜘蛛の鎧": {
        "materials": {"蜘蛛の糸": 3, "悪魔の角": 1},
        "result_type": "armor",
        "defense": 11,
        "ability": "回避率+15%、毒耐性+50%",
        "description": "蜘蛛の糸で織られた鎧。軽くて頑丈。"
    },
    "竜鱗の鎧": {
        "materials": {"古龍の心臓": 1, "竜の牙": 2, "闇の宝珠": 1},
        "result_type": "armor",
        "defense": 13,
        "ability": "全属性耐性+30%、HP自動回復+5/ターン",
        "description": "竜の素材から作られた究極の鎧。"
    },
    "腐肉の兜": {
        "materials": {"腐った肉": 4},
        "result_type": "armor",
        "defense": 8,
        "ability": "毒無効、アンデッド特効+40%",
        "description": "腐った肉で作られた兜。アンデッドに強い。"
    }
}

