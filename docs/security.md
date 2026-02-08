# セキュリティ設定ガイド

## 概要

このドキュメントは、家計シミュレーターアプリケーションの本番環境でのセキュリティ設定について説明します。

## 必須セキュリティ設定

### 1. DEBUG設定

**重要**: 本番環境では必ず`DEBUG=False`に設定してください。

```bash
# .env または環境変数
DEBUG=False
```

DEBUGがTrueの場合、以下のセキュリティリスクがあります：
- 詳細なエラーメッセージが表示され、システム情報が漏洩
- 静的ファイルが開発サーバーで配信される（非効率）
- セキュリティチェックが無効化される

### 2. SECRET_KEY

強力なSECRET_KEYを生成・設定してください。

```bash
# 生成コマンド
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# .env に設定
SECRET_KEY=)#n)^ekm$fs3rj-s!nux16k%rzpp)_#j4)#!ltng_gw83-e!cd
```

**注意**:
- SECRET_KEYはGitにコミットしないでください（.gitignoreに.envが含まれていることを確認）
- 本番環境と開発環境で異なるキーを使用してください
- 定期的に変更することを推奨します（ただし既存セッションは無効化されます）

### 3. ALLOWED_HOSTS

本番環境のドメインを設定してください。

```bash
# .env
ALLOWED_HOSTS=your-app.herokuapp.com,www.your-domain.com
```

設定されていないホスト名からのアクセスは拒否されます（セキュリティ保護）。

### 4. HTTPS/SSL設定

本番環境では、以下の設定が自動的に有効化されます（settings.py内で`DEBUG=False`の場合）：

```python
# HTTPS強制リダイレクト
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HSTS (HTTP Strict Transport Security)
SECURE_HSTS_SECONDS = 31536000  # 1年
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# セキュアクッキー
SESSION_COOKIE_SECURE = True  # 環境変数でも設定可能
CSRF_COOKIE_SECURE = True

# その他のセキュリティヘッダー
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
```

**HSTS注意事項**:
- HSTS設定は慎重に行ってください（1年間HTTPSが強制されます）
- テスト環境で十分に検証してから本番環境で有効化してください
- HSTSプリロードリストに登録する場合は、[hstspreload.org](https://hstspreload.org/)を参照してください

### 5. セッションセキュリティ

セッションの設定は以下の通りです：

```python
SESSION_ENGINE = 'django.contrib.sessions.backends.db'  # データベースセッション
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365  # 365日
SESSION_SAVE_EVERY_REQUEST = True  # リクエストごとに有効期限を更新
SESSION_COOKIE_SECURE = True  # 本番環境でHTTPSのみ（DEBUG=Falseで自動設定）
SESSION_COOKIE_HTTPONLY = True  # JavaScriptからのアクセスを防ぐ
SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF攻撃を防ぐ
```

## 推奨セキュリティ設定

### 1. Basic認証

公開前のステージング環境や、追加の保護が必要な場合はBasic認証を有効化できます。

```bash
# .env
BASIC_AUTH_ENABLED=True
BASIC_AUTH_USERNAME=your_username
BASIC_AUTH_PASSWORD=your_strong_password
```

**注意**: Basic認証は補助的なセキュリティ手段です。強力なパスワードを使用してください。

### 2. データベースセキュリティ

- PostgreSQLの強力なパスワードを設定
- データベースへのアクセスを信頼できるIPアドレスのみに制限
- 定期的なバックアップを実施

### 3. 定期的なセキュリティアップデート

```bash
# 依存パッケージの脆弱性チェック
pip list --outdated

# セキュリティアップデートの適用
pip install --upgrade django
pip install --upgrade -r requirements.txt
```

## デプロイ前チェックリスト

本番環境にデプロイする前に、以下を確認してください：

- [ ] `DEBUG=False`に設定
- [ ] 強力な`SECRET_KEY`を生成・設定（開発環境と異なるキー）
- [ ] `ALLOWED_HOSTS`に本番ドメインを設定
- [ ] `DATABASE_URL`が本番データベースを指している
- [ ] `SESSION_COOKIE_SECURE=True`（HTTPS環境の場合）
- [ ] Basic認証の設定（必要に応じて）
- [ ] `.env`ファイルがGitにコミットされていないことを確認
- [ ] Djangoのセキュリティチェックを実行（後述）
- [ ] 依存パッケージが最新版に更新されている
- [ ] データベースバックアップが設定されている

## Djangoセキュリティチェック

Djangoには組み込みのセキュリティチェック機能があります：

```bash
# 開発環境でのチェック
python manage.py check --deploy

# 本番環境設定でのチェック（DEBUG=Falseで実行）
DEBUG=False python manage.py check --deploy
```

このコマンドは、セキュリティに関する警告や推奨事項を表示します。

## Heroku環境での設定

Herokuにデプロイする場合の設定例：

```bash
# Heroku環境変数の設定
heroku config:set DEBUG=False
heroku config:set SECRET_KEY='your-generated-secret-key'
heroku config:set BASIC_AUTH_ENABLED=True
heroku config:set BASIC_AUTH_USERNAME=admin
heroku config:set BASIC_AUTH_PASSWORD='your-strong-password'

# DATABASE_URLはHeroku Postgresアドオンが自動設定
# ALLOWED_HOSTSは自動的にHerokuドメインが含まれる（settings.py参照）

# 環境変数の確認
heroku config
```

## 参考リンク

- [Django Security Settings](https://docs.djangoproject.com/en/5.2/topics/security/)
- [Django Deployment Checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [HSTS Preload List](https://hstspreload.org/)

## トラブルシューティング

### HTTPS関連のエラー

**症状**: "Mixed Content"エラーやHTTPSリダイレクトループ

**解決策**:
1. ロードバランサー/プロキシがHTTPSを終端している場合、`SECURE_PROXY_SSL_HEADER`が正しく設定されているか確認
2. Herokuの場合、この設定は既に含まれています

### セッションが保持されない

**症状**: ログイン状態が維持されない

**解決策**:
1. `SESSION_COOKIE_SECURE=True`の場合、HTTPS環境でのみ動作します
2. 開発環境（HTTP）では`SESSION_COOKIE_SECURE=False`に設定してください
3. `.env`ファイルの設定を確認してください

### HSTS警告

**症状**: ブラウザがHTTPアクセスを完全にブロック

**解決策**:
1. HSTS設定を一度有効化すると、指定期間（1年）はHTTPアクセスができなくなります
2. テスト時は`SECURE_HSTS_SECONDS`を短く設定（例: 60秒）してください
3. ブラウザのHSTSキャッシュをクリアする方法: `chrome://net-internals/#hsts`
