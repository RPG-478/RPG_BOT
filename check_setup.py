#!/usr/bin/env python3
"""
プロジェクトセットアップ検証スクリプト
"""
import os
import sys

def check_env_vars():
    """環境変数の確認"""
    required_vars = ["DISCORD_BOT_TOKEN", "SUPABASE_URL", "SUPABASE_KEY"]
    missing = []
    
    for var in required_vars:
        value = os.getenv(var)
        if not value or value.startswith("placeholder"):
            missing.append(var)
    
    return missing

def check_files():
    """必須ファイルの確認"""
    required_files = [
        "main.py",
        "db.py",
        "views.py",
        "raid_system.py",
        "config.py",
        "requirements.txt",
        "Procfile",
        "runtime.txt"
    ]
    
    missing = []
    for file in required_files:
        if not os.path.exists(file):
            missing.append(file)
    
    return missing

if __name__ == "__main__":
    print("🔍 プロジェクトセットアップ検証")
    print("=" * 50)
    
    # ファイルチェック
    missing_files = check_files()
    if missing_files:
        print(f"❌ 不足ファイル: {', '.join(missing_files)}")
        sys.exit(1)
    else:
        print("✅ すべての必須ファイルが存在します")
    
    # 環境変数チェック
    missing_vars = check_env_vars()
    if missing_vars:
        print(f"⚠️  未設定の環境変数: {', '.join(missing_vars)}")
        print("\n📋 次のステップ:")
        print("1. Replitシークレットに以下を追加してください:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n2. または、Koyebで環境変数を設定してデプロイしてください")
        sys.exit(0)
    else:
        print("✅ すべての環境変数が設定されています")
    
    print("\n✅ プロジェクトは実行可能です！")
    print("🚀 'python main.py' で起動できます")
