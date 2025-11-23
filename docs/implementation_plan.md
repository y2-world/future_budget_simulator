# 実装計画 - 家計シミュレーター

## 1. 実装概要

このドキュメントでは、家計シミュレーターの実装手順を段階的に説明します。
セッションが途切れても作業を再開できるよう、各ステップを詳細に記載しています。

## 2. 現在の状態

### 完了済み
- ✅ Djangoプロジェクトの作成
- ✅ budget_appアプリケーションの作成
- ✅ データモデルの定義（models.py）
- ✅ 設定ファイルの基本設定（settings.py）
- ✅ ドキュメントの作成

### 未完了
- ⬜ データベースマイグレーション
- ⬜ 管理画面の設定
- ⬜ フォームの作成
- ⬜ ビューの実装
- ⬜ URLルーティングの設定
- ⬜ テンプレートの作成
- ⬜ 静的ファイルの設定
- ⬜ シミュレーションロジックの実装
- ⬜ テスト作成
- ⬜ デプロイ準備

## 3. 実装フェーズ

### フェーズ1: 基盤構築（最優先）
データベースと管理画面を整備し、データの CRUD 操作ができる状態にする。

### フェーズ2: コア機能実装
月次計画の入力とシミュレーション実行機能を実装する。

### フェーズ3: UI/UX改善
フロントエンドを整備し、使いやすいインターフェースを提供する。

### フェーズ4: 拡張機能
CSV入出力、グラフ表示などの付加機能を追加する。

---

## 4. フェーズ1: 基盤構築

### ステップ1.1: データベースマイグレーション

**目的**: モデルをデータベースに反映させる

**作業内容**:
```bash
# マイグレーションファイルの生成
python manage.py makemigrations budget_app

# マイグレーションの適用
python manage.py migrate

# 結果確認
python manage.py showmigrations
```

**確認項目**:
- [ ] マイグレーションファイルが生成されている
- [ ] すべてのテーブルが作成されている
- [ ] エラーが発生していない

**トラブルシューティング**:
- エラーが発生した場合は、models.pyの記述を確認
- 既存のdb.sqlite3を削除して再実行も検討

---

### ステップ1.2: スーパーユーザーの作成

**目的**: 管理画面にアクセスできるユーザーを作成

**作業内容**:
```bash
python manage.py createsuperuser
```

**入力内容**:
- Username: admin（任意）
- Email: （任意、スキップ可）
- Password: （8文字以上）

**確認項目**:
- [ ] スーパーユーザーが作成された
- [ ] http://127.0.0.1:8000/admin/ にアクセスできる
- [ ] ログインできる

---

### ステップ1.3: 管理画面の設定

**目的**: すべてのモデルを管理画面で操作可能にする

**ファイル**: `budget_app/admin.py`

**実装内容**:
```python
from django.contrib import admin
from .models import (
    SimulationConfig,
    AccountBalance,
    MonthlyPlan,
    TransactionEvent
)


@admin.register(SimulationConfig)
class SimulationConfigAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'initial_balance', 'start_date',
        'simulation_months', 'is_active', 'created_at'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['id']
    ordering = ['-created_at']


@admin.register(AccountBalance)
class AccountBalanceAdmin(admin.ModelAdmin):
    list_display = ['date', 'balance', 'source', 'last_updated']
    list_filter = ['source', 'date']
    search_fields = ['date']
    ordering = ['-date']


@admin.register(MonthlyPlan)
class MonthlyPlanAdmin(admin.ModelAdmin):
    list_display = [
        'year_month', 'salary', 'bonus',
        'get_total_income', 'get_total_expenses', 'get_net_income',
        'updated_at'
    ]
    list_filter = ['year_month']
    search_fields = ['year_month']
    ordering = ['year_month']

    fieldsets = (
        ('基本情報', {
            'fields': ('year_month',)
        }),
        ('収入', {
            'fields': ('salary', 'bonus')
        }),
        ('固定費', {
            'fields': ('rent', 'utilities')
        }),
        ('変動費', {
            'fields': ('food', 'transportation', 'entertainment')
        }),
        ('ローン・返済', {
            'fields': ('lake', 'loan', 'credit')
        }),
        ('貯蓄', {
            'fields': ('savings',)
        }),
        ('その他', {
            'fields': ('other',)
        }),
    )


@admin.register(TransactionEvent)
class TransactionEventAdmin(admin.ModelAdmin):
    list_display = [
        'date', 'event_name', 'amount',
        'balance_after', 'month', 'created_at'
    ]
    list_filter = ['event_type', 'date', 'month']
    search_fields = ['event_name', 'event_type']
    ordering = ['date', 'id']
    readonly_fields = ['created_at']
```

**確認項目**:
- [ ] 管理画面で4つのモデルが表示される
- [ ] 各モデルのデータを作成・編集・削除できる
- [ ] リスト表示が適切に設定されている

---

### ステップ1.4: テストデータの投入

**目的**: 動作確認用のサンプルデータを作成

**作業内容**:

管理画面から以下のデータを手動で作成:

1. **SimulationConfig**
   - initial_balance: 500000
   - start_date: 2025-01-01
   - simulation_months: 12
   - is_active: True

2. **MonthlyPlan（3ヶ月分）**

   **2025-01**:
   - salary: 300000
   - food: 50000
   - rent: 80000
   - credit: 30000
   - utilities: 15000

   **2025-02**:
   - salary: 300000
   - food: 50000
   - rent: 80000
   - credit: 30000
   - utilities: 15000

   **2025-06**（ボーナス月）:
   - salary: 300000
   - bonus: 500000
   - food: 50000
   - rent: 80000
   - credit: 30000
   - utilities: 15000

**確認項目**:
- [ ] データが正しく保存される
- [ ] 一覧画面で表示される
- [ ] 編集・削除ができる

---

## 5. フェーズ2: コア機能実装

### ステップ2.1: URLルーティングの設定

**目的**: URLとビューを紐付ける

**ファイル**: `budget_app/urls.py`（新規作成）

**実装内容**:
```python
from django.urls import path
from . import views

app_name = 'budget_app'

urlpatterns = [
    # トップページ
    path('', views.index, name='index'),

    # シミュレーション設定
    path('config/', views.config_view, name='config'),

    # 月次計画
    path('plans/', views.plan_list, name='plan_list'),
    path('plans/create/', views.plan_create, name='plan_create'),
    path('plans/<int:pk>/edit/', views.plan_edit, name='plan_edit'),
    path('plans/<int:pk>/delete/', views.plan_delete, name='plan_delete'),

    # シミュレーション実行
    path('simulate/', views.simulate, name='simulate'),

    # 結果表示
    path('results/', views.results_list, name='results_list'),
]
```

**ファイル**: `future_budget_simulator/urls.py`（既存ファイルの編集）

**実装内容**:
```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('budget_app.urls')),  # 追加
]
```

**確認項目**:
- [ ] urls.pyファイルが正しく作成されている
- [ ] プロジェクトのurls.pyにincludeが追加されている

---

### ステップ2.2: フォームの作成

**目的**: データ入力用のフォームを定義

**ファイル**: `budget_app/forms.py`（新規作成）

**実装内容**:
```python
from django import forms
from .models import SimulationConfig, MonthlyPlan


class SimulationConfigForm(forms.ModelForm):
    """シミュレーション設定フォーム"""

    class Meta:
        model = SimulationConfig
        fields = ['initial_balance', 'start_date', 'simulation_months']
        widgets = {
            'initial_balance': forms.NumberInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': '例: 500000'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'w-full p-2 border rounded',
                'type': 'date'
            }),
            'simulation_months': forms.NumberInput(attrs={
                'class': 'w-full p-2 border rounded',
                'min': 1,
                'max': 60,
                'value': 12
            }),
        }
        labels = {
            'initial_balance': '初期残高（円）',
            'start_date': 'シミュレーション開始日',
            'simulation_months': 'シミュレーション期間（月）',
        }


class MonthlyPlanForm(forms.ModelForm):
    """月次計画フォーム"""

    class Meta:
        model = MonthlyPlan
        fields = [
            'year_month',
            'salary', 'bonus',
            'food', 'rent', 'lake', 'credit',
            'savings', 'loan', 'utilities',
            'transportation', 'entertainment', 'other'
        ]

        widgets = {
            'year_month': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': 'YYYY-MM',
                'pattern': r'\d{4}-\d{2}'
            }),
        }

        labels = {
            'year_month': '年月（YYYY-MM）',
            'salary': '給与',
            'bonus': 'ボーナス',
            'food': '食費',
            'rent': '家賃',
            'lake': 'レイク返済',
            'credit': 'クレカ引落',
            'savings': '定期預金',
            'loan': 'マネーアシスト返済',
            'utilities': '光熱費',
            'transportation': '交通費',
            'entertainment': '娯楽費',
            'other': 'その他',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # すべての数値入力フィールドに共通のクラスを適用
        for field_name in self.fields:
            if field_name != 'year_month':
                self.fields[field_name].widget.attrs.update({
                    'class': 'w-full p-2 border rounded',
                    'min': 0
                })
```

**確認項目**:
- [ ] forms.pyファイルが作成されている
- [ ] 2つのフォームクラスが定義されている
- [ ] ウィジェットが適切に設定されている

---

### ステップ2.3: ビューの実装（基本）

**目的**: ページ表示とデータ処理のロジックを実装

**ファイル**: `budget_app/views.py`

**実装内容**:

まず、必要なインポートを追加:
```python
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import (
    SimulationConfig,
    MonthlyPlan,
    TransactionEvent
)
from .forms import SimulationConfigForm, MonthlyPlanForm
```

次に、各ビュー関数を実装:

```python
def index(request):
    """トップページ"""
    config = SimulationConfig.objects.filter(is_active=True).first()
    plans = MonthlyPlan.objects.all().order_by('year_month')[:6]
    has_plans = MonthlyPlan.objects.exists()

    context = {
        'config': config,
        'plans': plans,
        'has_plans': has_plans,
    }
    return render(request, 'budget_app/index.html', context)


def config_view(request):
    """シミュレーション設定"""
    config = SimulationConfig.objects.filter(is_active=True).first()

    if request.method == 'POST':
        form = SimulationConfigForm(request.POST, instance=config)
        if form.is_valid():
            # 既存の有効設定を無効化
            SimulationConfig.objects.filter(is_active=True).update(is_active=False)
            # 新しい設定を保存
            new_config = form.save(commit=False)
            new_config.is_active = True
            new_config.save()
            messages.success(request, 'シミュレーション設定を保存しました。')
            return redirect('budget_app:index')
    else:
        form = SimulationConfigForm(instance=config)

    return render(request, 'budget_app/config.html', {'form': form})


def plan_list(request):
    """月次計画一覧"""
    plans = MonthlyPlan.objects.all().order_by('year_month')

    # 各計画に収支情報を追加
    for plan in plans:
        plan.total_income = plan.get_total_income()
        plan.total_expenses = plan.get_total_expenses()
        plan.net_income = plan.get_net_income()

    return render(request, 'budget_app/plan_list.html', {'plans': plans})


def plan_create(request):
    """月次計画作成"""
    if request.method == 'POST':
        form = MonthlyPlanForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '月次計画を作成しました。')
            return redirect('budget_app:plan_list')
    else:
        form = MonthlyPlanForm()

    return render(request, 'budget_app/plan_form.html', {
        'form': form,
        'title': '月次計画の作成'
    })


def plan_edit(request, pk):
    """月次計画編集"""
    plan = get_object_or_404(MonthlyPlan, pk=pk)

    if request.method == 'POST':
        form = MonthlyPlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, f'{plan.year_month} の計画を更新しました。')
            return redirect('budget_app:plan_list')
    else:
        form = MonthlyPlanForm(instance=plan)

    return render(request, 'budget_app/plan_form.html', {
        'form': form,
        'title': f'{plan.year_month} の編集'
    })


def plan_delete(request, pk):
    """月次計画削除"""
    plan = get_object_or_404(MonthlyPlan, pk=pk)

    if request.method == 'POST':
        year_month = plan.year_month
        plan.delete()
        messages.success(request, f'{year_month} の計画を削除しました。')

    return redirect('budget_app:plan_list')


def simulate(request):
    """シミュレーション実行（仮実装）"""
    if request.method == 'POST':
        messages.info(request, 'シミュレーション機能は次のステップで実装します。')
        return redirect('budget_app:index')

    return redirect('budget_app:index')


def results_list(request):
    """結果一覧（仮実装）"""
    messages.info(request, '結果表示機能は次のステップで実装します。')
    return redirect('budget_app:index')
```

**確認項目**:
- [ ] views.pyにすべての関数が実装されている
- [ ] インポート文が追加されている
- [ ] エラーが発生していない

---

### ステップ2.4: テンプレートの作成（基本）

**目的**: HTMLテンプレートを作成してページを表示

**ディレクトリ構成**:
```
budget_app/
└── templates/
    └── budget_app/
        ├── base.html
        ├── index.html
        ├── config.html
        ├── plan_list.html
        └── plan_form.html
```

**作業手順**:

1. ディレクトリ作成:
```bash
mkdir -p budget_app/templates/budget_app
```

2. ベーステンプレート作成:

**ファイル**: `budget_app/templates/budget_app/base.html`

```html
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}家計シミュレーター{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100">
    <nav class="bg-blue-600 text-white shadow-lg">
        <div class="container mx-auto px-4 py-3">
            <div class="flex justify-between items-center">
                <h1 class="text-2xl font-bold">家計シミュレーター</h1>
                <div class="space-x-4">
                    <a href="{% url 'budget_app:index' %}" class="hover:underline">ホーム</a>
                    <a href="{% url 'budget_app:config' %}" class="hover:underline">設定</a>
                    <a href="{% url 'budget_app:plan_list' %}" class="hover:underline">月次計画</a>
                    <a href="/admin/" class="hover:underline">管理画面</a>
                </div>
            </div>
        </div>
    </nav>

    <main class="container mx-auto px-4 py-8">
        {% if messages %}
            <div class="mb-4">
                {% for message in messages %}
                    <div class="p-4 mb-2 rounded {% if message.tags == 'success' %}bg-green-100 text-green-800{% elif message.tags == 'error' %}bg-red-100 text-red-800{% else %}bg-blue-100 text-blue-800{% endif %}">
                        {{ message }}
                    </div>
                {% endfor %}
            </div>
        {% endif %}

        {% block content %}{% endblock %}
    </main>

    <footer class="bg-gray-800 text-white py-4 mt-12">
        <div class="container mx-auto px-4 text-center">
            <p>&copy; 2025 家計シミュレーター</p>
        </div>
    </footer>
</body>
</html>
```

3. トップページ:

**ファイル**: `budget_app/templates/budget_app/index.html`

```html
{% extends 'budget_app/base.html' %}

{% block content %}
<div class="bg-white rounded-lg shadow-md p-6 mb-6">
    <h2 class="text-3xl font-bold mb-4">ようこそ</h2>
    <p class="text-gray-700 mb-4">月ごとの収支を入力して、将来の口座残高を確認しましょう。</p>

    {% if config %}
        <div class="bg-blue-50 p-4 rounded mb-4">
            <h3 class="font-bold text-lg mb-2">現在の設定</h3>
            <ul class="list-disc list-inside">
                <li>初期残高: ¥{{ config.initial_balance|floatformat:0 }}</li>
                <li>開始日: {{ config.start_date }}</li>
                <li>シミュレーション期間: {{ config.simulation_months }}ヶ月</li>
            </ul>
        </div>
    {% else %}
        <div class="bg-yellow-50 p-4 rounded mb-4">
            <p class="text-yellow-800">シミュレーション設定がありません。</p>
            <a href="{% url 'budget_app:config' %}" class="text-blue-600 hover:underline">設定を作成</a>
        </div>
    {% endif %}

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
        <a href="{% url 'budget_app:config' %}" class="bg-blue-500 text-white p-4 rounded hover:bg-blue-600 text-center">
            シミュレーション設定
        </a>
        <a href="{% url 'budget_app:plan_list' %}" class="bg-green-500 text-white p-4 rounded hover:bg-green-600 text-center">
            月次計画管理
        </a>
    </div>

    {% if has_plans %}
        <form method="post" action="{% url 'budget_app:simulate' %}" class="mt-6">
            {% csrf_token %}
            <button type="submit" class="w-full bg-red-500 text-white p-4 rounded hover:bg-red-600 text-lg font-bold">
                シミュレーション実行
            </button>
        </form>
    {% endif %}
</div>

{% if plans %}
<div class="bg-white rounded-lg shadow-md p-6">
    <h3 class="text-2xl font-bold mb-4">最新の月次計画</h3>
    <div class="overflow-x-auto">
        <table class="w-full">
            <thead class="bg-gray-100">
                <tr>
                    <th class="p-2 text-left">年月</th>
                    <th class="p-2 text-right">給与</th>
                    <th class="p-2 text-right">ボーナス</th>
                    <th class="p-2 text-right">支出計</th>
                </tr>
            </thead>
            <tbody>
                {% for plan in plans %}
                <tr class="border-t">
                    <td class="p-2">{{ plan.year_month }}</td>
                    <td class="p-2 text-right">¥{{ plan.salary|floatformat:0 }}</td>
                    <td class="p-2 text-right">¥{{ plan.bonus|floatformat:0 }}</td>
                    <td class="p-2 text-right">-</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endif %}
{% endblock %}
```

4. その他のテンプレート:

**ファイル**: `budget_app/templates/budget_app/config.html`
```html
{% extends 'budget_app/base.html' %}

{% block content %}
<div class="bg-white rounded-lg shadow-md p-6 max-w-2xl mx-auto">
    <h2 class="text-2xl font-bold mb-6">シミュレーション設定</h2>

    <form method="post">
        {% csrf_token %}
        {% for field in form %}
            <div class="mb-4">
                <label class="block text-gray-700 font-bold mb-2">{{ field.label }}</label>
                {{ field }}
                {% if field.errors %}
                    <p class="text-red-500 text-sm mt-1">{{ field.errors.0 }}</p>
                {% endif %}
            </div>
        {% endfor %}

        <button type="submit" class="w-full bg-blue-500 text-white p-3 rounded hover:bg-blue-600 font-bold">
            保存
        </button>
    </form>
</div>
{% endblock %}
```

**ファイル**: `budget_app/templates/budget_app/plan_list.html`
```html
{% extends 'budget_app/base.html' %}

{% block content %}
<div class="bg-white rounded-lg shadow-md p-6">
    <div class="flex justify-between items-center mb-6">
        <h2 class="text-2xl font-bold">月次計画一覧</h2>
        <a href="{% url 'budget_app:plan_create' %}" class="bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600">
            新規作成
        </a>
    </div>

    {% if plans %}
        <div class="overflow-x-auto">
            <table class="w-full">
                <thead class="bg-gray-100">
                    <tr>
                        <th class="p-3 text-left">年月</th>
                        <th class="p-3 text-right">総収入</th>
                        <th class="p-3 text-right">総支出</th>
                        <th class="p-3 text-right">純収支</th>
                        <th class="p-3 text-center">操作</th>
                    </tr>
                </thead>
                <tbody>
                    {% for plan in plans %}
                    <tr class="border-t hover:bg-gray-50">
                        <td class="p-3">{{ plan.year_month }}</td>
                        <td class="p-3 text-right text-green-600">¥{{ plan.total_income|floatformat:0 }}</td>
                        <td class="p-3 text-right text-red-600">¥{{ plan.total_expenses|floatformat:0 }}</td>
                        <td class="p-3 text-right {% if plan.net_income >= 0 %}text-green-600{% else %}text-red-600{% endif %}">
                            ¥{{ plan.net_income|floatformat:0 }}
                        </td>
                        <td class="p-3 text-center space-x-2">
                            <a href="{% url 'budget_app:plan_edit' plan.pk %}" class="text-blue-600 hover:underline">編集</a>
                            <form method="post" action="{% url 'budget_app:plan_delete' plan.pk %}" class="inline" onsubmit="return confirm('本当に削除しますか？')">
                                {% csrf_token %}
                                <button type="submit" class="text-red-600 hover:underline">削除</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    {% else %}
        <p class="text-gray-600">月次計画がありません。</p>
        <a href="{% url 'budget_app:plan_create' %}" class="text-blue-600 hover:underline">最初の計画を作成</a>
    {% endif %}
</div>
{% endblock %}
```

**ファイル**: `budget_app/templates/budget_app/plan_form.html`
```html
{% extends 'budget_app/base.html' %}

{% block content %}
<div class="bg-white rounded-lg shadow-md p-6 max-w-4xl mx-auto">
    <h2 class="text-2xl font-bold mb-6">{{ title }}</h2>

    <form method="post">
        {% csrf_token %}

        <div class="mb-6">
            <label class="block text-gray-700 font-bold mb-2">{{ form.year_month.label }}</label>
            {{ form.year_month }}
            {% if form.year_month.errors %}
                <p class="text-red-500 text-sm mt-1">{{ form.year_month.errors.0 }}</p>
            {% endif %}
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="bg-green-50 p-4 rounded">
                <h3 class="font-bold text-lg mb-4 text-green-800">収入</h3>
                {% for field in form %}
                    {% if field.name == 'salary' or field.name == 'bonus' %}
                        <div class="mb-4">
                            <label class="block text-gray-700 font-bold mb-2">{{ field.label }}</label>
                            {{ field }}
                        </div>
                    {% endif %}
                {% endfor %}
            </div>

            <div class="bg-red-50 p-4 rounded">
                <h3 class="font-bold text-lg mb-4 text-red-800">支出</h3>
                {% for field in form %}
                    {% if field.name != 'year_month' and field.name != 'salary' and field.name != 'bonus' %}
                        <div class="mb-4">
                            <label class="block text-gray-700 font-bold mb-2">{{ field.label }}</label>
                            {{ field }}
                        </div>
                    {% endif %}
                {% endfor %}
            </div>
        </div>

        <div class="mt-6 flex space-x-4">
            <button type="submit" class="flex-1 bg-blue-500 text-white p-3 rounded hover:bg-blue-600 font-bold">
                保存
            </button>
            <a href="{% url 'budget_app:plan_list' %}" class="flex-1 bg-gray-500 text-white p-3 rounded hover:bg-gray-600 font-bold text-center">
                キャンセル
            </a>
        </div>
    </form>
</div>
{% endblock %}
```

**確認項目**:
- [ ] すべてのテンプレートファイルが作成されている
- [ ] ディレクトリ構造が正しい
- [ ] HTMLに構文エラーがない

---

### ステップ2.5: 動作確認

**作業内容**:
```bash
# 開発サーバーの起動
python manage.py runserver
```

**確認URL**:
- http://127.0.0.1:8000/ - トップページ
- http://127.0.0.1:8000/config/ - シミュレーション設定
- http://127.0.0.1:8000/plans/ - 月次計画一覧
- http://127.0.0.1:8000/plans/create/ - 月次計画作成

**確認項目**:
- [ ] すべてのページが表示される
- [ ] ナビゲーションリンクが機能する
- [ ] フォーム送信ができる
- [ ] データが保存される
- [ ] メッセージが表示される
- [ ] エラーが発生していない

---

## 6. フェーズ3: シミュレーションロジック実装

### ステップ3.1: シミュレーション計算処理の実装

**目的**: 月次計画からTransactionEventを生成する

**ファイル**: `budget_app/services.py`（新規作成）

このステップは次回のセッションで実装予定。
詳細はAPI設計書の `simulate` ビューを参照。

---

## 7. フェーズ4: 結果表示機能

このフェーズは後続のセッションで実装予定。

---

## 8. 次回セッション開始時のチェックリスト

セッションが途切れて再開する際は、以下を確認してください:

1. **プロジェクトディレクトリの確認**
   ```bash
   cd /Users/yukiyoshida/future_budget_simulator
   ls
   ```

2. **ドキュメントの確認**
   ```bash
   ls docs/
   cat docs/implementation_plan.md
   ```

3. **現在の実装状況の確認**
   - [ ] データベースマイグレーション済みか
   - [ ] 管理画面の設定済みか
   - [ ] ビューの実装済みか
   - [ ] テンプレートの作成済みか
   - [ ] 基本機能の動作確認済みか

4. **サーバーの起動**
   ```bash
   python manage.py runserver
   ```

5. **ブラウザで動作確認**
   - トップページが表示されるか
   - 月次計画の作成・編集ができるか

---

## 9. トラブルシューティング

### 9.1 マイグレーションエラー
```bash
# データベースをリセット
rm db.sqlite3
rm -rf budget_app/migrations/

# 再マイグレーション
python manage.py makemigrations budget_app
python manage.py migrate
python manage.py createsuperuser
```

### 9.2 テンプレートが見つからない
- ディレクトリ構造を確認: `budget_app/templates/budget_app/`
- settings.pyの`INSTALLED_APPS`に`budget_app`が含まれているか確認

### 9.3 静的ファイルが読み込まれない
```bash
# 開発環境では通常不要だが、必要に応じて
python manage.py collectstatic
```

---

## 10. 今後の開発予定

### 短期（次回セッション）
1. シミュレーション計算ロジックの実装
2. 結果表示ページの作成
3. グラフ表示機能の追加

### 中期
1. CSV入出力機能
2. レスポンシブデザインの改善
3. エラーハンドリングの強化

### 長期
1. Zaim API連携
2. マルチユーザー対応
3. クラウドへのデプロイ（Heroku / Railway）
4. AI による支出予測機能

---

## 11. コマンドリファレンス

### よく使うコマンド
```bash
# サーバー起動
python manage.py runserver

# マイグレーション
python manage.py makemigrations
python manage.py migrate

# 管理者ユーザー作成
python manage.py createsuperuser

# Pythonシェル起動
python manage.py shell

# テスト実行
python manage.py test budget_app

# データベースのバックアップ
python manage.py dumpdata > backup.json

# データベースのリストア
python manage.py loaddata backup.json
```

---

## 12. 学習リソース

- Django公式チュートリアル: https://docs.djangoproject.com/ja/4.2/intro/tutorial01/
- Tailwind CSS: https://tailwindcss.com/docs
- Chart.js: https://www.chartjs.org/docs/latest/
- Python dateutil: https://dateutil.readthedocs.io/

---

以上で実装計画ドキュメントは完了です。
次回のセッションでは、フェーズ2のステップ2.5まで完了させることを目標とします。
