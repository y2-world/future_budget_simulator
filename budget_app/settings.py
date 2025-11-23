import os

# プロジェクトのベースディレクトリを定義
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 静的ファイル（CSS, JS, 画像など）のURL
STATIC_URL = '/static/'

# collectstatic がまとめるディレクトリ（Heroku では必須）
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    # …（既存のミドルウェア）
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'