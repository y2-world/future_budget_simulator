# セキュリティ設定ガイド

## 環境変数の設定

このアプリケーションは環境変数を使用してセキュリティ設定を管理します。

### ローカル開発環境

1. `.env.local` ファイルを作成（既に作成済み）
2. 以下の内容で設定：

```bash
DEBUG=True
SECRET_KEY=django-insecure-dev-key-only-for-local-development
ALLOWED_HOSTS=localhost,127.0.0.1
SESSION_COOKIE_SECURE=False
```

### 本番環境（Heroku等）

以下の環境変数を設定してください：

```bash
# 必須設定
DEBUG=False
SECRET_KEY=<50文字以上のランダムな文字列>
ALLOWED_HOSTS=your-domain.com,www.your-domain.com,your-app.herokuapp.com
SESSION_COOKIE_SECURE=True

# データベース（Herokuでは自動設定）
DATABASE_URL=postgresql://...

# Basic認証（オプション）
BASIC_AUTH_ENABLED=True
BASIC_AUTH_USERNAME=<ユーザー名>
BASIC_AUTH_PASSWORD=<パスワード>
```

## SECRET_KEYの生成方法

新しいSECRET_KEYを生成する：

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## セキュリティ機能

### 開発環境（DEBUG=True）
- HTTP接続が許可される
- セキュアクッキー無効
- 詳細なエラーメッセージ表示

### 本番環境（DEBUG=False）
- HTTPS強制リダイレクト
- HSTS（HTTP Strict Transport Security）有効
- セキュアクッキー有効
- XSS/クリックジャッキング保護
- CSRF保護強化

## 注意事項

⚠️ **絶対にやってはいけないこと**
- SECRET_KEYをGitにコミットしない
- DEBUGをTrueのまま本番環境で使用しない
- `.env` や `.env.local` をGitにコミットしない（.gitignoreに追加済み）

✅ **推奨事項**
- 本番環境のSECRET_KEYは環境変数で管理
- HTTPS証明書を適切に設定
- 定期的にセキュリティアップデートを実施
