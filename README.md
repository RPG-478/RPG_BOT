# イニシエダンジョン - Discord RPG Bot

曜日別レイドボスシステムを搭載したDiscord RPG Botです。

## 📋 必要な環境変数

以下の環境変数を設定してください（Koyebの環境変数設定画面で）：

```
DISCORD_BOT_TOKEN=your_discord_bot_token_here
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_anon_key_here
```

## 🗄️ データベースセットアップ

1. Supabaseプロジェクトを作成
2. SQL Editorで以下のマイグレーションファイルを実行：
   - `migration_raid_hp_recovery.sql`

## 🚀 Koyebデプロイ手順

### 1. GitHubリポジトリ準備
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

### 2. Koyebでデプロイ
1. Koyebダッシュボードにログイン
2. "Create Service" をクリック
3. GitHubリポジトリを選択
4. 以下の設定を行う：
   - **Build**: `Buildpack`
   - **Run command**: `python main.py`
   - **Port**: 設定不要（Discord botのため）
   - **Environment Variables**: 上記3つの環境変数を設定

### 3. デプロイ開始
- "Deploy" をクリック
- ログを確認して `Logged in as <bot_name>` が表示されればOK

## 📁 主要ファイル構成

```
イニシエダンジョン/
├── main.py                          # メインBot処理
├── db.py                            # Supabase REST API操作
├── raid_system.py                   # レイドボスシステム
├── game.py                          # ゲームロジック・アイテムDB
├── views.py                         # Discord UI (View/Modal)
├── story.py                         # ストーリーデータ
├── titles.py                        # 称号システム
├── death_system.py                  # 死亡履歴システム
├── death_stories.py                 # 死亡ストーリー
├── debug_commands.py                # デバッグコマンド
├── config.py                        # 環境変数読み込み
├── requirements.txt                 # Pythonパッケージ
├── Procfile                         # プロセス定義
└── migration_raid_hp_recovery.sql   # DBマイグレーション

```

## 🎮 主要機能

### レイドボスシステム
- 曜日別に異なるレイドボスが出現（月〜日）
- 500m地点ごとにレイドボスチャレンジ
- 全プレイヤー協力型（HP共有）
- 貢献度に応じた報酬配分
- 6時間ごとのHP自動回復
- `!raid_upgrade` でHP回復速度アップグレード

### その他の機能
- ダンジョン探索 (`!move`)
- 戦闘システム
- 死亡/リスポーンシステム
- 称号・実績システム
- インベントリ管理
- ストーリーイベント

## ⚠️ 重要な注意事項

- **Replitでの常時稼働は禁止**（利用規約違反）
- Replitはコードエディタとしてのみ使用
- Koyeb + GitHubでデプロイすること

## 📞 サポート

問題が発生した場合は、Koyebのログを確認してください：
```bash
# Koyebダッシュボード → サービス詳細 → Logs タブ
```

## 📝 ライセンス

Private Project
