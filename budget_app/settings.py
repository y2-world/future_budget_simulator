from pathlib import Path

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'

# Heroku 用に collectstatic 出力先を文字列の絶対パスで指定
STATIC_ROOT = str(BASE_DIR / 'staticfiles')

# collectstatic 時に参照するディレクトリ（存在する場合のみ）
STATICFILES_DIRS = [
    str(BASE_DIR / 'static'),  # 存在しない場合は削除してもOK
]

# WhiteNoise 設定
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # SecurityMiddleware の直後
    # 他のミドルウェア
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'