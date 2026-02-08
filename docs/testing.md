# テストとカバレッジ測定ガイド

## 概要

このドキュメントは、家計シミュレーターアプリケーションのテスト実行とカバレッジ測定について説明します。

## テストの実行

### 基本的なテスト実行

```bash
# すべてのテストを実行
python manage.py test budget_app.tests

# 特定のテストクラスのみ実行
python manage.py test budget_app.tests.CreditCardLogicTests

# 特定のテストメソッドのみ実行
python manage.py test budget_app.tests.CreditCardLogicTests.test_closing_date_calculation_various_cards

# 詳細出力（verbosity level 2）
python manage.py test budget_app.tests -v 2
```

### テストの自動実行（pre-pushフック）

このプロジェクトでは、gitのpre-pushフックが設定されており、`git push`実行時に自動的にテストが実行されます。

```bash
# git pushすると自動的にテストが実行される
git push origin master

# テストが失敗するとpushが中止される
# テストをスキップしてpushする場合（非推奨）
git push --no-verify origin master
```

**pre-pushフックの動作**:
1. テストをカバレッジ測定付きで実行
2. テストが失敗した場合、pushを中止
3. テストが成功した場合、カバレッジレポートを表示
4. カバレッジが80%未満の場合、警告を表示（pushは許可）

## カバレッジ測定

### coverage.pyとは

coverage.pyは、Pythonコードのどの部分がテストで実行されたかを測定するツールです。

### 基本的なカバレッジ測定

```bash
# カバレッジ測定付きでテストを実行
coverage run --source='budget_app' manage.py test budget_app.tests

# カバレッジレポートを表示（ターミナル）
coverage report

# カバレッジが低いファイルのみ表示
coverage report --skip-covered

# 詳細なカバレッジレポート（HTML）を生成
coverage html

# HTMLレポートをブラウザで開く
open htmlcov/index.html  # macOS
# または
xdg-open htmlcov/index.html  # Linux
```

### カバレッジレポートの見方

#### ターミナル出力例

```
Name                                Stmts   Miss  Cover
-------------------------------------------------------
budget_app/__init__.py                  0      0   100%
budget_app/admin.py                    15      0   100%
budget_app/models.py                  120      5    96%
budget_app/views.py                   450     45    90%
budget_app/middleware.py               25      3    88%
-------------------------------------------------------
TOTAL                                 610     53    91%
```

- **Stmts**: 実行可能な文の総数
- **Miss**: テストで実行されなかった文の数
- **Cover**: カバレッジ率（％）

#### HTMLレポート

HTMLレポートでは、以下を確認できます：
- ファイルごとのカバレッジ詳細
- 実行された行（緑色）と実行されなかった行（赤色）
- ブランチカバレッジ（if文などの分岐）

### カバレッジの目標

このプロジェクトのカバレッジ目標は **80%以上** です（`.coveragerc`で設定）。

```bash
# カバレッジが80%未満の場合、エラーを返す
coverage report --fail-under=80
```

### カバレッジ設定（.coveragerc）

カバレッジ測定の設定は`.coveragerc`ファイルで管理されています。

```ini
[run]
source = budget_app
omit =
    */migrations/*      # マイグレーションファイルを除外
    */tests.py          # テストファイル自体を除外
    */test_*.py
    */__pycache__/*
    */venv/*
    manage.py

[report]
precision = 2           # カバレッジを小数点2桁まで表示
show_missing = True     # カバーされていない行番号を表示
fail_under = 80         # 最低カバレッジ基準: 80%
```

## テストコードの構成

### テストファイル

- `budget_app/tests.py`: すべてのテストコード（430行、25テスト）

### テストクラス

1. **HelperFunctionTests**: ヘルパー関数のテスト（7テスト）
   - 締め日計算、請求月計算、奇数月判定など

2. **MonthlyPlanModelTests**: MonthlyPlanモデルのテスト（3テスト）
   - データ保存、検証、デフォルト値など

3. **SimulationLogicTests**: シミュレーションロジックのテスト（8テスト）
   - 残高計算、営業日調整、イベント生成など

4. **CreditCardLogicTests**: クレジットカード処理のテスト（7テスト）
   - 締め日計算、請求月計算、分割払い、ボーナス払いなど

### テストカバレッジの内訳

- **models.py**: 96% カバレッジ
- **views.py**: 90% カバレッジ
- **helper functions**: 95% カバレッジ
- **middleware.py**: 88% カバレッジ

## テストのベストプラクティス

### 1. テストの追加タイミング

- 新機能を実装する前にテストを書く（TDD: Test-Driven Development）
- バグを修正する際、そのバグを再現するテストを先に書く
- 複雑なロジックには必ずテストを追加する

### 2. テストの命名規則

```python
def test_<対象機能>_<条件>_<期待結果>(self):
    """テストの説明をdocstringで記述"""
    pass

# 例
def test_closing_date_calculation_various_cards(self):
    """様々なカードの締め日計算テスト"""
    pass
```

### 3. テストの独立性

- 各テストは独立して実行可能であること
- テスト間でデータベース状態を共有しない
- `setUp()`と`tearDown()`を適切に使用

### 4. アサーションメッセージ

```python
# 良い例: エラーメッセージを含める
self.assertEqual(result, expected,
                 f"Expected {expected}, but got {result}")

# 悪い例: メッセージなし
self.assertEqual(result, expected)
```

### 5. テストデータの管理

```python
# setUp()でテストデータを準備
def setUp(self):
    self.card = MonthlyPlanDefault.objects.create(
        key='rakuten',
        title='楽天カード',
        closing_day=5
    )

# 各テストで使用
def test_something(self):
    self.assertEqual(self.card.closing_day, 5)
```

## テストのトラブルシューティング

### テストが失敗する

1. **エラーメッセージを確認**
   ```bash
   python manage.py test budget_app.tests -v 2
   ```

2. **特定のテストのみ実行して詳細を確認**
   ```bash
   python manage.py test budget_app.tests.CreditCardLogicTests.test_split_payment_billing_month -v 2
   ```

3. **デバッグ出力を追加**
   ```python
   def test_something(self):
       print(f"Debug: value = {value}")
       self.assertEqual(value, expected)
   ```

### カバレッジが低い

1. **カバーされていない行を確認**
   ```bash
   coverage report --show-missing
   ```

2. **HTMLレポートで詳細を確認**
   ```bash
   coverage html
   open htmlcov/index.html
   ```

3. **未カバーのコードパスにテストを追加**

### pre-pushフックが動作しない

1. **フックファイルの実行権限を確認**
   ```bash
   chmod +x .git/hooks/pre-push
   ```

2. **フックファイルの内容を確認**
   ```bash
   cat .git/hooks/pre-push
   ```

3. **仮想環境のパスを確認**
   ```bash
   which python
   # venv/bin/python であるべき
   ```

## CI/CD統合（将来の拡張）

将来的には、以下のCI/CDツールと統合できます：

### GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.13
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run tests with coverage
        run: |
          coverage run manage.py test budget_app.tests
          coverage report --fail-under=80
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v2
```

## 参考コマンド集

```bash
# テスト実行
python manage.py test budget_app.tests                    # すべてのテスト
python manage.py test budget_app.tests -v 2               # 詳細出力
python manage.py test budget_app.tests --keepdb           # DBを保持して高速化

# カバレッジ測定
coverage run --source='budget_app' manage.py test budget_app.tests
coverage report                                            # レポート表示
coverage report --skip-covered                             # カバー済みをスキップ
coverage report --fail-under=80                            # 80%未満でエラー
coverage html                                              # HTMLレポート生成
coverage erase                                             # カバレッジデータ削除

# pre-pushフック
git push origin master                                     # フック自動実行
git push --no-verify origin master                         # フックをスキップ（非推奨）

# カバレッジとテストの一括実行
coverage run --source='budget_app' manage.py test budget_app.tests && coverage report
```

## まとめ

- テストは`python manage.py test`で実行
- カバレッジは`coverage run`と`coverage report`で測定
- HTMLレポートで詳細なカバレッジを確認
- pre-pushフックでpush前に自動テスト実行
- カバレッジ目標は80%以上
- テストは独立性を保ち、明確な命名規則に従う
