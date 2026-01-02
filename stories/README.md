# Stories JSON（ストーリー分割）

このBOTは `story.py` が外部JSONを読み込みます。

- プロジェクトルートの `stories.json`
- プロジェクトルートの `stories/*.json`

外部JSONが同じ `story_id` を持つ場合、後から読み込まれた定義で上書きされます。
（`stories/*.json` はファイル名順でマージ）

## 最小フォーマット（従来互換）

```json
{
  "stories": {
    "intro_test": {
      "title": "テスト",
      "lines": [
        {"speaker": "ナレーション", "text": "これはテストです"}
      ]
    }
  }
}
```

## ノード形式（分岐対応）

```json
{
  "stories": {
    "route_example": {
      "title": "分岐例",
      "start_node": "start",
      "nodes": {
        "start": {
          "lines": [
            {"speaker": "???", "text": "条件で選択肢が変わる"}
          ],
          "choices": [
            {
              "label": "ATKが10以上なら見える",
              "conditions": [{"type": "stat.atk.gte", "amount": 10}],
              "result": {
                "title": "力を示した",
                "lines": [{"speaker": "あなた", "text": "任せろ"}]
              },
              "effects": [{"type": "flag.set", "key": "route.power"}],
              "next": {"node": "after"}
            },
            {
              "label": "別ルート",
              "result": {
                "title": "静かに進む",
                "lines": [{"speaker": "あなた", "text": "今はやめておこう"}]
              },
              "effects": [{"type": "flag.set", "key": "route.silent"}],
              "next": {"node": "after"}
            }
          ]
        },
        "after": {
          "lines": [
            {"speaker": "ナレーション", "text": "ここから先は route.power / route.silent のフラグで分岐可能"}
          ],
          "choices": [
            {
              "label": "エンディングA（powerのみ）",
              "conditions": [{"type": "flag.has", "key": "route.power"}],
              "result": {
                "title": "Ending A",
                "lines": [{"speaker": "システム", "text": "Aエンド"}]
              },
              "effects": [{"type": "flag.set", "key": "ending.A"}],
              "next": {"end": true}
            },
            {
              "label": "エンディングB（silentのみ）",
              "conditions": [{"type": "flag.has", "key": "route.silent"}],
              "result": {
                "title": "Ending B",
                "lines": [{"speaker": "システム", "text": "Bエンド"}]
              },
              "effects": [{"type": "flag.set", "key": "ending.B"}],
              "next": {"end": true}
            }
          ]
        }
      }
    }
  }
}
```

## conditions（現在サポート）

- `flag.has` / `flag.missing` : `key`
- `inventory.has` / `inventory.missing` : `item`
- `gold.gte` : `amount`
- `stat.atk.gte` / `stat.atk.lte` : `amount`
- `stat.def.gte` / `stat.def.lte` : `amount`
- `distance.gte` / `distance.lte` : `amount`

## effects（現在サポート）

- `inventory.add` / `inventory.remove` : `item`
- `gold.add` : `amount`
- `player.heal` : `hp`, `mp`
- `flag.set` / `flag.clear` : `key`

> 未知の条件は「無視」されます（段階導入のため）。
