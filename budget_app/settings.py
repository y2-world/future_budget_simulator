import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = str(BASE_DIR / 'staticfiles')
STATICFILES_DIRS = [str(BASE_DIR / 'static')]

# WhiteNoise
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ALLOWED_HOSTS
env_hosts = os.environ.get('ALLOWED_HOSTS', '*')
ALLOWED_HOSTS = [h.strip() for h in env_hosts.split(',') if h.strip()]

# デバッグ用に Heroku で値を確認
print("ALLOWED_HOSTS:", ALLOWED_HOSTS)