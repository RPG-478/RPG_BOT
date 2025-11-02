# イニシエダンジョン - 新システム統合状況

## 📊 統合ステータス

### ✅ 完了したタスク

1. **開発環境セットアップ**
   - Python 3.11とすべての依存関係をインストール完了
   - Workflowを設定（`python main.py`）
   - `.gitignore`と`.env.example`を作成

2. **データベース移行**
   - `migrations_new_systems.sql` を作成
   - 新しいテーブル定義:
     - `raid_boss_progress` - レイドボスのHP状態
     - `raid_boss_contributions` - プレイヤー貢献度
     - `merchant_encounters` - 商人遭遇履歴
     - `enemy_battle_stats` - 敵AI戦闘統計
   - インデックスとトリガーも含む

3. **商人システム（Merchant System）**
   - ✅ `main.py`に統合（0.5%確率）
   - ⚠️ 保存機能は未実装（`db.py`に関数追加が必要）

### ⚠️ 未完了のタスク

1. **レイドボスシステム（Raid Boss System）**
   - ❌ `raid_boss_system.py`は存在するが、統合されていない
   - ❌ 500m地点の`SpecialEventView`を`RaidBossView`に置き換える必要がある
   - ❌ `db.py`にレイドボス用の関数が必要
   - ❌ `views.py`に`RaidBossView`クラスを追加する必要がある

2. **敵AIシステム（Enemy AI System）**
   - ❌ `enemy_ai.py`は存在するが、統合されていない
   - ❌ `views.py`の`BattleView`に敵AIロジックを統合する必要がある
   - ❌ `db.py`に戦闘統計記録関数が必要

3. **データベース関数**
   - ❌ レイドボス用の関数（`db.py`に追加）
   - ❌ 商人遭遇記録関数（`db.py`に追加）
   - ❌ 敵AI統計記録関数（`db.py`に追加）
   - ⚠️ `update_updated_at_column()`関数がSupabaseに存在する必要がある

## 🔧 次のステップ

### ステップ1: データベース準備
1. Supabaseコンソールで`update_updated_at_column()`関数を作成:
```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

2. `migrations_new_systems.sql`を実行してテーブルを作成

### ステップ2: データベース関数を追加（db.py）
以下の関数を`db.py`に追加する必要があります:

#### レイドボス関数
```python
async def get_raid_boss_progress(raid_boss_id):
    """レイドボス進捗を取得"""
    # 実装が必要

async def create_raid_boss(raid_boss_id, max_hp):
    """新しいレイドボスを作成"""
    # 実装が必要

async def update_raid_boss_hp(raid_boss_id, damage):
    """レイドボスにダメージを与える"""
    # 実装が必要

async def add_raid_contribution(raid_boss_id, user_id, damage):
    """プレイヤーの貢献度を記録"""
    # 実装が必要

async def get_raid_contributions(raid_boss_id):
    """レイドボスの貢献度リストを取得"""
    # 実装が必要
```

#### 商人関数
```python
async def record_merchant_encounter(user_id, distance, items_bought, items_sold, gold_spent, gold_earned):
    """商人遭遇を記録"""
    # 実装が必要
```

#### 敵AI関数
```python
async def record_enemy_battle(user_id, enemy_name, won, damage_dealt, damage_taken, skills_used):
    """敵との戦闘統計を記録"""
    # 実装が必要

async def get_enemy_stats(user_id, enemy_name):
    """敵との戦闘統計を取得"""
    # 実装が必要
```

### ステップ3: RaidBossViewを作成（views.py）
`views.py`に新しいクラスを追加:
```python
class RaidBossView(View):
    def __init__(self, ctx, player, raid_boss_data, user_processing):
        # レイドボス戦闘UI
        # 複数プレイヤーが同時に戦える仕組み
        # 貢献度に応じた報酬システム
        pass
```

### ステップ4: 統合（main.py）
500m地点のハンドラを更新:
```python
# 優先度2: レイドボス（500m毎、1000m除く）
raid_distances = [500, 1500, 2500, 3500, 4500, 5500, 6500, 7500, 8500, 9500]
for raid_distance in raid_distances:
    if passed_through(raid_distance):
        # RaidBossViewを使用
        raid_boss_data = raid_boss_system.get_raid_boss_data(raid_distance)
        view = RaidBossView(ctx, player_data, raid_boss_data, user_processing)
        # ...
```

### ステップ5: 敵AIをBattleViewに統合（views.py）
`BattleView`の敵ターンロジックを更新:
```python
# 敵の行動決定
enemy_action = enemy_ai.get_enemy_action(
    self.enemy["name"],
    self.enemy["hp"],
    self.enemy["max_hp"],
    self.turn_count
)

if enemy_action["action"] == "skill":
    # スキル使用
    skill_result = enemy_ai.calculate_enemy_skill_damage(...)
    # ...
```

## 🔐 環境変数

`.env`ファイルを作成し、以下を設定してください:
```bash
DISCORD_BOT_TOKEN=your_discord_bot_token_here
SUPABASE_URL=your_supabase_project_url_here
SUPABASE_KEY=your_supabase_anon_key_here
```

## 🚀 起動方法

環境変数を設定後:
```bash
python main.py
```

または、Replitの「Run」ボタンをクリック。

## 📝 既存ファイル

- `merchant_system.py` - 商人システム（UI完成）
- `raid_boss_system.py` - レイドボスデータとロジック
- `enemy_ai.py` - 敵AI行動パターンとスキル
- `migrations_new_systems.sql` - データベース移行SQL

## ⚠️ 重要な注意事項

1. **データベース移行**: 本番環境（Koyeb）でもSupabaseで同じテーブルを作成する必要があります
2. **環境変数**: 開発環境と本番環境で異なる値を使用してください
3. **テスト**: 各システムを個別にテストしてから統合してください

## 🎯 優先順位

1. **高**: データベース関数を追加（すべてのシステムに必要）
2. **高**: 商人システムの保存機能を完成させる
3. **中**: レイドボスシステムを統合
4. **中**: 敵AIをBattleViewに統合
5. **低**: 統計表示コマンドを追加（オプション）

## 📚 参考資料

- Discord.py ドキュメント: https://discordpy.readthedocs.io/
- Supabase ドキュメント: https://supabase.com/docs
