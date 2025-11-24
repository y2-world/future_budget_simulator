from django import forms
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum
from django.utils import timezone
from .models import (
    SimulationConfig,
    MonthlyPlan,
    TransactionEvent,
    CreditEstimate,
    DefaultChargeOverride,
    CreditDefault,
)
from .forms import (
    SimulationConfigForm,
    MonthlyPlanForm,
    CreditEstimateForm,
    CreditDefaultForm,
)

DEFAULT_CREDIT_CHARGES = [
     {
         'key': 'amazon_prime',
         'label': 'Amazon Prime',
         'card_type': 'view',
         'amount': 600,
         'due_day': 4,
     },
     {
         'key': 'apple_music',
         'label': 'Apple Music',
         'card_type': 'view',
         'amount': 1980,
         'due_day': 4,
     },
     {
         'key': 'heroku',
         'label': 'Heroku',
         'card_type': 'view',
         'amount': 798,
         'due_day': 4,
     },
     {
         'key': 'moneytree',
         'label': 'Moneytree',
         'card_type': 'view',
         'amount': 360,
         'due_day': 4,
     },
     {
         'key': 'ntt',
         'label': 'NTT',
         'card_type': 'view',
         'amount': 5170,
         'due_day': 4,
     },
     {
         'key': 'water',
         'label': '水道（奇数月）',
         'card_type': 'view',
         'amount': 3806,
         'due_day': 4,  # 支払日をVIEWカードに合わせる
         'odd_month_only': True,
     },
 ]

DEFAULT_CHARGE_MAP = {item['key']: item for item in DEFAULT_CREDIT_CHARGES}


def format_year_month_display(year_month: str) -> str:
    if not year_month:
        return ''
    try:
        year_str, month_str = year_month.split('-', 1)
        year = int(year_str)
        month = int(month_str)
    except (ValueError, TypeError):
        return year_month
    return f'{year}年{month}月'


def get_next_bonus_month(year_month: str) -> str:
    """指定された年月から請求月を返す
    - 12月〜6月の購入 -> 8月請求
    - 7月〜11月の購入 -> 翌年1月請求
    """
    try:
        year, month = map(int, year_month.split('-'))
    except (ValueError, AttributeError):
        return year_month

    # 12月〜6月の購入 -> 同年8月請求
    if month == 12 or 1 <= month <= 6:
        # 12月の場合は翌年8月
        if month == 12:
            return f"{year + 1}-08"
        else:
            return f"{year}-08"
    # 7月〜11月の購入 -> 翌年1月請求
    else:
        return f"{year + 1}-01"


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
    from datetime import date

    config = SimulationConfig.objects.filter(is_active=True).first()

    if request.method == 'POST':
        form = SimulationConfigForm(request.POST, instance=config)
        if form.is_valid():
            # 既存の設定を更新、または新規作成
            new_config = form.save(commit=False)
            new_config.is_active = True
            # 開始日とシミュレーション期間のデフォルト値を設定（新規作成時のみ）
            if not new_config.pk:
                new_config.start_date = date.today()
                new_config.simulation_months = 12
            new_config.save()
            messages.success(request, 'シミュレーション設定を保存しました。')
            return redirect('budget_app:config')
    else:
        form = SimulationConfigForm(instance=config)

    return render(request, 'budget_app/config.html', {'form': form})


def update_initial_balance(request):
    """初期残高を更新"""
    if request.method == 'POST':
        initial_balance = request.POST.get('initial_balance', 0)
        try:
            initial_balance = int(initial_balance)
            # 有効な設定を取得または作成
            config = SimulationConfig.objects.filter(is_active=True).first()
            if config:
                config.initial_balance = initial_balance
                config.save()
                messages.success(request, f'初期残高を{initial_balance:,}円に更新しました。')
            else:
                messages.error(request, 'シミュレーション設定が見つかりません。')
        except ValueError:
            messages.error(request, '無効な金額です。')

    return redirect('budget_app:plan_list')


def adjust_to_previous_business_day(target_date):
    """給与日用: 土日祝なら前の営業日（金曜日）に調整"""
    import jpholiday
    from datetime import timedelta

    while target_date.weekday() >= 5 or jpholiday.is_holiday(target_date):
        target_date -= timedelta(days=1)
    return target_date


def adjust_to_next_business_day(target_date):
    """支払日用: 土日祝なら次の営業日に調整"""
    import jpholiday
    from datetime import timedelta

    while target_date.weekday() >= 5 or jpholiday.is_holiday(target_date):
        target_date += timedelta(days=1)
    return target_date


def plan_list(request):
    """月次計画一覧"""
    from datetime import date
    import calendar

    # 現在の年月を取得
    today = date.today()
    current_year_month = f"{today.year}-{today.month:02d}"

    # 月次計画を取得し、現在/未来と過去に分ける
    all_plans = list(MonthlyPlan.objects.all().order_by('year_month'))
    current_and_future_plans = [p for p in all_plans if p.year_month >= current_year_month]
    past_plans = [p for p in all_plans if p.year_month < current_year_month]

    # 過去のプランは新しい順にソート
    past_plans.sort(key=lambda p: p.year_month, reverse=True)

    # 現在/未来 + 過去の順で結合
    plans = current_and_future_plans + past_plans

    # 初期残高と定期預金情報を取得
    config = SimulationConfig.objects.filter(is_active=True).first()
    initial_balance = config.initial_balance if config else 0
    savings_enabled = config.savings_enabled if config else False
    savings_amount = config.savings_amount if (config and savings_enabled) else 0
    savings_start_month = config.savings_start_month if (config and savings_enabled) else None

    current_balance = initial_balance
    cumulative_savings = 0  # 定期預金の累計

    # 各計画に収支情報とタイムラインを追加
    for plan in plans:
        plan.total_income = plan.get_total_income()
        plan.total_expenses = plan.get_total_expenses()
        plan.net_income = plan.get_net_income()

        # 定期預金が有効で開始されているか判定
        plan.has_savings = savings_enabled and savings_start_month and plan.year_month >= savings_start_month
        if plan.has_savings:
            cumulative_savings += savings_amount
        plan.savings_amount_display = cumulative_savings if plan.has_savings else 0

        year, month = map(int, plan.year_month.split('-'))
        last_day = calendar.monthrange(year, month)[1]

        timeline = []
        plan.start_balance = current_balance
        view_card_balance = None  # VIEWカード引き落とし後の残高を記録

        def clamp_day(day: int) -> int:
            return min(max(day, 1), last_day)

        # 給与日（土日祝なら前の営業日）
        salary_date = adjust_to_previous_business_day(date(year, month, clamp_day(25)))
        bonus_date = adjust_to_previous_business_day(date(year, month, clamp_day(25)))
        food_date = adjust_to_previous_business_day(date(year, month, clamp_day(25)))

        # 支払日（土日祝なら次の営業日）
        rent_date = adjust_to_next_business_day(date(year, month, clamp_day(27)))
        lake_date = adjust_to_next_business_day(date(year, month, clamp_day(27)))
        view_card_date = adjust_to_next_business_day(date(year, month, clamp_day(4)))
        rakuten_card_date = adjust_to_next_business_day(date(year, month, clamp_day(27)))
        paypay_card_date = adjust_to_next_business_day(date(year, month, clamp_day(27)))
        vermillion_card_date = adjust_to_next_business_day(date(year, month, clamp_day(4)))
        amazon_card_date = adjust_to_next_business_day(date(year, month, clamp_day(26)))
        loan_date = adjust_to_next_business_day(date(year, month, clamp_day(last_day)))
        loan_borrowing_date = adjust_to_next_business_day(date(year, month, clamp_day(1)))

        transactions = [
            {'date': salary_date, 'name': '給与', 'amount': plan.salary, 'is_view_card': False},
            {'date': bonus_date, 'name': 'ボーナス', 'amount': plan.bonus, 'is_view_card': False},
            {'date': food_date, 'name': '食費', 'amount': -plan.food, 'is_view_card': False},
            {'date': rent_date, 'name': '家賃', 'amount': -plan.rent, 'is_view_card': False},
            {'date': lake_date, 'name': 'レイク返済', 'amount': -plan.lake, 'is_view_card': False},
            {'date': view_card_date, 'name': 'VIEWカード', 'amount': -plan.view_card, 'is_view_card': True},
            {'date': view_card_date, 'name': 'ボーナス払い', 'amount': -plan.view_card_bonus, 'is_view_card': True},
            {'date': rakuten_card_date, 'name': '楽天カード', 'amount': -plan.rakuten_card, 'is_view_card': False},
            {'date': paypay_card_date, 'name': 'PayPayカード', 'amount': -plan.paypay_card, 'is_view_card': False},
            {'date': vermillion_card_date, 'name': 'VERMILLION CARD', 'amount': -plan.vermillion_card, 'is_view_card': False},
            {'date': amazon_card_date, 'name': 'Amazonカード', 'amount': -plan.amazon_card, 'is_view_card': False},
            {'date': loan_date, 'name': 'マネーアシスト返済', 'amount': -plan.loan, 'is_view_card': False},
            {'date': loan_borrowing_date, 'name': 'マネーアシスト借入', 'amount': plan.loan_borrowing, 'is_view_card': False},
        ]

        # 「その他」は金額が0でない場合のみ追加（日付なし）
        if plan.other != 0:
            transactions.append({
                'date': None,
                'name': 'その他',
                'amount': -plan.other,
                'is_view_card': False,
            })

        # 日付順にソート（日付がNoneの場合は最後、同日の場合は収入を先に）
        transactions.sort(key=lambda x: (x['date'] if x['date'] is not None else date.max, -x['amount']))

        for transaction in transactions:
            if transaction['amount'] == 0:
                continue
            current_balance += transaction['amount']
            timeline.append({
                'date': transaction['date'],
                'name': transaction['name'],
                'amount': transaction['amount'],
                'balance': current_balance,
                'is_income': transaction['amount'] > 0
            })
            # VIEWカード（通常払いまたはボーナス払い）の引き落とし後の残高を記録
            if transaction.get('is_view_card', False):
                view_card_balance = current_balance

        plan.timeline = timeline
        plan.final_balance = current_balance
        # メイン預金残高を計算（VIEWカード引き落とし後の残高 - 定期預金残高）
        # VIEWカードの引き落としがない場合は月末残高を使用
        base_balance = view_card_balance if view_card_balance is not None else current_balance
        plan.main_balance = base_balance - cumulative_savings if plan.has_savings else base_balance
        # アーカイブフラグを設定
        plan.is_archived = plan.year_month < current_year_month

    return render(request, 'budget_app/plan_list.html', {
        'plans': plans,
        'current_and_future_plans': current_and_future_plans,
        'past_plans': past_plans,
        'initial_balance': initial_balance,
    })


def plan_create(request):
    """月次計画作成"""
    from django.http import JsonResponse
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = MonthlyPlanForm(request.POST)
        if form.is_valid():
            plan = form.save()
            if is_ajax:
                return JsonResponse({'status': 'success', 'message': '月次計画を作成しました。'})
            messages.success(request, '月次計画を作成しました。')
            return redirect('budget_app:plan_list')
        elif is_ajax:
            return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)

    else:
        # 設定からデフォルト給与と食費を取得
        config = SimulationConfig.objects.filter(is_active=True).first()
        default_salary = config.default_salary if config else 271919
        default_food = config.default_food if config else 50000
        default_view_card = config.default_view_card if config else 0

        # デフォルト値を設定
        initial_data = {
            'salary': default_salary,
            'food': default_food,
            'view_card': default_view_card,
            'lake': 8000,
            'rent': 74396,
        }
        form = MonthlyPlanForm(initial=initial_data)

    return render(request, 'budget_app/plan_form.html', {
        'form': form,
        'title': '月次計画の作成'
    })


def plan_edit(request, pk):
    """月次計画編集"""
    plan = get_object_or_404(MonthlyPlan, pk=pk)
    from django.http import JsonResponse
    import logging
    logger = logging.getLogger(__name__)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = MonthlyPlanForm(request.POST, instance=plan)
        if form.is_valid():
            plan = form.save()
            display_month = format_year_month_display(plan.year_month)
            if is_ajax:
                return JsonResponse({'status': 'success', 'message': f'{display_month} の計画を更新しました。'})
            messages.success(request, f'{display_month} の計画を更新しました。')
            return redirect('budget_app:plan_list')
        else:
            # フォームエラーをログに出力
            logger.error(f"Plan edit form validation failed. Errors: {form.errors}")
            logger.error(f"POST data: {request.POST}")
            if is_ajax:
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
            messages.error(request, '更新に失敗しました。入力内容を確認してください。')

    else:
        form = MonthlyPlanForm(instance=plan)

    return render(request, 'budget_app/plan_form.html', {
        'form': form,
        'title': f'{format_year_month_display(plan.year_month)} の編集'
    })


def plan_delete(request, pk):
    """月次計画削除"""
    plan = get_object_or_404(MonthlyPlan, pk=pk)
    from django.http import JsonResponse
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        year_month = plan.year_month
        plan.delete()
        if is_ajax:
            return JsonResponse({'status': 'success', 'message': f'{format_year_month_display(year_month)} の計画を削除しました。'})
        messages.success(request, f'{format_year_month_display(year_month)} の計画を削除しました。')

    if is_ajax:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)
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


def credit_estimate_list(request):
    """クレカ請求見積り一覧＆追加"""
    from datetime import datetime, timedelta
    from collections import OrderedDict
    from django.http import JsonResponse

    # 事前に上書きデータを取得して辞書に格納
    overrides = DefaultChargeOverride.objects.all()
    override_map = {(ov.default_id, ov.year_month): ov.amount for ov in overrides}
    estimates = list(CreditEstimate.objects.all().order_by('year_month', 'card_type', 'due_date', 'created_at'))
    credit_defaults = list(CreditDefault.objects.filter(is_active=True))

    # サマリー（年月 -> カード -> {total, entries}）
    card_labels = dict(CreditEstimate.CARD_TYPES)

    # カードタイプと支払日のマッピング
    card_due_days = {
        'view': 4,
        'rakuten': 27,
        'paypay': 27,
        'vermillion': 4,
        'amazon': 26,
    }

    # カード名に支払日を追加する関数
    def get_card_label_with_due_day(card_type, is_bonus=False):
        base_label = card_labels.get(card_type, card_type)
        due_day = card_due_days.get(card_type, '')
        if due_day:
            label = f'{base_label} ({due_day}日)'
        else:
            label = base_label

        if is_bonus:
            label = f'ボーナス払い {label}'

        return label

    summary = OrderedDict()

    # シミュレーション設定からVIEWカードのデフォルト値を取得
    config = SimulationConfig.objects.filter(is_active=True).first()

    # 全ての年月を取得
    all_months = set(est.year_month for est in estimates)

    # 当月と次月を追加（データがなくても表示）
    today = datetime.now()
    current_month = today.strftime('%Y-%m')
    next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1).strftime('%Y-%m')
    all_months.add(current_month)
    all_months.add(next_month)

    for est in estimates:
        month_group = summary.setdefault(est.year_month, OrderedDict())

        if est.is_bonus_payment:
            card_key = f'{est.card_type}_bonus'
            card_label = get_card_label_with_due_day(est.card_type, is_bonus=True)
        else:
            card_key = est.card_type
            card_label = get_card_label_with_due_day(est.card_type, is_bonus=False)

        card_group = month_group.setdefault(card_key, { # card_keyが 'view_bonus' のようになる
            'label': card_label, # 'VIEWカード' または 'VIEWカード（ボーナス払い）'
            'total': 0,
            'entries': [],
            'year_month': est.year_month,  # 元の年月を保持
            'is_bonus_section': est.is_bonus_payment,  # ボーナス払いセクションかどうか
        })
        card_group['total'] += est.amount
        # 通常のCreditEstimateオブジェクトにis_defaultフラグを追加
        est.is_default = False
        card_group['entries'].append(est)

    # 各年月の各カードに定期デフォルトを追加
    for year_month in all_months:
        month_group = summary.setdefault(year_month, OrderedDict())

        # 年月から月を取得（奇数月判定用）
        year, month = map(int, year_month.split('-'))
        is_odd_month = (month % 2 == 1)

        # 定期デフォルトを該当カードのエントリーとして追加
        for default in credit_defaults:
            # 奇数月のみ適用フラグが立っている場合、偶数月はスキップ
            if default.apply_odd_months_only and not is_odd_month:
                continue

            # 該当カードのグループを取得または作成
            card_group = month_group.setdefault(default.card_type, {
                'label': get_card_label_with_due_day(default.card_type, is_bonus=False),
                'total': 0,
                'entries': [],
                # 反映機能で year_month が参照されるため追加
                'year_month': year_month,
                'is_bonus_section': False,
            })

            # 疑似的なCreditEstimateオブジェクトを作成
            class DefaultEntry:
                def __init__(self, default_obj, year_month):
                    self.pk = None  # 削除・編集不可を示すためにNone
                    # 上書きされた金額があればそれを使用
                    overridden_amount = override_map.get((default_obj.id, year_month), None)
                    self.year_month = year_month
                    self.card_type = default_obj.card_type
                    self.description = default_obj.label
                    self.amount = overridden_amount if overridden_amount is not None else default_obj.amount
                    self.is_overridden = overridden_amount is not None # 上書きされているかどうかのフラグ
                    self.due_date = None
                    self.is_split_payment = False
                    self.is_bonus_payment = False
                    self.is_default = True  # デフォルトエントリーであることを示すフラグ
                    self.default_id = default_obj.id  # デフォルト項目のID

            default_entry = DefaultEntry(default, year_month)
            # 金額が0の場合は追加しない（削除された定期項目）
            if default_entry.amount > 0:
                card_group['entries'].append(default_entry)
                card_group['total'] += default_entry.amount

    # 各カードのエントリーを支払日順にソート（定期デフォルトは最後）
    for year_month, month_group in summary.items():
        for card_type, card_data in month_group.items():
            card_data['entries'].sort(key=lambda x: (
                x.is_default if hasattr(x, 'is_default') else False,  # 定期デフォルトを最後に
                x.due_date if x.due_date else datetime.max.date(),  # due_dateがNoneの場合は最後に
                # 定期デフォルト項目の場合はdefault_idでソート、通常項目はpkでソート
                x.default_id if (hasattr(x, 'is_default') and x.is_default and hasattr(x, 'default_id')) else (x.pk if hasattr(x, 'pk') and x.pk else float('inf'))
            ))

    # カードタイプの表示順序（定義順）
    card_order = {
        'view': 0,
        'rakuten': 1,
        'paypay': 2,
        'vermillion': 3,
        'amazon': 4,
        'view_bonus': 5,  # VIEWボーナス払い
        'rakuten_bonus': 6,
        'paypay_bonus': 7,
        'vermillion_bonus': 8,
        'amazon_bonus': 9,
    }

    # 各月のカードをカードタイプ順にソート
    for year_month, month_group in summary.items():
        sorted_cards = OrderedDict(sorted(
            month_group.items(),
            key=lambda item: card_order.get(item[0], 99)  # カードタイプ順でソート
        ))
        summary[year_month] = sorted_cards

    # summaryを現在、未来、過去に分割
    current_month_str = datetime.now().strftime('%Y-%m')
    current_month_summary = OrderedDict()
    future_summary = OrderedDict()
    past_summary = OrderedDict()

    for ym, cards in summary.items():
        # ymが '2024-08_bonus' のような形式の場合、年月部分を取得
        ym_date_part = ym.split('_')[0]

        if ym_date_part == current_month_str:
            current_month_summary[ym] = cards
        elif ym_date_part > current_month_str:
            future_summary[ym] = cards
        else:
            past_summary[ym] = cards

    # 過去の見積もりは年月が新しい順に表示
    past_summary = OrderedDict(sorted(past_summary.items(), key=lambda item: item[0].split('_')[0], reverse=True))

    # 未来の見積もりは年月が古い順に表示
    future_summary = OrderedDict(sorted(future_summary.items(), key=lambda item: item[0].split('_')[0]))

    # 今月の見積もりもソート（通常→ボーナスの順）
    current_month_summary = OrderedDict(sorted(current_month_summary.items(), key=lambda item: item[0].split('_')[0]))

    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        action = request.POST.get('action')

        # --- POSTアクションによる分岐 ---

        if action == 'edit_default':
            default_id = request.POST.get('id')
            year_month = request.POST.get('year_month')
            amount_str = request.POST.get('amount')

            try:
                amount = int(amount_str)
                default_instance = get_object_or_404(CreditDefault, pk=default_id)

                # 上書きオブジェクトを取得または作成
                override, created = DefaultChargeOverride.objects.update_or_create(
                    default=default_instance,
                    year_month=year_month,
                    defaults={'amount': amount}
                )
                
                return JsonResponse({
                    'status': 'success',
                    'message': f'{format_year_month_display(year_month)}の「{default_instance.label}」を更新しました。'
                })
            except (ValueError, TypeError):
                return JsonResponse({'status': 'error', 'message': '無効な金額が入力されました。'}, status=400)
            return redirect('budget_app:credit_estimates')

        elif action == 'delete_override':
            default_id = request.POST.get('default_id')
            year_month = request.POST.get('year_month')

            try:
                override_instance = get_object_or_404(DefaultChargeOverride, default_id=default_id, year_month=year_month)
                default_label = override_instance.default.label
                override_instance.delete()
                return JsonResponse({
                    'status': 'success',
                    'message': f'{format_year_month_display(year_month)}の「{default_label}」への変更を元に戻しました。'
                })
            except DefaultChargeOverride.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': '削除対象の上書き設定が見つかりません。'}, status=404)

        elif action == 'delete_default_for_month':
            default_id = request.POST.get('default_id')
            year_month = request.POST.get('year_month')

            try:
                default_instance = get_object_or_404(CreditDefault, pk=default_id)
                default_label = default_instance.label

                # 金額を0にする上書きを作成（実質的に非表示）
                DefaultChargeOverride.objects.update_or_create(
                    default=default_instance,
                    year_month=year_month,
                    defaults={'amount': 0}
                )

                return JsonResponse({
                    'status': 'success',
                    'message': f'{format_year_month_display(year_month)}の「{default_label}」を削除しました。'
                })
            except CreditDefault.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': '削除対象の定期項目が見つかりません。'}, status=404)

        elif action == 'edit_default':
            default_id = request.POST.get('id')
            year_month = request.POST.get('year_month')
            new_amount = request.POST.get('amount')

            try:
                default_instance = get_object_or_404(CreditDefault, pk=default_id)
                default_label = default_instance.label

                # この月だけの金額上書きを作成
                DefaultChargeOverride.objects.update_or_create(
                    default=default_instance,
                    year_month=year_month,
                    defaults={'amount': new_amount}
                )

                return JsonResponse({
                    'status': 'success',
                    'message': f'{format_year_month_display(year_month)}の「{default_label}」を{new_amount}円に変更しました。'
                })
            except CreditDefault.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': '編集対象の定期項目が見つかりません。'}, status=404)
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': f'エラーが発生しました: {str(e)}'}, status=500)

        elif action == 'reflect_card':
            year_month = request.POST.get('year_month')
            card_type = request.POST.get('card_type')
            is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

            # card_typeから実際のカード種別とボーナス払いフラグを取得
            is_bonus = card_type.endswith('_bonus')
            if is_bonus:
                actual_card_type = card_type.replace('_bonus', '')
            else:
                actual_card_type = card_type

            # サマリーからカードデータを取得
            if year_month in summary and card_type in summary[year_month]:
                card_data = summary[year_month][card_type]
                total_amount = card_data['total']
                card_label = card_data['label']

                # 反映先の年月を計算
                current_date = datetime.strptime(year_month, '%Y-%m')

                # ボーナス払いの場合は請求月と同じ月に反映
                if is_bonus:
                    target_year_month = year_month
                else:
                    # 通常払いの場合、カード種別に応じて支払い月を計算
                    use_year, use_month = map(int, current_date.strftime('%Y-%m').split('-'))

                    if actual_card_type in ['view', 'vermillion']:
                        # 翌々月払い
                        payment_month = use_month + 2
                        payment_year = use_year
                        if payment_month > 12:
                            payment_month -= 12
                            payment_year += 1
                        target_year_month = f"{payment_year}-{payment_month:02d}"
                    elif actual_card_type in ['rakuten', 'paypay', 'amazon']:
                        # 翌月払い
                        payment_month = use_month + 1
                        payment_year = use_year
                        if payment_month > 12:
                            payment_month -= 12
                            payment_year += 1
                        target_year_month = f"{payment_year}-{payment_month:02d}"
                    else:
                        # その他のカードは翌月払い
                        payment_month = use_month + 1
                        payment_year = use_year
                        if payment_month > 12:
                            payment_month -= 12
                            payment_year += 1
                        target_year_month = f"{payment_year}-{payment_month:02d}"

                # 月次計画を取得または作成
                plan, _ = MonthlyPlan.objects.get_or_create(
                    year_month=target_year_month,
                    defaults={
                        'salary': 0,
                        'bonus': 0,
                        'food': 0,
                        'rent': 0,
                        'lake': 0,
                        'view_card': 0,
                        'view_card_bonus': 0,
                        'rakuten_card': 0,
                        'paypay_card': 0,
                        'vermillion_card': 0,
                        'amazon_card': 0,
                        'loan': 0,
                        'loan_borrowing': 0,
                        'other': 0,
                    }
                )

                # 通常払いまたはボーナス払いを反映
                if is_bonus:
                    field_name = f'{actual_card_type}_card_bonus'
                else:
                    field_name = f'{actual_card_type}_card' if actual_card_type != 'view' else 'view_card'

                if hasattr(plan, field_name):
                    setattr(plan, field_name, total_amount)
                    plan.save()

                    success_message = f'{format_year_month_display(year_month)}の「{card_label}」を{format_year_month_display(target_year_month)}の月次計画に反映しました（{total_amount:,}円）'

                    if is_ajax:
                        return JsonResponse({
                            'status': 'success',
                            'message': success_message
                        })
                    else:
                        messages.success(request, success_message)
                else:
                    error_message = f'フィールド {field_name} が見つかりません。'
                    if is_ajax:
                        return JsonResponse({'status': 'error', 'message': error_message}, status=400)
                    else:
                        messages.error(request, error_message)
            else:
                error_message = 'カードデータが見つかりません。'
                if is_ajax:
                    return JsonResponse({'status': 'error', 'message': error_message}, status=400)
                else:
                    messages.error(request, error_message)

            return redirect('budget_app:credit_estimates')

        elif action == 'reflect':
            year_month = request.POST.get('year_month')
            reflect_type = request.POST.get('reflect_type') # 'normal' or 'bonus'

            # 月全体を反映する場合、通常払いとボーナス払いの両方を処理
            sections_to_process = []
            if reflect_type == 'normal':
                # 通常払いセクションがあれば追加
                if year_month in summary:
                    sections_to_process.append(year_month)
            elif reflect_type == 'bonus':
                # ボーナス払いセクションがあれば追加
                bonus_key = f"{year_month}_bonus"
                if bonus_key in summary:
                    sections_to_process.append(bonus_key)

            if sections_to_process:
                reflected_details = {}  # 反映先年月ごとの詳細を格納

                for section_key in sections_to_process:
                    # VIEW/VERMILLIONは翌々月、その他は翌月に反映
                    for card_key, data in summary[section_key].items():
                        # card_keyがボーナス払いかどうかを判定
                        is_bonus = card_key.endswith('_bonus')
                        if is_bonus:
                            # ボーナス払いの場合、card_typeを取得
                            card_type = card_key.replace('_bonus', '')
                        else:
                            card_type = card_key

                        total_amount = data['total']

                        # 反映先の年月を計算
                        current_date = datetime.strptime(year_month, '%Y-%m')

                        # ボーナス払いの場合は請求月と同じ月に反映
                        if is_bonus:
                            target_year_month = year_month
                        else:
                            # 通常払いの場合
                            # 通常払いの場合、カード種別に応じて支払い月を計算
                            use_year, use_month = map(int, current_date.strftime('%Y-%m').split('-'))
                            
                            if card_type in ['view', 'vermillion']:
                                # 翌々月払い
                                payment_month = use_month + 2
                                payment_year = use_year
                                if payment_month > 12:
                                    payment_month -= 12
                                    payment_year += 1
                                target_year_month = f"{payment_year}-{payment_month:02d}"
                            elif card_type in ['rakuten', 'paypay', 'amazon']:
                                # 翌月払い
                                payment_month = use_month + 1
                                payment_year = use_year
                                if payment_month > 12:
                                    payment_month -= 12
                                    payment_year += 1
                                target_year_month = f"{payment_year}-{payment_month:02d}"                            

                        # 月次計画を取得または作成
                        plan, _ = MonthlyPlan.objects.get_or_create(
                            year_month=target_year_month,
                            defaults={
                                'salary': 0,
                                'bonus': 0,
                                'food': 0,
                                'rent': 0,
                                'lake': 0,
                                'view_card': 0,
                                'view_card_bonus': 0,
                                'rakuten_card': 0,
                                'paypay_card': 0,
                                'vermillion_card': 0,
                                'amazon_card': 0,
                                'loan': 0,
                                'loan_borrowing': 0,
                                'other': 0,
                            }
                        )

                        # 通常払いまたはボーナス払いを反映
                        if is_bonus:
                            field_name = f'{card_type}_card_bonus'
                        else:
                            field_name = f'{card_type}_card' if card_type != 'view' else 'view_card'

                        if hasattr(plan, field_name):
                            setattr(plan, field_name, total_amount)

                        plan.save()

                        # 反映詳細を記録
                        plan_display = format_year_month_display(target_year_month)
                        card_label = data.get('label', card_type)
                        if plan_display not in reflected_details:
                            reflected_details[plan_display] = []
                        reflected_details[plan_display].append(f"{card_label}: {total_amount:,}円")

                # 成功メッセージを生成
                message_parts = [f"{format_year_month_display(year_month)}の見積もりを反映しました。"]
                for plan_month, details in reflected_details.items():
                    message_parts.append(f"【{plan_month}】" + "、".join(details))
                
                messages.success(request, " ".join(message_parts))
                return redirect('budget_app:credit_estimates')
        
        elif action == 'create_estimate':
            form = CreditEstimateForm(request.POST)
            if form.is_valid():
                estimate = form.save(commit=False)

                # ボーナス払いの場合、年月を直近の1月/8月に変更
                if estimate.is_bonus_payment:
                    estimate.year_month = get_next_bonus_month(estimate.year_month)

                instance = form.save() # 分割払い対応のためsaveメソッドを使う
                if is_ajax:
                     return JsonResponse({'status': 'success', 'message': 'クレカ見積りを追加しました。'})
                messages.success(request, 'クレカ見積りを追加しました。')
            else:
                if is_ajax:
                    return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
                messages.error(request, f'エラー: {form.errors.as_text()}')

        # どのactionにも一致しない場合は、単にリダイレクト
        return redirect('budget_app:credit_estimates')

    else:
        # 新規作成時のデフォルト（当月）
        initial_data = {'year': timezone.now().year, 'month': f"{timezone.now().month:02d}"}
        form = CreditEstimateForm(initial=initial_data)

    context = {
        'form': form,
        'card_labels': card_labels,
        'current_month_summary': current_month_summary,
        'future_summary': future_summary,
        'past_summary': past_summary,
        'current_month_str': current_month_str,
        'default_edit_form': CreditDefaultForm(), # モーダル用のフォームを追加
    }
    return render(request, 'budget_app/credit_estimates.html', context)


def credit_estimate_edit(request, pk):
    """クレカ見積り編集（インライン編集対応）"""
    estimate = get_object_or_404(CreditEstimate, pk=pk)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = CreditEstimateForm(request.POST, instance=estimate)
        if form.is_valid():
            estimate = form.save(commit=False)
            if estimate.is_bonus_payment:
                estimate.year_month = get_next_bonus_month(estimate.year_month)
            estimate.save()
            if is_ajax:
                return JsonResponse({'status': 'success', 'message': 'クレカ見積りを更新しました。'})
            messages.success(request, 'クレカ見積りを更新しました。')
            return redirect('budget_app:credit_estimates')
        else:
            if is_ajax:
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
            messages.error(request, '更新に失敗しました。入力内容を確認してください。')
            return redirect('budget_app:credit_estimates')
    
    # GETリクエストやAjaxでないPOSTの場合は、ここでは何も返さず、リダイレクトさせる
    return redirect('budget_app:credit_estimates')


def credit_estimate_delete(request, pk):
    """クレカ見積り削除"""
    from .models import CreditDefault, DefaultChargeOverride
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        delete_type = request.POST.get('delete_type', 'single')
        default_id = request.GET.get('default_id')

        try:
            # 定期項目の削除の場合
            if default_id:
                default_instance = get_object_or_404(CreditDefault, pk=default_id)
                year_month = request.GET.get('year_month')

                if delete_type == 'all':
                    # 関連する上書き設定を全て削除
                    DefaultChargeOverride.objects.filter(default=default_instance).delete()
                    # 定期設定自体を論理削除
                    default_instance.is_active = False
                    default_instance.save()
                    message = f'定期設定「{default_instance.label}」と関連する全ての見積もりを削除しました。'
                else: # 'single' の場合
                    # この月だけ非表示にするため、金額0の上書きを作成
                    DefaultChargeOverride.objects.update_or_create(
                        default=default_instance,
                        year_month=year_month,
                        defaults={'amount': 0}
                    )
                    message = f'{format_year_month_display(year_month)}の「{default_instance.label}」を削除しました。'
            # 通常項目の削除の場合
            else:
                estimate = get_object_or_404(CreditEstimate, pk=pk)
                estimate.delete()
                message = 'クレカ見積りを削除しました。'

            return JsonResponse({'status': 'success', 'message': message})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'削除中にエラーが発生しました: {str(e)}'}, status=500)

    # POST以外のリクエストはリダイレクト

    return redirect('budget_app:credit_estimates')


def credit_default_list(request):
    """定期デフォルト（サブスク・固定費）の編集"""
    defaults = CreditDefault.objects.filter(is_active=True).order_by('id')

    # POST時の処理
    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        action = request.POST.get('action')

        if action == 'create':
            form = CreditDefaultForm(request.POST)
            if form.is_valid():
                instance = form.save()
                if is_ajax:
                    return JsonResponse({
                        'status': 'success',
                        'message': f'定期項目「{instance.label}」を作成しました。',
                        'default': {
                            'id': instance.id,
                            'label': instance.label,
                            'card_type': instance.card_type,
                            'amount': instance.amount,
                        }
                    })
                messages.success(request, f'定期項目「{instance.label}」を作成しました。')
            else:
                if is_ajax:
                    return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
                messages.error(request, f'エラー: {form.errors.as_text()}')

        elif action == 'update':
            target_id = request.POST.get('id')
            instance = get_object_or_404(CreditDefault, pk=target_id)
            form = CreditDefaultForm(request.POST, instance=instance)
            if form.is_valid():
                instance = form.save()
                if is_ajax:
                    return JsonResponse({
                        'status': 'success',
                        'message': f'{instance.label} を更新しました。',
                        'default': {
                            'id': instance.id,
                            'label': instance.label,
                            'card_type': instance.card_type,
                            'card_type_display': instance.get_card_type_display(),
                            'amount': instance.amount,
                        }
                    })
                messages.success(request, f'{instance.label} を更新しました。')
            else:
                if is_ajax:
                    return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
                messages.error(request, f'エラー: {form.errors.as_text()}')
        
        return redirect('budget_app:credit_defaults')

    # GETリクエスト、またはバリデーションエラーがあった場合のフォーム
    form = CreditDefaultForm()
    forms_by_id = {d.id: CreditDefaultForm(instance=d, prefix=str(d.id)) for d in defaults}

    return render(request, 'budget_app/credit_defaults.html', {
        'defaults': defaults,
        'forms_by_id': forms_by_id,
        'form': form,  # 'create_form' から 'form' に変更
    })


def credit_default_delete(request, pk):
    """定期デフォルト削除（論理削除）"""
    default = get_object_or_404(CreditDefault, pk=pk)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        label = default.label
        # 論理削除：is_activeをFalseに設定（既存の見積もりには影響なし）
        default.is_active = False
        default.save()
        if is_ajax:
            return JsonResponse({'status': 'success', 'message': f'{label} を削除しました。'})
        messages.success(request, f'{label} を削除しました。')

    if is_ajax:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)
    return redirect('budget_app:credit_defaults')
