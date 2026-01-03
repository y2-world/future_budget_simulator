# Python 3.13をベースイメージとして使用
FROM python:3.13-slim

# 環境変数を設定
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 作業ディレクトリを設定
WORKDIR /app

# システムパッケージの更新とPostgreSQLクライアントのインストール
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 依存関係をコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのコードをコピー
COPY . .

# 静的ファイルを収集
RUN python manage.py collectstatic --noinput

# ポート8000を公開
EXPOSE 8000

# エントリーポイントスクリプトをコピー
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# エントリーポイントを設定
ENTRYPOINT ["/docker-entrypoint.sh"]

# デフォルトコマンド（gunicornでアプリを起動）
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "future_budget_simulator.wsgi:application"]
