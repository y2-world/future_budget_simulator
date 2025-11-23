import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = str(BASE_DIR / 'staticfiles')
STATICFILES_DIRS = [str(BASE_DIR / 'static')]

# Middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ALLOWED_HOSTS の設定
ALLOWED_HOSTS = ['future-budget-simulator-b9ef5003e4b5.herokuapp.com']

# 環境変数から追加のホストを取得
allowed_hosts_env = os.environ.get('ALLOWED_HOSTS', '')
if allowed_hosts_env:
    additional_hosts = [host.strip() for host in allowed_hosts_env.split(',') if host.strip()]
    ALLOWED_HOSTS.extend(additional_hosts)

# ローカル開発用
if os.environ.get('DEBUG') == 'True':
    ALLOWED_HOSTS.extend(['localhost', '127.0.0.1', '[::1]'])

# デバッグ用ログ
print("ALLOWED_HOSTS:", ALLOWED_HOSTS)