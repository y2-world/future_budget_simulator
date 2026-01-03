#!/bin/bash
set -e

# データベースの準備ができるまで待機
echo "Waiting for PostgreSQL..."
while ! pg_isready -h db -U postgres > /dev/null 2>&1; do
    sleep 1
done
echo "PostgreSQL is ready!"

# マイグレーションを実行
echo "Running migrations..."
python manage.py migrate --noinput

# スーパーユーザーが存在しない場合は作成（オプション）
# python manage.py shell -c "
# from django.contrib.auth import get_user_model;
# User = get_user_model();
# if not User.objects.filter(username='admin').exists():
#     User.objects.create_superuser('admin', 'admin@example.com', 'admin')
# "

# 静的ファイルを収集
echo "Collecting static files..."
python manage.py collectstatic --noinput

# コマンドを実行
exec "$@"
