import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'

# collectstatic 出力先
STATIC_ROOT = str(BASE_DIR / 'staticfiles')

# collectstatic 時に参照するディレクトリ（存在する場合のみ）
STATICFILES_DIRS = [
    str(BASE_DIR / 'static'),
]

# WhiteNoise 設定
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ALLOWED_HOSTS: Heroku 環境変数から取得、無ければ *（全ホスト許可）
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')