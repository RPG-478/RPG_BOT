-- ========================================
-- New Systems Database Migration
-- ========================================
-- このSQLファイルは3つの新システム用のテーブルを作成します
-- 1. Raid Boss Progress (レイドボス進捗)
-- 2. Merchant Encounters (商人遭遇履歴)
-- 3. Enemy Battle Stats (敵AI戦闘統計)
-- ========================================

-- レイドボス進捗テーブル
CREATE TABLE IF NOT EXISTS raid_boss_progress (
    id BIGSERIAL PRIMARY KEY,
    raid_boss_id TEXT NOT NULL,
    current_hp INTEGER NOT NULL,
    max_hp INTEGER NOT NULL,
    last_damaged_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    defeated_at TIMESTAMP WITH TIME ZONE,
    is_defeated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- レイドボス貢献度テーブル
CREATE TABLE IF NOT EXISTS raid_boss_contributions (
    id BIGSERIAL PRIMARY KEY,
    raid_boss_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    total_damage INTEGER DEFAULT 0,
    last_contribution_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(raid_boss_id, user_id)
);

-- 商人遭遇履歴テーブル
CREATE TABLE IF NOT EXISTS merchant_encounters (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    distance INTEGER NOT NULL,
    items_bought JSONB DEFAULT '[]'::jsonb,
    items_sold JSONB DEFAULT '[]'::jsonb,
    total_spent INTEGER DEFAULT 0,
    total_earned INTEGER DEFAULT 0,
    encountered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES players(user_id) ON DELETE CASCADE
);

-- 敵AI戦闘統計テーブル
CREATE TABLE IF NOT EXISTS enemy_battle_stats (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    enemy_name TEXT NOT NULL,
    battles_fought INTEGER DEFAULT 0,
    battles_won INTEGER DEFAULT 0,
    battles_lost INTEGER DEFAULT 0,
    total_damage_dealt INTEGER DEFAULT 0,
    total_damage_taken INTEGER DEFAULT 0,
    skills_used JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, enemy_name),
    FOREIGN KEY (user_id) REFERENCES players(user_id) ON DELETE CASCADE
);

-- インデックス作成
CREATE INDEX IF NOT EXISTS idx_raid_boss_progress_boss_id ON raid_boss_progress(raid_boss_id);
CREATE INDEX IF NOT EXISTS idx_raid_boss_progress_defeated ON raid_boss_progress(is_defeated);
CREATE INDEX IF NOT EXISTS idx_raid_boss_contributions_boss_id ON raid_boss_contributions(raid_boss_id);
CREATE INDEX IF NOT EXISTS idx_raid_boss_contributions_user_id ON raid_boss_contributions(user_id);
CREATE INDEX IF NOT EXISTS idx_merchant_encounters_user_id ON merchant_encounters(user_id);
CREATE INDEX IF NOT EXISTS idx_merchant_encounters_distance ON merchant_encounters(distance);
CREATE INDEX IF NOT EXISTS idx_enemy_battle_stats_user_id ON enemy_battle_stats(user_id);
CREATE INDEX IF NOT EXISTS idx_enemy_battle_stats_enemy_name ON enemy_battle_stats(enemy_name);

-- 更新時刻の自動更新トリガー
CREATE TRIGGER update_raid_boss_progress_updated_at BEFORE UPDATE ON raid_boss_progress
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_raid_boss_contributions_updated_at BEFORE UPDATE ON raid_boss_contributions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_enemy_battle_stats_updated_at BEFORE UPDATE ON enemy_battle_stats
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- コメント
COMMENT ON TABLE raid_boss_progress IS 'レイドボスの現在HP状態（500m毎）';
COMMENT ON TABLE raid_boss_contributions IS 'プレイヤーごとのレイドボス貢献度';
COMMENT ON TABLE merchant_encounters IS '商人遭遇履歴（0.5%確率イベント）';
COMMENT ON TABLE enemy_battle_stats IS '敵AI戦闘統計（スキル使用履歴含む）';
