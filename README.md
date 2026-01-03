# 家計シミュレーター

月ごとの収支を入力し、将来の口座残高推移を可視化するWebアプリケーション

デモサイト: https://future-budget-simulator-b9ef5003e4b5.herokuapp.com/

## 目次

1. [概要](#概要)
2. [主な機能](#主な機能)
3. [技術構成](#技術構成)
4. [セットアップ](#セットアップ)
5. [使用方法](#使用方法)
6. [Herokuへのデプロイ](#herokuへのデプロイ)
7. [ドキュメント](#ドキュメント)

## 概要

家計シミュレーターは、月ごとの支出・収入の想定額を入力することで、支払いごとの口座残高推移を確認できるWebアプリケーションです。将来の貯金・預金残高の見通しを立て、家計管理をサポートします。

### 主な特徴

- 月ごとの収支計画の作成・編集
- 複数のクレジットカード管理（VIEW、楽天、PayPay、VERMILLION、Amazon）
- クレジットカードのデフォルト請求額設定
- 月別の支出見積もり機能
- 支払いイベント単位での残高推移を表示
- グラフによる視覚的な残高推移の確認
- 営業日（土日祝を考慮）での支払日・給与日自動調整
- 日本の祝日対応（jpholidayライブラリ使用）
- レスポンシブデザイン（モバイル対応）

## 主な機能

### 1. 初期設定
- 初期口座残高の入力
- シミュレーション開始日の設定
- シミュレーション期間の設定（12ヶ月、24ヶ月など）

### 2. クレジットカード管理
- デフォルト請求額の設定（各カード共通）
- 月別の支出見積もり（購入月ベース）
- 請求月の自動計算（VIEWカード独自ルール対応）
- ボーナス払いの設定

### 3. 月次計画入力
- 給与
- 食費
- 家賃
- レイク返済
- 各種クレジットカード引落額（VIEW、楽天、PayPay、VERMILLION、Amazon）
- ボーナス（該当月のみ）
- マネーアシスト返済・借入
- その他支出

### 4. シミュレーション実行
- 月ごとのイベントを日付順に整理
- 営業日調整（給与は前営業日、支払いは翌営業日）
- 支払いごとに残高を計算
- 計算結果をテーブルとグラフで表示

### 5. 結果表示
- 支払いイベント一覧（日付、イベント名、金額、残高）
- 月ごとの残高推移グラフ（折れ線グラフ）
- 収支サマリー（月別の収入・支出・純収支）
- 月初/月末残高の表示

### 6. データ管理
- 月次計画の保存・更新・削除
- クレジットカードデータの管理
- データのバックアップ・復元機能

## 技術構成

### バックエンド
- Python 3.13
- Django 5.2.8
- PostgreSQL（本番環境）
- SQLite（開発環境）
- gunicorn 23.0.0（WSGIサーバー）

### フロントエンド
- HTML5
- Tailwind CSS 3.x（CSSフレームワーク）
- JavaScript（ES6+）
- Chart.js（グラフ描画ライブラリ）

### 主な依存パッケージ
- jpholiday 0.1.10（日本の祝日判定）
- dj-database-url 2.2.0（データベースURL設定）
- psycopg2-binary 2.9.11（PostgreSQLアダプター）
- whitenoise 6.8.2（静的ファイル配信）

### インフラ
- Heroku（本番環境ホスティング）
- Git（バージョン管理）

## セットアップ

### 方法1: Docker（推奨）

#### 前提条件
- Docker Desktop がインストールされていること

#### 起動手順

1. リポジトリのクローン
```bash
git clone <repository-url>
cd future_budget_simulator
```

2. Dockerコンテナのビルドと起動
```bash
docker compose up -d
```

3. ブラウザでアクセス
```
http://localhost:8000/
```

4. データベース管理ツール（Adminer）にアクセス（オプション）
```
http://localhost:8080/

ログイン情報:
- システム: PostgreSQL
- サーバ: db
- ユーザ名: postgres
- パスワード: postgres
- データベース: budget_simulator
```

#### Docker関連コマンド

コンテナの停止:
```bash
docker compose down
```

ログの確認:
```bash
docker compose logs web
docker compose logs db
```

コンテナの再起動:
```bash
docker compose restart
```

データベースのシェルに接続:
```bash
docker compose exec db psql -U postgres -d budget_simulator
```

Djangoのシェルに接続:
```bash
docker compose exec web python manage.py shell
```

マイグレーションの実行:
```bash
docker compose exec web python manage.py migrate
```

### 方法2: ローカル環境（Python venv）

#### 前提条件
- Python 3.13以上がインストールされていること

#### インストール手順

1. リポジトリのクローン
```bash
git clone <repository-url>
cd future_budget_simulator
```

2. 仮想環境の作成と有効化
```bash
python3 -m venv venv
source venv/bin/activate  # Windowsの場合: venv\Scripts\activate
```

3. 依存パッケージのインストール
```bash
pip install -r requirements.txt
```

4. データベースのマイグレーション
```bash
python manage.py migrate
```

5. 管理者ユーザーの作成（オプション）
```bash
python manage.py createsuperuser
```

6. 静的ファイルの収集
```bash
python manage.py collectstatic
```

7. 開発サーバーの起動
```bash
python manage.py runserver
```

8. ブラウザでアクセス
```
http://127.0.0.1:8000/
```

## 使用方法

### 基本的な利用フロー

1. **初期設定**
   - トップページから「設定」にアクセス
   - 初期口座残高を入力
   - シミュレーション開始日と期間を設定（オプション）

2. **クレジットカードの設定（オプション）**
   - 「クレカデフォルト」で各カードの基本請求額を設定
   - 「クレカ見積もり」で月別の購入予定額を入力
   - システムが自動的に請求月に反映

3. **月次計画の作成**
   - 「月次計画」ページで新規作成
   - 年月を選択
   - 各項目（給与、食費、家賃など）の想定額を入力
   - クレジットカードの請求額は自動計算されるが手動で上書き可能
   - 保存ボタンをクリック

4. **結果確認**
   - 月次計画一覧で各月の収支サマリーを確認
   - 月初・月末残高を確認
   - タイムラインで支払いイベントごとの詳細を表示
   - グラフで視覚的に残高推移を確認

5. **計画の修正**
   - 各月の計画を編集して再保存
   - システムが自動的に再計算

## Herokuへのデプロイ

このアプリケーションはHerokuにデプロイされています。初回デプロイ時に発生した主な問題と解決方法を記載します。

### 初回デプロイで発生した問題

1. **ALLOWED_HOSTS設定エラー**
   - **問題**: Herokuのホスト名が`ALLOWED_HOSTS`に含まれていなかった
   - **解決**: `settings.py`で`future-budget-simulator-b9ef5003e4b5.herokuapp.com`を追加

2. **静的ファイル配信エラー**
   - **問題**: 静的ファイル（CSS、JS）が正しく配信されなかった
   - **解決**:
     - `STATIC_ROOT`を設定
     - WhiteNoiseをインストール・設定
     - `python manage.py collectstatic`を実行

3. **データベース接続エラー**
   - **問題**: SQLiteがHerokuで使用できない
   - **解決**:
     - PostgreSQLアドオンを追加
     - `dj-database-url`を使用してDATABASE_URL環境変数を読み込み
     - `psycopg2-binary`をインストール

### デプロイ手順

1. **Heroku CLIのインストール**
```bash
brew tap heroku/brew && brew install heroku  # macOS
```

2. **Herokuアプリの作成**
```bash
heroku create future-budget-simulator
```

3. **PostgreSQLアドオンの追加**
```bash
heroku addons:create heroku-postgresql:mini
```

4. **環境変数の設定**
```bash
heroku config:set DJANGO_SECRET_KEY='your-secret-key'
heroku config:set DEBUG=False
```

5. **デプロイ**
```bash
git push heroku master
```

6. **データベースのマイグレーション**
```bash
heroku run python manage.py migrate
```

7. **管理者ユーザーの作成（オプション）**
```bash
heroku run python manage.py createsuperuser
```

### 設定ファイル

プロジェクトには以下のHeroku用設定ファイルが含まれています：

- **Procfile**: gunicornでアプリケーションを起動
  ```
  web: gunicorn future_budget_simulator.wsgi
  ```

- **requirements.txt**: 必要なPythonパッケージ一覧

- **settings.py**:
  - WhiteNoiseの設定
  - DATABASE_URLの読み込み
  - STATIC_ROOT設定
  - ALLOWED_HOSTS設定

### トラブルシューティング

ログの確認:
```bash
heroku logs --tail
```

アプリの再起動:
```bash
heroku restart
```

## ドキュメント

詳細な設計ドキュメントは[docs](./docs/)ディレクトリを参照してください。

- [要件定義書](./docs/requirements.md)
- [データベース設計書](./docs/database_design.md)
- [API設計書](./docs/api_design.md)
- [実装計画](./docs/implementation_plan.md)

## プロジェクト構造

```
future_budget_simulator/
├── manage.py
├── db.sqlite3
├── README.md
├── docs/                          # ドキュメント
│   ├── requirements.md
│   ├── database_design.md
│   ├── api_design.md
│   └── implementation_plan.md
├── future_budget_simulator/       # プロジェクト設定
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
└── budget_app/                    # メインアプリケーション
    ├── __init__.py
    ├── models.py                  # データモデル
    ├── views.py                   # ビュー
    ├── urls.py                    # URLルーティング
    ├── admin.py                   # 管理画面設定
    ├── apps.py
    ├── tests.py
    ├── templates/                 # HTMLテンプレート
    │   └── budget_app/
    ├── static/                    # 静的ファイル
    │   ├── css/
    │   ├── js/
    │   └── images/
    └── migrations/                # データベースマイグレーション
```

## 開発状況

### 完了
- ✅ Djangoプロジェクトのセットアップ
- ✅ データモデルの定義（MonthlyPlan、CreditEstimate、CreditDefault等）
- ✅ ビューとURLの実装
- ✅ テンプレートの作成（レスポンシブデザイン対応）
- ✅ 計算ロジックの実装（営業日調整含む）
- ✅ グラフ表示機能（Chart.js）
- ✅ クレジットカード管理機能
- ✅ データバックアップ・復元機能
- ✅ Herokuへのデプロイ

### 未着手
- ⬜ CSV入出力機能
- ⬜ Zaim API連携
- ⬜ テストコードの作成
- ⬜ ユーザー認証機能

## ライセンス

このプロジェクトは個人利用目的で作成されています。

## 作成者

Yuki Yoshida

## 更新履歴

- 2025-11-24: README更新、Herokuデプロイ情報追加
- 2025-11-23: Herokuへのデプロイ、jpholidayバージョン固定
- 2025-11-22: クレジットカード管理機能実装、モバイル表示対応
- 2025-11-21: プロジェクト作成、データモデル定義
