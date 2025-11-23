import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = str(BASE_DIR / 'staticfiles')
STATICFILES_DIRS = [
    str(BASE_DIR / 'static'),
]

# WhiteNoise
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ALLOWED_HOSTS を Heroku 環境変数から取得、存在しない場合は '*' にして全ホスト許可
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')