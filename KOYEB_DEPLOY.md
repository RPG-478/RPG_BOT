# Koyeb デプロイ手順

## 1. GitHubリポジトリの準備
このプロジェクトをGitHubにプッシュしてください。

## 2. Koyebアカウント作成
- https://www.koyeb.com にアクセス
- アカウント作成（GitHubでサインアップ推奨）

## 3. サービスの作成
1. Koyebダッシュボードで「Create Service」
2. デプロイ元：「GitHub」を選択
3. リポジトリ：このプロジェクトを選択
4. ビルド設定：
   - **Build command**: (空欄のまま)
   - **Run command**: `python main.py`
   - **Port**: `8000`

## 4. 環境変数の設定
以下の環境変数を追加：

| 変数名 | 値 |
|--------|-----|
| `DISCORD_BOT_TOKEN` | Discordボットトークン |
| `SUPABASE_URL` | SupabaseプロジェクトURL |
| `SUPABASE_KEY` | Supabase ANONキー |

## 5. デプロイ
「Deploy」ボタンをクリック

## 6. 確認
- ログで "Logged in as [Bot Name]" を確認
- Discordサーバーで `!start` をテスト

## トラブルシューティング
- **ボットがオフライン**: ログを確認、環境変数を確認
- **データベースエラー**: Supabase URLとキーを確認
- **ポートエラー**: ポート8000が正しく設定されているか確認

## コスト最適化（無料枠3$以内）
- Koyebの無料枠を使用
- Supabaseの無料枠を使用
- 1インスタンスのみ実行
