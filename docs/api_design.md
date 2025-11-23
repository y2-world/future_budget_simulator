# API設計書 - 家計シミュレーター

## 1. 概要

本アプリケーションは Django のテンプレートベースのWebアプリケーションとして実装します。
将来的に REST API としての拡張も視野に入れた設計とします。

## 2. URL設計

### 2.1 URLパターン一覧

| URL | メソッド | ビュー | 説明 |
|-----|---------|-------|------|
| `/` | GET | `index` | トップページ |
| `/config/` | GET, POST | `config_view` | シミュレーション設定 |
| `/config/create/` | GET, POST | `config_create` | 設定新規作成 |
| `/config/<int:pk>/edit/` | GET, POST | `config_edit` | 設定編集 |
| `/plans/` | GET | `plan_list` | 月次計画一覧 |
| `/plans/create/` | GET, POST | `plan_create` | 月次計画新規作成 |
| `/plans/<int:pk>/edit/` | GET, POST | `plan_edit` | 月次計画編集 |
| `/plans/<int:pk>/delete/` | POST | `plan_delete` | 月次計画削除 |
| `/plans/<int:pk>/copy/` | POST | `plan_copy` | 月次計画複製 |
| `/simulate/` | POST | `simulate` | シミュレーション実行 |
| `/results/` | GET | `results_list` | 結果一覧 |
| `/results/table/` | GET | `results_table` | 結果テーブル表示 |
| `/results/graph/` | GET | `results_graph` | 結果グラフ表示 |
| `/results/summary/` | GET | `results_summary` | 結果サマリー表示 |
| `/export/csv/` | GET | `export_csv` | CSV エクスポート |
| `/admin/` | - | Django Admin | 管理画面 |

### 2.2 URLconf（urls.py）

#### プロジェクトレベル
```python
# future_budget_simulator/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('budget_app.urls')),
]
```

#### アプリケーションレベル
```python
# budget_app/urls.py
from django.urls import path
from . import views

app_name = 'budget_app'

urlpatterns = [
    # トップページ
    path('', views.index, name='index'),

    # シミュレーション設定
    path('config/', views.config_view, name='config'),
    path('config/create/', views.config_create, name='config_create'),
    path('config/<int:pk>/edit/', views.config_edit, name='config_edit'),

    # 月次計画
    path('plans/', views.plan_list, name='plan_list'),
    path('plans/create/', views.plan_create, name='plan_create'),
    path('plans/<int:pk>/edit/', views.plan_edit, name='plan_edit'),
    path('plans/<int:pk>/delete/', views.plan_delete, name='plan_delete'),
    path('plans/<int:pk>/copy/', views.plan_copy, name='plan_copy'),

    # シミュレーション実行
    path('simulate/', views.simulate, name='simulate'),

    # 結果表示
    path('results/', views.results_list, name='results_list'),
    path('results/table/', views.results_table, name='results_table'),
    path('results/graph/', views.results_graph, name='results_graph'),
    path('results/summary/', views.results_summary, name='results_summary'),

    # エクスポート
    path('export/csv/', views.export_csv, name='export_csv'),
]
```

## 3. ビュー設計

### 3.1 トップページ

#### `index`
```python
def index(request):
    """
    トップページ
    - 現在の設定を表示
    - 最新の月次計画を表示
    - シミュレーション実行ボタン
    """
    context = {
        'config': SimulationConfig.objects.filter(is_active=True).first(),
        'recent_plans': MonthlyPlan.objects.all()[:6],
        'has_plans': MonthlyPlan.objects.exists(),
    }
    return render(request, 'budget_app/index.html', context)
```

**レスポンス**
- テンプレート: `templates/budget_app/index.html`
- コンテキスト:
  - `config`: 有効なシミュレーション設定
  - `recent_plans`: 最新6件の月次計画
  - `has_plans`: 月次計画が存在するか

---

### 3.2 シミュレーション設定

#### `config_view`
```python
def config_view(request):
    """
    シミュレーション設定の表示・更新
    GET: 現在の設定を表示
    POST: 設定を更新
    """
    config = SimulationConfig.objects.filter(is_active=True).first()

    if request.method == 'POST':
        form = SimulationConfigForm(request.POST, instance=config)
        if form.is_valid():
            # 既存の有効設定を無効化
            SimulationConfig.objects.filter(is_active=True).update(is_active=False)
            # 新しい設定を有効化
            new_config = form.save(commit=False)
            new_config.is_active = True
            new_config.save()
            return redirect('budget_app:index')
    else:
        form = SimulationConfigForm(instance=config)

    return render(request, 'budget_app/config.html', {'form': form})
```

**フォームフィールド**
- `initial_balance`: 初期残高（整数、必須）
- `start_date`: 開始日（日付、必須）
- `simulation_months`: シミュレーション期間（整数、1-60、必須）

**バリデーション**
- 初期残高: 整数値
- 開始日: 有効な日付形式
- シミュレーション期間: 1〜60の範囲

---

### 3.3 月次計画管理

#### `plan_list`
```python
def plan_list(request):
    """
    月次計画一覧
    - すべての月次計画を年月順に表示
    - 各計画の収支サマリーを表示
    """
    plans = MonthlyPlan.objects.all().order_by('year_month')

    # 各計画に収支情報を追加
    for plan in plans:
        plan.total_income = plan.get_total_income()
        plan.total_expenses = plan.get_total_expenses()
        plan.net_income = plan.get_net_income()

    context = {
        'plans': plans,
        'total_plans': plans.count(),
    }
    return render(request, 'budget_app/plan_list.html', context)
```

#### `plan_create`
```python
def plan_create(request):
    """
    月次計画の新規作成
    GET: 空のフォームを表示（前月のデータを初期値として提案）
    POST: 新しい月次計画を保存
    """
    if request.method == 'POST':
        form = MonthlyPlanForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('budget_app:plan_list')
    else:
        # 前月のデータを取得
        year_month = request.GET.get('year_month')
        previous_plan = None

        if year_month:
            # 指定された月の前月を取得
            from datetime import datetime
            from dateutil.relativedelta import relativedelta

            date = datetime.strptime(year_month, '%Y-%m')
            prev_date = date - relativedelta(months=1)
            prev_year_month = prev_date.strftime('%Y-%m')

            previous_plan = MonthlyPlan.objects.filter(
                year_month=prev_year_month
            ).first()

        # 前月データを初期値として設定
        initial_data = {}
        if previous_plan:
            initial_data = {
                'salary': previous_plan.salary,
                'food': previous_plan.food,
                'rent': previous_plan.rent,
                'lake': previous_plan.lake,
                'credit': previous_plan.credit,
                'savings': previous_plan.savings,
                'utilities': previous_plan.utilities,
                'transportation': previous_plan.transportation,
                # ボーナスとローンは引き継がない
            }

        form = MonthlyPlanForm(initial=initial_data)

    return render(request, 'budget_app/plan_form.html', {
        'form': form,
        'title': '月次計画の作成'
    })
```

#### `plan_edit`
```python
def plan_edit(request, pk):
    """
    月次計画の編集
    GET: 既存データをフォームに表示
    POST: 更新内容を保存
    """
    plan = get_object_or_404(MonthlyPlan, pk=pk)

    if request.method == 'POST':
        form = MonthlyPlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            return redirect('budget_app:plan_list')
    else:
        form = MonthlyPlanForm(instance=plan)

    return render(request, 'budget_app/plan_form.html', {
        'form': form,
        'title': f'{plan.year_month} の編集'
    })
```

#### `plan_delete`
```python
def plan_delete(request, pk):
    """
    月次計画の削除
    POST: 指定された月次計画を削除（関連するTransactionEventも削除される）
    """
    plan = get_object_or_404(MonthlyPlan, pk=pk)

    if request.method == 'POST':
        plan.delete()
        messages.success(request, f'{plan.year_month} の計画を削除しました。')
        return redirect('budget_app:plan_list')

    return redirect('budget_app:plan_list')
```

#### `plan_copy`
```python
def plan_copy(request, pk):
    """
    月次計画の複製
    POST: 既存の計画を複製して新しい月の計画を作成
    """
    source_plan = get_object_or_404(MonthlyPlan, pk=pk)

    if request.method == 'POST':
        target_month = request.POST.get('target_month')

        # 既存チェック
        if MonthlyPlan.objects.filter(year_month=target_month).exists():
            messages.error(request, f'{target_month} の計画は既に存在します。')
            return redirect('budget_app:plan_list')

        # 複製
        new_plan = MonthlyPlan.objects.create(
            year_month=target_month,
            salary=source_plan.salary,
            food=source_plan.food,
            rent=source_plan.rent,
            lake=source_plan.lake,
            credit=source_plan.credit,
            savings=source_plan.savings,
            utilities=source_plan.utilities,
            transportation=source_plan.transportation,
            entertainment=source_plan.entertainment,
            other=source_plan.other,
            # ボーナスとローンは0にリセット
            bonus=0,
            loan=0,
        )

        messages.success(request, f'{target_month} の計画を作成しました。')
        return redirect('budget_app:plan_edit', pk=new_plan.pk)

    return redirect('budget_app:plan_list')
```

---

### 3.4 シミュレーション実行

#### `simulate`
```python
def simulate(request):
    """
    シミュレーションの実行
    POST: 月次計画を元にシミュレーションを実行し、TransactionEventを生成
    """
    if request.method != 'POST':
        return redirect('budget_app:index')

    # 有効な設定を取得
    config = SimulationConfig.objects.filter(is_active=True).first()
    if not config:
        messages.error(request, 'シミュレーション設定が見つかりません。')
        return redirect('budget_app:config')

    # シミュレーション期間の月リストを生成
    from datetime import datetime
    from dateutil.relativedelta import relativedelta

    start_date = config.start_date
    months = []
    for i in range(config.simulation_months):
        month_date = start_date + relativedelta(months=i)
        months.append(month_date.strftime('%Y-%m'))

    # 既存のTransactionEventを削除
    TransactionEvent.objects.all().delete()

    # 初期残高
    current_balance = config.initial_balance

    # イベント発生日の設定
    event_schedule = {
        'salary': 25,
        'bonus': 25,
        'food': 1,
        'rent': 27,
        'lake': 5,
        'credit': 10,
        'savings': 26,
        'loan': 15,
        'utilities': 20,
        'transportation': 1,
        'entertainment': 15,
        'other': -1,  # -1は月末
    }

    # 各月のイベントを生成
    for year_month in months:
        plan = MonthlyPlan.objects.filter(year_month=year_month).first()
        if not plan:
            continue

        # 年月から日付オブジェクトを作成
        year, month = map(int, year_month.split('-'))

        # 月末日を取得
        from calendar import monthrange
        last_day = monthrange(year, month)[1]

        # 各イベントを生成
        events = []

        # 収入イベント
        if plan.salary > 0:
            events.append({
                'date': datetime(year, month, event_schedule['salary']),
                'event_type': 'salary',
                'event_name': '給与',
                'amount': plan.salary,
            })

        if plan.bonus > 0:
            events.append({
                'date': datetime(year, month, event_schedule['bonus']),
                'event_type': 'bonus',
                'event_name': 'ボーナス',
                'amount': plan.bonus,
            })

        # 支出イベント
        if plan.food > 0:
            events.append({
                'date': datetime(year, month, event_schedule['food']),
                'event_type': 'food',
                'event_name': '食費',
                'amount': -plan.food,
            })

        if plan.rent > 0:
            events.append({
                'date': datetime(year, month, event_schedule['rent']),
                'event_type': 'rent',
                'event_name': '家賃',
                'amount': -plan.rent,
            })

        # ... 他の支出項目も同様に追加 ...

        # イベントを日付順にソート
        events.sort(key=lambda x: x['date'])

        # イベントを保存
        for event_data in events:
            current_balance += event_data['amount']

            TransactionEvent.objects.create(
                date=event_data['date'],
                event_type=event_data['event_type'],
                event_name=event_data['event_name'],
                amount=event_data['amount'],
                balance_after=current_balance,
                month=plan,
            )

    messages.success(request, 'シミュレーションが完了しました。')
    return redirect('budget_app:results_list')
```

---

### 3.5 結果表示

#### `results_list`
```python
def results_list(request):
    """
    結果一覧（ダッシュボード）
    - テーブル、グラフ、サマリーへのリンク
    - 簡易サマリーを表示
    """
    events = TransactionEvent.objects.all()

    if not events.exists():
        messages.info(request, 'シミュレーションを実行してください。')
        return redirect('budget_app:index')

    # 簡易サマリー
    from django.db.models import Sum, Min, Max

    summary = events.aggregate(
        start_balance=Min('balance_after'),
        end_balance=Max('balance_after'),
        total_income=Sum('amount', filter=models.Q(amount__gt=0)),
        total_expense=Sum('amount', filter=models.Q(amount__lt=0)),
    )

    context = {
        'event_count': events.count(),
        'summary': summary,
    }
    return render(request, 'budget_app/results_list.html', context)
```

#### `results_table`
```python
def results_table(request):
    """
    結果テーブル表示
    - すべてのTransactionEventを日付順に表示
    - ページネーション（100件/ページ）
    - フィルタリング機能
    """
    events = TransactionEvent.objects.select_related('month').all()

    # フィルタリング
    month_filter = request.GET.get('month')
    event_type_filter = request.GET.get('event_type')

    if month_filter:
        events = events.filter(month__year_month=month_filter)

    if event_type_filter:
        events = events.filter(event_type=event_type_filter)

    # ページネーション
    from django.core.paginator import Paginator
    paginator = Paginator(events, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'months': MonthlyPlan.objects.values_list('year_month', flat=True),
        'event_types': TransactionEvent.EVENT_TYPES,
    }
    return render(request, 'budget_app/results_table.html', context)
```

#### `results_graph`
```python
def results_graph(request):
    """
    結果グラフ表示
    - 残高推移の折れ線グラフ
    - Chart.jsでの描画
    """
    events = TransactionEvent.objects.all().order_by('date')

    # グラフ用データ
    labels = [event.date.strftime('%Y-%m-%d') for event in events]
    data = [event.balance_after for event in events]

    context = {
        'labels': labels,
        'data': data,
    }
    return render(request, 'budget_app/results_graph.html', context)
```

#### `results_summary`
```python
def results_summary(request):
    """
    結果サマリー表示
    - 月次サマリー
    - 全体サマリー
    """
    from django.db.models import Sum, Q

    # 月次サマリー
    monthly_summaries = []
    for plan in MonthlyPlan.objects.all():
        events = TransactionEvent.objects.filter(month=plan)

        if events.exists():
            summary = events.aggregate(
                total_income=Sum('amount', filter=Q(amount__gt=0)),
                total_expense=Sum('amount', filter=Q(amount__lt=0)),
            )

            first_event = events.first()
            last_event = events.last()

            monthly_summaries.append({
                'year_month': plan.year_month,
                'start_balance': first_event.balance_after - first_event.amount,
                'end_balance': last_event.balance_after,
                'total_income': summary['total_income'] or 0,
                'total_expense': summary['total_expense'] or 0,
                'net_income': (summary['total_income'] or 0) + (summary['total_expense'] or 0),
            })

    # 全体サマリー
    all_events = TransactionEvent.objects.all()
    overall_summary = all_events.aggregate(
        total_income=Sum('amount', filter=Q(amount__gt=0)),
        total_expense=Sum('amount', filter=Q(amount__lt=0)),
    )

    if all_events.exists():
        overall_summary['start_balance'] = all_events.first().balance_after - all_events.first().amount
        overall_summary['end_balance'] = all_events.last().balance_after
        overall_summary['net_income'] = (overall_summary['total_income'] or 0) + (overall_summary['total_expense'] or 0)

    context = {
        'monthly_summaries': monthly_summaries,
        'overall_summary': overall_summary,
    }
    return render(request, 'budget_app/results_summary.html', context)
```

---

### 3.6 エクスポート

#### `export_csv`
```python
import csv
from django.http import HttpResponse

def export_csv(request):
    """
    CSV エクスポート
    - すべてのTransactionEventをCSV形式でダウンロード
    """
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="simulation_results.csv"'

    # BOM付きUTF-8（Excelで正しく開けるように）
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow(['日付', 'イベント名', '金額', '残高'])

    events = TransactionEvent.objects.all().order_by('date')
    for event in events:
        writer.writerow([
            event.date.strftime('%Y-%m-%d'),
            event.event_name,
            event.amount,
            event.balance_after,
        ])

    return response
```

---

## 4. フォーム設計

### 4.1 SimulationConfigForm
```python
from django import forms
from .models import SimulationConfig

class SimulationConfigForm(forms.ModelForm):
    class Meta:
        model = SimulationConfig
        fields = ['initial_balance', 'start_date', 'simulation_months']
        widgets = {
            'initial_balance': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '例: 500000'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'simulation_months': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 60,
                'placeholder': '例: 12'
            }),
        }
        labels = {
            'initial_balance': '初期残高（円）',
            'start_date': 'シミュレーション開始日',
            'simulation_months': 'シミュレーション期間（月）',
        }
```

### 4.2 MonthlyPlanForm
```python
class MonthlyPlanForm(forms.ModelForm):
    class Meta:
        model = MonthlyPlan
        fields = [
            'year_month', 'salary', 'bonus',
            'food', 'rent', 'lake', 'credit', 'savings', 'loan',
            'utilities', 'transportation', 'entertainment', 'other'
        ]
        widgets = {
            'year_month': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'YYYY-MM',
                'pattern': r'\d{4}-\d{2}'
            }),
            # 他のフィールドも同様にNumberInput
        }
```

---

## 5. テンプレート設計

### 5.1 ベーステンプレート
```html
<!-- templates/budget_app/base.html -->
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}家計シミュレーター{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2/dist/tailwind.min.css" rel="stylesheet">
    {% block extra_css %}{% endblock %}
</head>
<body class="bg-gray-100">
    <nav class="bg-blue-600 text-white p-4">
        <!-- ナビゲーション -->
    </nav>

    <main class="container mx-auto p-4">
        {% if messages %}
            {% for message in messages %}
                <div class="alert alert-{{ message.tags }}">
                    {{ message }}
                </div>
            {% endfor %}
        {% endif %}

        {% block content %}{% endblock %}
    </main>

    <footer class="bg-gray-800 text-white p-4 mt-8">
        <!-- フッター -->
    </footer>

    {% block extra_js %}{% endblock %}
</body>
</html>
```

---

## 6. エラーハンドリング

### 6.1 404エラー
```python
def handler404(request, exception):
    return render(request, 'budget_app/404.html', status=404)
```

### 6.2 500エラー
```python
def handler500(request):
    return render(request, 'budget_app/500.html', status=500)
```

---

## 7. 将来のREST API設計（参考）

### 7.1 エンドポイント案
- `GET /api/plans/`: 月次計画一覧
- `POST /api/plans/`: 月次計画作成
- `GET /api/plans/{id}/`: 月次計画詳細
- `PUT /api/plans/{id}/`: 月次計画更新
- `DELETE /api/plans/{id}/`: 月次計画削除
- `POST /api/simulate/`: シミュレーション実行
- `GET /api/results/`: 結果取得

### 7.2 実装方法
Django REST frameworkを使用する想定

```python
pip install djangorestframework
```

---

## 8. セキュリティ対策

### 8.1 CSRF対策
- Django標準のCSRFトークンを使用
- すべてのPOSTリクエストに `{% csrf_token %}` を含める

### 8.2 XSS対策
- テンプレートの自動エスケープを有効化（Django標準）
- ユーザー入力は必ずエスケープ

### 8.3 SQLインジェクション対策
- Django ORMを使用（生のSQLは避ける）

---

## 9. パフォーマンス最適化

### 9.1 クエリ最適化
- `select_related()` で外部キーを事前ロード
- `prefetch_related()` で多対多を事前ロード

### 9.2 キャッシング
```python
from django.views.decorators.cache import cache_page

@cache_page(60 * 15)  # 15分間キャッシュ
def results_graph(request):
    # ...
```
