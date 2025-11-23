import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

STATIC_URL = '/static/'

# Heroku 用に絶対パスで staticfiles を指定
STATIC_ROOT = BASE_DIR / 'staticfiles'

# collectstatic 時に参照するディレクトリ
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    # 他のミドルウェア
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'