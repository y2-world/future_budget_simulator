import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')  # collectstatic 出力先

# ローカル静的ファイルを探すディレクトリ（任意／必要に応じて）
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # SecurityMiddleware のすぐあとに配置する
    # その他ミドルウェア
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'