import os
from pathlib import Path

# BASE_DIR
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent

# SECRET_KEY
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-default-key')

# DEBUG
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

# ALLOWED_HOSTS: Heroku 環境変数から取得、無ければ全ホスト許可
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # ここにアプリ名を追加
    'budget_app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # SecurityMiddleware の直後
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'future_budget_simulator.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'future_budget_simulator.wsgi.application'

# Database: Heroku の DATABASE_URL を利用
import dj_database_url
DATABASES = {
    'default': dj_database_url.config(default=os.environ.get('DATABASE_URL'))
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Tokyo'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'

# collectstatic 出力先
STATIC_ROOT = str(BASE_DIR / 'staticfiles')

# collectstatic 時に参照するディレクトリ（存在する場合のみ）
STATICFILES_DIRS = [
    str(BASE_DIR / 'static'),  # 存在しない場合は削除してOK
]

# WhiteNoise 設定
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'