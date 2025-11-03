# クイックスタートガイド

## 🚀 Koyebへのデプロイ（5ステップ）

### ステップ1: リポジトリをGitHubにプッシュ
このプロジェクトをGitHubリポジトリにプッシュしてください。

### ステップ2: Supabaseデータベース準備
1. [Supabase](https://supabase.com)で新規プロジェクト作成
2. SQL Editorで以下を順番に実行：
   - `attached_assets/supabase_schema_1762125002111.sql`
   - `migration_raid_hp_recovery.sql`
3. URLとAnon Keyをコピー

### ステップ3: Discord Bot作成
1. [Discord Developer Portal](https://discord.com/developers/applications)でアプリ作成
2. Bot Tokenを取得
3. Intentsを有効化：
   - ✅ Presence Intent
   - ✅ Server Members Intent
   - ✅ Message Content Intent

### ステップ4: Koyebにデプロイ
1. [Koyeb](https://www.koyeb.com)でサービス作成
2. GitHubリポジトリを接続
3. 設定：
   - **Run command**: `python main.py`
   - **Port**: `8000`
4. 環境変数を追加：
   - `DISCORD_BOT_TOKEN` = Discord Bot Token
   - `SUPABASE_URL` = Supabase Project URL
   - `SUPABASE_KEY` = Supabase Anon Key

### ステップ5: デプロイ＆テスト
1. 「Deploy」をクリック
2. ログで "Logged in as..." を確認
3. Discordサーバーで `!start` を実行

## ✅ 完了！

ボットが起動し、レイドボスシステムが利用可能になります。

## 📋 実装済み機能

### レイドシステム
- 曜日別レイドボス7種類（月〜日）
- レイド専用ステータス（HP/ATK/DEF）
- 6時間HP自動回復
- 全プレイヤー共有のボスHP
- 貢献度報酬システム
- 討伐通知（チャンネルID: 1424712515396305007）
- `!reset`でもレイドステータス保護

### コマンド一覧
```
!raid_info (!ri)       - ボス情報
!raid_upgrade (!ru)    - ステータス確認
!raid_atk (!ra)        - 攻撃力+5 (3PT)
!raid_def (!rd)        - 防御力+3 (3PT)
!raid_hp (!rh)         - 最大HP+50 (5PT)
!raid_heal (!rhe)      - HP全回復 (1PT)
!raid_recovery (!rr)   - 回復速度+5 (4PT)
```

## 💰 コスト

**無料枠で運用可能！**
- Koyeb: 無料枠（1インスタンス）
- Supabase: 無料枠（500MB DB）
- 推定コスト: $0/月

## ⚠️ 重要な注意事項

1. **Replitで24/7稼働させないでください**
   - 利用規約違反になります
   - Koyebでの稼働を推奨

2. **環境変数を絶対にコミットしないでください**
   - `.env`ファイルは`.gitignore`に含まれています
   - Koyebで環境変数を設定

3. **データベースマイグレーションは順番に実行**
   - 基本スキーマ → HP回復マイグレーションの順

## 📞 トラブルシューティング

### ボットがオフライン
- Koyebのログを確認
- 環境変数が正しく設定されているか確認
- Discord Bot Tokenが有効か確認

### データベースエラー
- Supabase URLとKeyを確認
- マイグレーションが実行されているか確認

### レイドボスが出現しない
- 500m、1000m、1500m...で出現
- データベースの`raid_bosses`テーブルを確認

詳細は `DEPLOYMENT_GUIDE.md` を参照してください。
