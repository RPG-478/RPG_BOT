import os
import sys

def check_environment():
    print("=" * 50)
    print("イニシエダンジョン Discord Bot - セットアップチェック")
    print("=" * 50)
    
    required_env_vars = [
        "DISCORD_BOT_TOKEN",
        "SUPABASE_URL",
        "SUPABASE_KEY"
    ]
    
    missing_vars = []
    for var in required_env_vars:
        if os.getenv(var):
            print(f"✅ {var}: 設定済み")
        else:
            print(f"❌ {var}: 未設定")
            missing_vars.append(var)
    
    print("\n" + "=" * 50)
    
    if missing_vars:
        print("\n⚠️  以下の環境変数が未設定です:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\n💡 このBotはKoyebで運用されます。")
        print("   Koyebで環境変数を設定してからデプロイしてください。")
        print("\n📝 実装済み機能:")
        print("  ✅ 倉庫ゴールドシステム")
        print("  ✅ ラスボス撃破時の倉庫ゴールド自動送金")
        print("  ✅ レイドステータス強化コマンド（!raid_atk, !raid_def, !raid_hp, !raid_recovery）")
        print("  ✅ 倉庫ゴールド確認コマンド（!vault_gold）")
        print("  ✅ レイド討伐報酬からアップグレードポイント削除（ゴールドのみ）")
    else:
        print("\n✅ すべての環境変数が設定されています！")
        print("   Koyebでデプロイ可能です。")
    
    print("=" * 50)

if __name__ == "__main__":
    check_environment()
