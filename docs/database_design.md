# データベース設計書 - 家計シミュレーター

## 1. ER図

```
┌─────────────────────┐
│  SimulationConfig   │
│─────────────────────│
│  id (PK)            │
│  initial_balance    │
│  start_date         │
│  simulation_months  │
│  is_active          │
│  created_at         │
│  updated_at         │
└─────────────────────┘

┌─────────────────────┐
│   AccountBalance    │
│─────────────────────│
│  id (PK)            │
│  date (UNIQUE)      │
│  balance            │
│  source             │
│  last_updated       │
└─────────────────────┘

┌─────────────────────┐         ┌─────────────────────┐
│   MonthlyPlan       │         │  TransactionEvent   │
│─────────────────────│         │─────────────────────│
│  id (PK)            │◄────────│  id (PK)            │
│  year_month (UNIQUE)│    1:N  │  date               │
│  salary             │         │  event_type         │
│  bonus              │         │  event_name         │
│  food               │         │  amount             │
│  rent               │         │  balance_after      │
│  lake               │         │  month_id (FK)      │
│  credit             │         │  created_at         │
│  savings            │         └─────────────────────┘
│  loan               │
│  utilities          │
│  transportation     │
│  entertainment      │
│  other              │
│  created_at         │
│  updated_at         │
└─────────────────────┘
```

## 2. テーブル定義

### 2.1 SimulationConfig（シミュレーション設定）

シミュレーション全体の設定を管理するテーブル。

| カラム名 | データ型 | NULL | デフォルト | 説明 |
|---------|---------|------|-----------|------|
| id | BigInteger | NO | AUTO | 主キー |
| initial_balance | Integer | NO | 0 | 初期残高（円） |
| start_date | Date | NO | - | シミュレーション開始日 |
| simulation_months | Integer | NO | 12 | シミュレーション期間（月） |
| is_active | Boolean | NO | True | 有効フラグ |
| created_at | DateTime | NO | AUTO | 作成日時 |
| updated_at | DateTime | NO | AUTO | 更新日時 |

**制約**
- `simulation_months` は 1 以上
- 有効な設定（`is_active=True`）は常に1つのみ

**インデックス**
- PRIMARY KEY: `id`
- INDEX: `is_active`

**備考**
- 新しい設定を有効にする際は、既存の有効設定を無効化する
- 初期残高は負の値も許容（借入金がある場合など）

---

### 2.2 AccountBalance（口座残高）

実際の口座残高を記録するテーブル（将来の API 連携用）。

| カラム名 | データ型 | NULL | デフォルト | 説明 |
|---------|---------|------|-----------|------|
| id | BigInteger | NO | AUTO | 主キー |
| date | Date | NO | - | 日付 |
| balance | Integer | NO | - | 残高（円） |
| source | Varchar(20) | NO | 'manual' | データソース |
| last_updated | DateTime | NO | AUTO | 最終更新日時 |

**制約**
- `date` はユニーク制約
- `source` の選択肢: 'manual'（手動入力）, 'api'（API取得）

**インデックス**
- PRIMARY KEY: `id`
- UNIQUE INDEX: `date`

**備考**
- 将来的に銀行APIから実際の残高を取得する際に使用
- シミュレーションとの差分を確認できる

---

### 2.3 MonthlyPlan（月次計画）

月ごとの収支計画を管理するテーブル。

| カラム名 | データ型 | NULL | デフォルト | 説明 |
|---------|---------|------|-----------|------|
| id | BigInteger | NO | AUTO | 主キー |
| year_month | Varchar(7) | NO | - | 年月（YYYY-MM形式） |
| **収入項目** |
| salary | Integer | NO | 0 | 給与（円） |
| bonus | Integer | NO | 0 | ボーナス（円） |
| **支出項目** |
| food | Integer | NO | 0 | 食費（円） |
| rent | Integer | NO | 0 | 家賃（円） |
| lake | Integer | NO | 0 | レイク返済（円） |
| credit | Integer | NO | 0 | クレカ引落（円） |
| savings | Integer | NO | 0 | 定期預金（円） |
| loan | Integer | NO | 0 | マネーアシスト返済（円） |
| utilities | Integer | NO | 0 | 光熱費（円） |
| transportation | Integer | NO | 0 | 交通費（円） |
| entertainment | Integer | NO | 0 | 娯楽費（円） |
| other | Integer | NO | 0 | その他（円） |
| **メタ情報** |
| created_at | DateTime | NO | AUTO | 作成日時 |
| updated_at | DateTime | NO | AUTO | 更新日時 |

**制約**
- `year_month` はユニーク制約
- `year_month` の形式: YYYY-MM（例: 2025-01）
- すべての金額項目は 0 以上

**インデックス**
- PRIMARY KEY: `id`
- UNIQUE INDEX: `year_month`
- INDEX: `year_month`（範囲検索用）

**メソッド**
- `get_total_income()`: 月次総収入を計算
- `get_total_expenses()`: 月次総支出を計算
- `get_net_income()`: 月次収支（純増減）を計算

**備考**
- 各項目のデフォルト値は 0
- 支出項目は正の値で入力（システムが自動的に負の値として処理）

---

### 2.4 TransactionEvent（取引イベント）

シミュレーション計算結果の取引イベントを記録するテーブル。

| カラム名 | データ型 | NULL | デフォルト | 説明 |
|---------|---------|------|-----------|------|
| id | BigInteger | NO | AUTO | 主キー |
| date | Date | NO | - | イベント発生日 |
| event_type | Varchar(20) | NO | - | イベント種類 |
| event_name | Varchar(100) | NO | - | イベント名（日本語） |
| amount | Integer | NO | - | 金額（円）※正=収入、負=支出 |
| balance_after | Integer | NO | - | 取引後残高（円） |
| month_id | BigInteger | NO | - | 関連月次計画（外部キー） |
| created_at | DateTime | NO | AUTO | 作成日時 |

**制約**
- `event_type` の選択肢:
  - 'salary': 給与
  - 'bonus': ボーナス
  - 'food': 食費
  - 'rent': 家賃
  - 'lake': レイク返済
  - 'credit': クレカ引落
  - 'savings': 定期預金
  - 'loan': マネーアシスト返済
  - 'utilities': 光熱費
  - 'transportation': 交通費
  - 'entertainment': 娯楽費
  - 'other': その他

**外部キー**
- `month_id` → `MonthlyPlan.id`（CASCADE削除）

**インデックス**
- PRIMARY KEY: `id`
- INDEX: `date`（日付順ソート用）
- INDEX: `month_id`（関連月検索用）
- INDEX: `event_type`（種類別フィルタリング用）

**備考**
- このテーブルのデータはシミュレーション実行時に自動生成される
- 月次計画が削除された場合、関連するイベントも削除される
- `amount` は収入の場合は正、支出の場合は負の値

---

## 3. データ整合性

### 3.1 外部キー制約

```sql
ALTER TABLE budget_app_transactionevent
    ADD CONSTRAINT fk_month
    FOREIGN KEY (month_id)
    REFERENCES budget_app_monthlyplan(id)
    ON DELETE CASCADE;
```

### 3.2 ユニーク制約

```sql
-- SimulationConfigの有効設定は1つのみ（アプリケーションレベルで制御）
-- MonthlyPlanの年月は一意
ALTER TABLE budget_app_monthlyplan
    ADD CONSTRAINT uk_year_month UNIQUE (year_month);

-- AccountBalanceの日付は一意
ALTER TABLE budget_app_accountbalance
    ADD CONSTRAINT uk_date UNIQUE (date);
```

### 3.3 チェック制約

```sql
-- シミュレーション期間は1ヶ月以上
ALTER TABLE budget_app_simulationconfig
    ADD CONSTRAINT chk_simulation_months
    CHECK (simulation_months >= 1);
```

## 4. インデックス戦略

### 4.1 パフォーマンス最適化

```sql
-- 日付範囲検索の高速化
CREATE INDEX idx_transaction_date ON budget_app_transactionevent(date);

-- 月次計画の範囲検索
CREATE INDEX idx_monthlyplan_yearmonth ON budget_app_monthlyplan(year_month);

-- イベント種類でのフィルタリング
CREATE INDEX idx_transaction_event_type ON budget_app_transactionevent(event_type);

-- 有効な設定の検索
CREATE INDEX idx_config_active ON budget_app_simulationconfig(is_active);
```

## 5. サンプルデータ

### 5.1 SimulationConfig

```sql
INSERT INTO budget_app_simulationconfig
    (initial_balance, start_date, simulation_months, is_active)
VALUES
    (500000, '2025-01-01', 12, true);
```

### 5.2 MonthlyPlan

```sql
INSERT INTO budget_app_monthlyplan
    (year_month, salary, bonus, food, rent, lake, credit, savings, utilities, transportation, entertainment, other)
VALUES
    ('2025-01', 300000, 0, 50000, 80000, 10000, 30000, 20000, 15000, 5000, 10000, 5000),
    ('2025-02', 300000, 0, 50000, 80000, 10000, 30000, 20000, 15000, 5000, 10000, 5000),
    ('2025-06', 300000, 500000, 50000, 80000, 10000, 30000, 20000, 15000, 5000, 10000, 5000);  -- ボーナス月
```

## 6. マイグレーション履歴

### 6.1 初期マイグレーション

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6.2 マイグレーションファイル

- `0001_initial.py`: 初期テーブル作成
  - SimulationConfig
  - AccountBalance
  - MonthlyPlan
  - TransactionEvent

## 7. バックアップ戦略

### 7.1 定期バックアップ

```bash
# データベース全体のバックアップ
python manage.py dumpdata > backup_$(date +%Y%m%d).json

# 特定アプリのみバックアップ
python manage.py dumpdata budget_app > budget_backup_$(date +%Y%m%d).json
```

### 7.2 リストア

```bash
# バックアップからリストア
python manage.py loaddata backup_20250121.json
```

## 8. データメンテナンス

### 8.1 古いデータの削除

```python
# 1年以上前のTransactionEventを削除
from datetime import datetime, timedelta
from budget_app.models import TransactionEvent

one_year_ago = datetime.now() - timedelta(days=365)
TransactionEvent.objects.filter(date__lt=one_year_ago).delete()
```

### 8.2 データ整合性チェック

```python
# 孤立したTransactionEventのチェック
orphaned_events = TransactionEvent.objects.filter(month__isnull=True)
if orphaned_events.exists():
    print(f"孤立したイベント: {orphaned_events.count()}件")
```

## 9. クエリ最適化

### 9.1 N+1問題の回避

```python
# NG: N+1クエリが発生
events = TransactionEvent.objects.all()
for event in events:
    print(event.month.year_month)  # 各イベントごとにクエリ発行

# OK: select_relatedで1回のクエリに
events = TransactionEvent.objects.select_related('month').all()
for event in events:
    print(event.month.year_month)  # クエリ発行なし
```

### 9.2 集計クエリの最適化

```python
from django.db.models import Sum, Count

# 月次サマリーの集計
monthly_summary = TransactionEvent.objects.filter(
    month__year_month='2025-01'
).aggregate(
    total_income=Sum('amount', filter=models.Q(amount__gt=0)),
    total_expense=Sum('amount', filter=models.Q(amount__lt=0)),
    event_count=Count('id')
)
```

## 10. データベース設定（settings.py）

### 10.1 開発環境（SQLite）

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

### 10.2 本番環境（PostgreSQL想定）

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'budget_simulator',
        'USER': 'budget_user',
        'PASSWORD': 'secure_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

## 11. 今後の拡張

### 11.1 追加予定テーブル

#### 11.1.1 EventSchedule（イベントスケジュール）
イベント発生日をカスタマイズ可能にする

| カラム名 | データ型 | 説明 |
|---------|---------|------|
| id | BigInteger | 主キー |
| event_type | Varchar(20) | イベント種類 |
| day_of_month | Integer | 発生日（1-31） |
| is_last_day | Boolean | 月末フラグ |

#### 11.1.2 User（ユーザー）
マルチユーザー対応

| カラム名 | データ型 | 説明 |
|---------|---------|------|
| id | BigInteger | 主キー |
| username | Varchar(150) | ユーザー名 |
| email | Varchar(254) | メールアドレス |
| created_at | DateTime | 作成日時 |

## 12. パフォーマンス指標

### 12.1 目標

- 月次計画取得: 10ms以内
- シミュレーション計算（12ヶ月）: 500ms以内
- イベント一覧取得（100件）: 50ms以内
- グラフデータ取得: 100ms以内

### 12.2 モニタリング

```python
# Django Debug Toolbarでクエリ実行時間を監視
INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
```
