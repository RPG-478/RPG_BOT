-- レイドHP自動回復システムのための新フィールド追加
-- このSQLはSupabaseのSQL Editorで実行してください

ALTER TABLE player_raid_stats 
ADD COLUMN IF NOT EXISTS raid_hp_recovery_rate INTEGER DEFAULT 10,
ADD COLUMN IF NOT EXISTS raid_hp_recovery_upgrade INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_hp_recovery TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- 既存データに対してデフォルト値を設定
UPDATE player_raid_stats
SET raid_hp_recovery_rate = 10,
    raid_hp_recovery_upgrade = 0,
    last_hp_recovery = NOW()
WHERE raid_hp_recovery_rate IS NULL OR last_hp_recovery IS NULL;

-- インデックス作成（パフォーマンス最適化）
CREATE INDEX IF NOT EXISTS idx_player_raid_stats_last_hp_recovery ON player_raid_stats(last_hp_recovery);

COMMENT ON COLUMN player_raid_stats.raid_hp_recovery_rate IS '6時間ごとのHP自動回復量';
COMMENT ON COLUMN player_raid_stats.raid_hp_recovery_upgrade IS 'HP回復速度のアップグレードレベル';
COMMENT ON COLUMN player_raid_stats.last_hp_recovery IS '最後にHP回復が適用された時刻';
