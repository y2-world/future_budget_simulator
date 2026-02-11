from django import forms
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponseRedirect
from django.db import models as django_models
from django.db.models import Sum
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.urls import reverse
from .models import (
    SimulationConfig,
    MonthlyPlan,
    TransactionEvent,
    CreditEstimate,
    DefaultChargeOverride,
    CreditDefault,
    MonthlyPlanDefault,
)
from .forms import (
    SimulationConfigForm,
    MonthlyPlanForm,
    CreditEstimateForm,
    CreditDefaultForm,
    MonthlyPlanDefaultForm,
    get_next_bonus_month,
)
import logging

logger = logging.getLogger(__name__)


def get_monthly_plan_defaults():
    """
    月次計画のデフォルト値を取得する
    MonthlyPlanDefaultテーブルから有効なデフォルト項目を取得し、
    keyをキーとした辞書を返す
    """
    defaults = {}
    default_items = get_active_defaults_ordered()

    for item in default_items:
        if item.key:
            defaults[item.key] = item.amount

    return defaults


def get_withdrawal_day(field_name):
    """
    指定されたkeyの引落日をMonthlyPlanDefaultから取得
    返り値: (day: int|None, is_end_of_month: bool)
    """
    default_item = MonthlyPlanDefault.objects.filter(
        key=field_name,
        is_active=True
    ).first()

    if default_item:
        return (default_item.withdrawal_day, default_item.is_withdrawal_end_of_month)

    return (None, False)


def get_day_for_field(field_name, year, month):
    """
    指定されたフィールド名の引落日/支払日を取得
    月末の場合はその月の最終日を返す
    """
    from calendar import monthrange

    day, is_end_of_month = get_withdrawal_day(field_name)

    if is_end_of_month:
        return monthrange(year, month)[1]  # その月の最終日

    return day if day else 1  # デフォルトは1日


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



def config_view(request):
    """設定"""
    from datetime import date
    from .forms import MonthlyPlanDefaultForm

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
            messages.success(request, '設定を保存しました。')
            return redirect('budget_app:config')
        else:
            # バリデーションエラーをログに出力


            logger.error(f"Form validation errors: {form.errors}")
            logger.error(f"POST data: {request.POST}")
            messages.error(request, 'エラーが発生しました。入力内容を確認してください。')
    else:
        form = SimulationConfigForm(instance=config)

    # 月次計画デフォルト項目のデータを取得（論理削除されていないもののみ）
    defaults = get_active_defaults_ordered()
    defaults_with_amount = [d for d in defaults if d.amount]
    defaults_without_amount = [d for d in defaults if not d.amount]
    default_form = MonthlyPlanDefaultForm()

    context = {
        'form': form,
        'defaults': defaults,
        'defaults_with_amount': defaults_with_amount,
        'defaults_without_amount': defaults_without_amount,
        'default_form': default_form,
    }

    return render(request, 'budget_app/config.html', context)


def update_initial_balance(request):
    """現在残高を更新"""
    if request.method == 'POST':
        initial_balance = request.POST.get('initial_balance', 0)
        try:
            initial_balance = int(initial_balance)
            # 有効な設定を取得または作成
            config = SimulationConfig.objects.filter(is_active=True).first()
            if config:
                config.initial_balance = initial_balance
                config.save()
                messages.success(request, f'現在残高を{initial_balance:,}円に更新しました。')
            else:
                messages.error(request, '設定が見つかりません。')
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


def get_card_plan(card_type):
    """
    カード種別からMonthlyPlanDefaultを取得

    Args:
        card_type: カード種別のkey

    Returns:
        MonthlyPlanDefault: カード情報、存在しない場合はNone
    """
    return MonthlyPlanDefault.objects.filter(key=card_type, is_active=True).first()


def calculate_closing_date(year_month, card_type):
    """
    締め日を計算

    Args:
        year_month: 利用月（YYYY-MM形式）
        card_type: カード種別のkey

    Returns:
        date: 締め日、計算できない場合はNone
    """
    from datetime import date
    import calendar

    try:
        year, month = map(int, year_month.split('-'))
    except (ValueError, AttributeError):
        return None

    card_plan = get_card_plan(card_type)

    if card_plan:
        if card_plan.is_end_of_month:
            # 月末締めの場合：year_month = 利用月 → 締め日 = year_month の月末
            last_day = calendar.monthrange(year, month)[1]
            return date(year, month, last_day)
        elif card_plan.closing_day:
            # 指定日締めの場合：year_month = 締め日の前月 → 締め日 = (year_month+1) の closing_day日
            closing_month = month + 1
            closing_year = year
            if closing_month > 12:
                closing_month = 1
                closing_year += 1
            return date(closing_year, closing_month, card_plan.closing_day)

    # デフォルト: 月末締め
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def calculate_billing_month(year_month, card_type, split_part=None):
    """
    利用月から引き落とし月を計算

    Args:
        year_month: 利用月（YYYY-MM形式）
        card_type: カード種別のkey
        split_part: 分割払いの回数（1 or 2）、Noneの場合は通常払い

    Returns:
        str: 引き落とし月（YYYY-MM形式）
    """
    try:
        year, month = map(int, year_month.split('-'))
    except (ValueError, AttributeError):
        return year_month

    card_plan = get_card_plan(card_type)

    if card_plan:
        if card_plan.is_end_of_month:
            # 月末締め: billing_month = year_month + 1
            billing_month = month + 1
            billing_year = year
        else:
            # 指定日締め: billing_month = year_month + 2
            billing_month = month + 2
            billing_year = year
    else:
        # デフォルト値（情報がない場合は翌月）
        billing_month = month + 1
        billing_year = year

    # 分割2回目の場合はさらに+1ヶ月
    if split_part == 2:
        billing_month += 1

    # 月の繰り上がり処理
    while billing_month > 12:
        billing_month -= 12
        billing_year += 1

    return f"{billing_year}-{billing_month:02d}"


def is_odd_month(year_month):
    """
    奇数月かどうかを判定

    Args:
        year_month: 年月（YYYY-MM形式）

    Returns:
        bool: 奇数月の場合True
    """
    try:
        month = int(year_month.split('-')[1])
        return month % 2 == 1
    except (ValueError, IndexError, AttributeError):
        return False


def get_active_defaults_ordered():
    """
    有効な月次計画デフォルト項目を順序付きで取得

    Returns:
        QuerySet: 有効なMonthlyPlanDefaultをorder順でソートしたQuerySet
    """
    return MonthlyPlanDefault.objects.filter(is_active=True).order_by('order', 'id')


def get_active_card_defaults():
    """
    有効なカード項目（card_idが設定されている）を取得

    Returns:
        QuerySet: カード項目のMonthlyPlanDefault
    """
    return MonthlyPlanDefault.objects.filter(is_active=True, card_id__isnull=False)


def get_card_choices_for_form():
    """
    フォーム用のカード選択肢を取得（key, titleのみ）

    Returns:
        QuerySet: カード選択肢用のMonthlyPlanDefault（card_idがあり、ボーナス払いを除外）
    """
    return MonthlyPlanDefault.objects.filter(
        is_active=True,
        card_id__isnull=False
    ).exclude(card_id='').exclude(is_bonus_payment=True).order_by('order', 'id').values('key', 'title')


def get_card_by_key(card_key):
    """
    keyからMonthlyPlanDefaultを取得（is_activeフィルターなし）

    Args:
        card_key: カードのkey

    Returns:
        MonthlyPlanDefault: カード情報、存在しない場合はNone
    """
    return MonthlyPlanDefault.objects.filter(key=card_key).first()


def get_cards_by_closing_day(closing_day):
    """
    指定された締め日のカードを取得

    Args:
        closing_day: 締め日（1-31）

    Returns:
        QuerySet: 指定された締め日のMonthlyPlanDefault
    """
    return MonthlyPlanDefault.objects.filter(is_active=True, closing_day=closing_day)




def plan_list(request):
    """月次計画一覧"""
    from datetime import date
    import calendar

    # 現在の年月を取得
    today = date.today()
    current_year_month = f"{today.year}-{today.month:02d}"

    # 月次計画を取得（現在月以降のみ表示）
    all_plans = list(MonthlyPlan.objects.all().order_by('year_month'))
    # 現在月以降のプランのみ表示
    current_and_future_plans = [
        p for p in all_plans
        if p.year_month >= current_year_month
    ]
    past_plans = []  # 過去月は非表示

    # 表示対象のプラン
    plans = current_and_future_plans

    # 現在残高と定期預金情報を取得
    config = SimulationConfig.objects.filter(is_active=True).first()
    initial_balance = config.initial_balance if config else 0
    savings_enabled = config.savings_enabled if config else False
    savings_amount = config.savings_amount if (config and savings_enabled) else 0
    savings_start_month = config.savings_start_month if (config and savings_enabled) else None
    savings_day = config.savings_day if (config and savings_enabled) else None

    current_balance = initial_balance
    cumulative_savings = 0  # 定期預金の累計

    # 各計画に収支情報とタイムラインを追加
    # 現在月かどうかを判定するフラグ
    reached_current_month = False

    for plan in plans:
        plan.total_income = plan.get_total_income()
        plan.total_expenses = plan.get_total_expenses()
        plan.net_income = plan.get_net_income()

        # 定期預金が有効で開始されているか判定
        plan.has_savings = savings_enabled and savings_start_month and plan.year_month >= savings_start_month
        # savings_dayあり時は定期預金行を処理した後に累積するので、ここでは前月までの累積を保持
        # savings_dayなし時はここで加算（タイムライン行なし）
        if plan.has_savings and not savings_day:
            cumulative_savings += savings_amount
        plan.savings_amount_display = cumulative_savings if plan.has_savings else 0
        plan.savings_day_display = savings_day if plan.has_savings else None

        year, month = map(int, plan.year_month.split('-'))
        last_day = calendar.monthrange(year, month)[1]

        timeline = []

        # 現在月の場合、現在残高（今日時点の残高）から開始
        if plan.year_month == current_year_month:
            reached_current_month = True
            current_balance = initial_balance

        plan.start_balance = current_balance
        view_card_balance = None  # VIEWカード引き落とし後の残高を記録

        def clamp_day(day: int) -> int:
            return min(max(day, 1), last_day)

        # MonthlyPlanDefaultから動的にトランザクションを生成
        default_items = MonthlyPlanDefault.objects.all().order_by('order', 'id')
        transactions = []

        for item in default_items:
            # この月に表示すべき項目かチェック
            if not item.should_display_for_month(plan.year_month):
                continue

            key = item.key
            if not key:
                continue

            # 金額を取得
            amount = plan.get_item(key)
            if amount == 0:
                continue

            # 引落日 / 振込日を計算
            day = get_day_for_field(key, year, month)
            item_date = date(year, month, clamp_day(day))

            # 休日を考慮して日付を調整
            if item.consider_holidays:
                if item.payment_type == 'deposit':
                    # 振込（給与など）: 休日なら前営業日
                    item_date = adjust_to_previous_business_day(item_date)
                else:
                    if item.title == '食費':
                        # 引き落とし: 休日なら前営業日
                        item_date = adjust_to_previous_business_day(item_date)
                    else:
                        # 引き落とし: 休日なら翌営業日
                        item_date = adjust_to_next_business_day(item_date)

            # 収入か支出かを判定
            is_income = item.payment_type == 'deposit'
            transaction_amount = amount if is_income else -amount

            # 繰上げ返済フラグを取得（クレカ項目のみ）
            is_excluded = plan.get_exclusion(key) if item.is_credit_card() else False

            # VIEWカードかどうかを判定（item_6がVIEWカード）
            is_view_card = (key == 'item_6') and item.is_credit_card()

            # 項目名を表示用に設定
            display_name = item.title

            transactions.append({
                'date': item_date,
                'name': display_name,
                'amount': transaction_amount,
                'is_view_card': is_view_card,
                'is_excluded': is_excluded
            })

        # 臨時項目をトランザクションに追加
        temporary_items = plan.get_temporary_items()
        for temp_item in temporary_items:
            temp_day = temp_item.get('date', 1)
            temp_amount = temp_item.get('amount', 0)
            if temp_amount == 0:
                continue

            temp_date = date(year, month, clamp_day(temp_day))
            transactions.append({
                'date': temp_date,
                'name': f"⚡ {temp_item.get('name', '臨時項目')}",
                'amount': temp_amount,  # 既に正負が設定されている
                'is_view_card': False,
                'is_excluded': False,
                'is_temporary': True
            })

        # 定期預金トランザクションを追加（savings_dayが設定されている場合のみ）
        if plan.has_savings and savings_amount > 0 and savings_day:
            savings_date = date(year, month, clamp_day(savings_day))
            transactions.append({
                'date': savings_date,
                'name': '🏦 定期預金',
                'amount': -savings_amount,
                'is_view_card': False,
                'is_excluded': False,
                'is_savings': True
            })

        # 日付順にソート（日付がNoneの場合は最後、同日の場合は定期預金を最後に、収入を先に）
        transactions.sort(key=lambda x: (x['date'] if x['date'] is not None else date.max, 1 if x.get('is_savings') else 0, -x['amount']))

        # 過去の明細用のリスト（現在月の今日以前の取引）
        past_timeline = []

        # 現在月の場合、過去の明細を別途計算
        if reached_current_month and plan.year_month == current_year_month:
            past_balance = initial_balance
            for transaction in transactions:
                if transaction['amount'] == 0:
                    continue
                if transaction['date'] and transaction['date'] <= today:
                    # 過去の明細として記録（残高は元の累積計算のまま）
                    # 実際の残高計算は不要なので、ダミー値を入れる
                    past_timeline.append({
                        'date': transaction['date'],
                        'name': transaction['name'],
                        'amount': transaction['amount'],
                        'balance': 0,  # テンプレートで表示しないのでダミー
                        'is_income': transaction['amount'] > 0,
                        'is_excluded': transaction.get('is_excluded', False)
                    })

        # タイムライン作成（未来の取引のみ、または過去月の全取引）
        for transaction in transactions:
            if transaction['amount'] == 0:
                continue
            # 現在月で今日以前の取引はスキップ
            if reached_current_month and plan.year_month == current_year_month:
                if transaction['date'] and transaction['date'] <= today:
                    continue

            # 繰上げ返済・定期預金は残高計算から除外（定期預金は cumulative_savings で別途管理）
            if not transaction.get('is_excluded', False) and not transaction.get('is_savings', False):
                current_balance += transaction['amount']

            # 定期預金行の場合、この行を処理した後にcumulative_savingsを加算
            if transaction.get('is_savings', False):
                cumulative_savings += savings_amount

            # メイン残高 = 残高 - 定期預金累積（定期預金が開始していれば常に引く）
            main_balance_for_row = current_balance - cumulative_savings if plan.has_savings else current_balance

            total_balance_for_row = main_balance_for_row + cumulative_savings if plan.has_savings else None

            timeline.append({
                'date': transaction['date'],
                'name': transaction['name'],
                'amount': transaction['amount'],
                'balance': main_balance_for_row,
                'is_income': transaction['amount'] > 0,
                'is_excluded': transaction.get('is_excluded', False),
                'is_savings': transaction.get('is_savings', False),
                'savings_cumulative': cumulative_savings if plan.has_savings else None,
                'total_balance': total_balance_for_row,
            })
            # VIEWカード（通常払いまたはボーナス払い）の引き落とし後の残高を記録
            if transaction.get('is_view_card', False):
                view_card_balance = current_balance

        plan.timeline = timeline
        plan.past_timeline = past_timeline  # 過去の明細を保存
        # 月末残高もメイン残高（定期分を引いた後）で表示
        plan.final_balance = current_balance - cumulative_savings if plan.has_savings else current_balance
        # アーカイブフラグを設定
        plan.is_archived = plan.year_month < current_year_month

        # 現在月の場合、現在残高を表示
        if plan.year_month == current_year_month:
            plan.current_balance = initial_balance  # 現在残高（今日時点）
        else:
            plan.current_balance = None

    # 今日以降の明細がある月のみ表示（現在月の場合）
    filtered_plans = []
    archived_current_month_plans = []  # 今日以降の明細がない現在月のプラン
    for plan in plans:
        if plan.year_month == current_year_month:
            # 現在月の場合、今日以降の明細があるかチェック（金額が0でないもののみ）
            future_items = [item for item in plan.timeline if item.get('date') and item['date'] >= today and item.get('amount', 0) != 0]
            has_future_items = len(future_items) > 0

            if has_future_items:
                filtered_plans.append(plan)
            else:
                # 今日以降の明細がない現在月は過去の明細として扱う
                archived_current_month_plans.append(plan)
        else:
            # 未来月は全て表示
            filtered_plans.append(plan)

    plans = filtered_plans
    past_plans = archived_current_month_plans  # 過去の明細に追加

    # MonthlyPlanDefaultのデータを取得
    default_items = get_active_defaults_ordered()

    # 登録済みの年月リストを取得（モーダルで除外するため）
    import json
    registered_year_months = list(
        MonthlyPlan.objects.values_list('year_month', flat=True)
    )

    # デフォルト項目の情報をJSON形式で渡す（モーダルのフォーム生成用）
    default_items_data = [
        {
            'key': item.key,
            'title': item.title,
            'amount': item.amount,
            'payment_type': item.payment_type,
            'is_credit_card': item.is_credit_card(),
            'is_bonus_payment': item.is_bonus_payment,
        }
        for item in default_items
    ]

    # 各プランのデータをJSON形式で渡す（編集モーダル用）
    plans_data = {}
    for plan in plans:
        plans_data[plan.pk] = {
            'year_month': plan.year_month,
            'gross_salary': plan.gross_salary or 0,
            'deductions': plan.deductions or 0,
            'transportation': plan.transportation or 0,
            'bonus_gross_salary': plan.bonus_gross_salary or 0,
            'bonus_deductions': plan.bonus_deductions or 0,
            'items': plan.items or {},
            'exclusions': plan.exclusions or {},
            'temporary_items': plan.temporary_items or [],
        }

    return render(request, 'budget_app/plan_list.html', {
        'plans': plans,
        'current_and_future_plans': current_and_future_plans,
        'past_plans': past_plans,
        'initial_balance': initial_balance,
        'today': today,
        'default_items': default_items,
        'registered_year_months': json.dumps(registered_year_months),
        'default_items_json': json.dumps(default_items_data),
        'plans_data_json': json.dumps(plans_data),
    })


def plan_create(request):
    """月次計画作成"""
    from django.http import JsonResponse
    from datetime import datetime, timedelta

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    is_past_mode = False

    if request.method == 'POST':
        # 先月以前かどうかを判定
        year = request.POST.get('year')
        month = request.POST.get('month')
        current_year_month = datetime.now().strftime('%Y-%m')
        is_past_month = False

        if year and month:
            selected_year_month = f"{year}-{month}"
            is_past_month = selected_year_month < current_year_month

        # 既存のプランがあるかチェック
        existing_plan = None
        if year and month:
            year_month_str = f"{year}-{month}"
            existing_plan = MonthlyPlan.objects.filter(year_month=year_month_str).first()

        # デバッグ: POSTデータを確認



        # 過去月の場合はPastSalaryFormを使用
        if is_past_month:
            from .forms import PastSalaryForm
            form = PastSalaryForm(request.POST, instance=existing_plan)
        else:
            form = MonthlyPlanForm(request.POST, instance=existing_plan)

        if form.is_valid():
            plan = form.save()

            # 成功メッセージを年月付きで作成
            year_month_display = format_year_month_display(plan.year_month)
            if is_past_month:
                success_message = f'{year_month_display}の給与情報を登録しました。'
            else:
                success_message = f'{year_month_display}の月次計画を登録しました。'

            if is_ajax:
                response_data = {
                    'status': 'success',
                    'message': success_message,
                }
                # 作成した月にリダイレクト（過去月以外）
                if not is_past_month:
                    target_url = reverse('budget_app:index') + f'#plan-{plan.year_month}'
                    response_data['target_url'] = target_url
                return JsonResponse(response_data)
            messages.success(request, success_message)
            # 過去月の場合は給与一覧にリダイレクト
            if is_past_month:
                return redirect('budget_app:salary_list')
            # 通常は作成した月にリダイレクト
            return redirect(reverse('budget_app:index') + f'#plan-{plan.year_month}')
        else:
            if is_ajax:
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
            # 非AJAXの場合、エラーのあるformをそのまま使ってレンダリング
            # is_past_mode を設定してからrenderへ
            is_past_mode = is_past_month

    if request.method == 'GET':
        # GETリクエストの場合のみ新しいフォームを作成
        # URLパラメータで過去月モードかどうかを判定
        is_past_mode = request.GET.get('past_mode') == 'true'

        if is_past_mode:
            from .forms import PastSalaryForm
            form = PastSalaryForm()
        else:
            # デフォルト値を取得
            plan_defaults = get_monthly_plan_defaults()

            # 現在の年月を取得
            now = datetime.now()
            current_year = now.year
            current_month = f"{now.month:02d}"

            # URLパラメータで年月が指定されている場合はそれを使用
            param_year = request.GET.get('year')
            param_month = request.GET.get('month')
            if param_year:
                current_year = int(param_year)
            if param_month:
                current_month = f"{int(param_month):02d}"

            # 既存の同じ年月のプランがあれば、その値を初期値として使用
            year_month_str = f"{current_year}-{current_month}"
            existing_plan = MonthlyPlan.objects.filter(year_month=year_month_str).first()

            if existing_plan:
                # 既存のプランがある場合、その値を初期値として使用
                initial_data = {
                    'year': current_year,
                    'month': current_month,
                }
                # 給与明細フィールド
                for field in ['gross_salary', 'deductions', 'transportation', 'bonus_gross_salary', 'bonus_deductions']:
                    initial_data[field] = existing_plan.get_item(field)

                # MonthlyPlanDefaultから動的フィールドを追加
                default_items = get_active_defaults_ordered()
                for item in default_items:
                    if item.key:
                        initial_data[item.key] = existing_plan.get_item(item.key)
            else:
                # 既存のプランがない場合
                from datetime import date
                today = date.today()
                selected_month_int = int(current_month)

                # 選択された年月が過去かどうか判定
                is_past_month = (current_year < today.year) or (current_year == today.year and selected_month_int < today.month)

                if is_past_month:
                    # 過去の月の場合はすべて0を設定
                    initial_data = {
                        'year': current_year,
                        'month': current_month,
                    }
                else:
                    # 未来の月の場合はデフォルト値を設定
                    initial_data = {
                        'year': current_year,
                        'month': current_month,
                    }
                    # MonthlyPlanDefaultからデフォルト値を追加
                    initial_data.update(plan_defaults)
            form = MonthlyPlanForm(initial=initial_data)

    # デフォルト項目の情報をJavaScript用にJSON形式で渡す
    import json

    default_items = get_active_defaults_ordered()
    default_items_data = [
        {
            'key': item.key,
            'title': item.title,
            'withdrawal_day': item.withdrawal_day,
            'is_withdrawal_end_of_month': item.is_withdrawal_end_of_month,
            'is_credit_card': item.is_credit_card()
        }
        for item in default_items
    ]

    # 登録済みの年月リストを取得（新規作成時のドロップダウンから除外するため）
    registered_months = list(
        MonthlyPlan.objects.values_list('year_month', flat=True)
    )

    return render(request, 'budget_app/plan_form.html', {
        'form': form,
        'title': '月次計画の作成' if not is_past_mode else '過去の給与データ登録',
        'is_past_mode': is_past_mode,
        'default_items_json': json.dumps(default_items_data),
        'registered_months_json': json.dumps(registered_months)
    })


def get_plan_by_month(request):
    """年月に基づいて既存の月次計画データを取得するAPI"""
    from django.http import JsonResponse

    year = request.GET.get('year')
    month = request.GET.get('month')

    if not year or not month:
        return JsonResponse({'error': 'Year and month are required'}, status=400)

    try:
        year_month_str = f"{year}-{int(month):02d}"
        plan = MonthlyPlan.objects.filter(year_month=year_month_str).first()

        if plan:
            # 既存のプランがある場合、データを返す
            # 固定フィールドと動的itemsフィールドを統合
            data = {
                'exists': True,
                'gross_salary': plan.gross_salary or 0,
                'transportation': plan.transportation or 0,
                'deductions': plan.deductions or 0,
                'bonus_gross_salary': plan.bonus_gross_salary or 0,
                'bonus_deductions': plan.bonus_deductions or 0,
            }
            # itemsフィールドから全ての項目を追加
            for key, value in plan.items.items():
                data[key] = value or 0
            return JsonResponse(data)
        else:
            # 既存のプランがない場合
            from datetime import date
            today = date.today()
            selected_year = int(year)
            selected_month = int(month)

            # 選択された年月が過去かどうか判定
            is_past_month = (selected_year < today.year) or (selected_year == today.year and selected_month < today.month)

            # 固定フィールド
            data = {
                'exists': False,
                'gross_salary': 0,
                'transportation': 0,
                'deductions': 0,
                'bonus_gross_salary': 0,
                'bonus_deductions': 0,
            }

            if not is_past_month:
                # 未来の月の場合はデフォルト値を返す
                default_items = get_active_defaults_ordered()
                for item in default_items:
                    data[item.key] = item.amount or 0
            else:
                # 過去の月の場合は全て0
                default_items = get_active_defaults_ordered()
                for item in default_items:
                    data[item.key] = 0

            return JsonResponse(data)
    except Exception as e:


        logger.error(f'Error in get_plan_by_month: {e}', exc_info=True)
        return JsonResponse({'error': 'データ取得中にエラーが発生しました。'}, status=500)


def plan_data(request, pk):
    """月次計画データをJSON形式で返す（モーダル用）"""
    from django.http import JsonResponse
    plan = get_object_or_404(MonthlyPlan, pk=pk)

    # MonthlyPlanDefaultから収入・支出項目を取得
    default_items = get_active_defaults_ordered()

    income_items = []
    expense_items = []

    for item in default_items:
        if not item.key:
            continue

        # この月に表示すべき項目かチェック
        if not item.should_display_for_month(plan.year_month):
            continue

        value = plan.get_item(item.key) or 0

        item_data = {
            'key': item.key,
            'label': item.title,
            'value': value
        }

        # payment_typeで収入・支出を分類
        if item.payment_type == 'deposit':
            income_items.append(item_data)
        else:
            expense_items.append(item_data)

    data = {
        'income_items': income_items,
        'expense_items': expense_items
    }

    return JsonResponse(data)


def plan_edit(request, pk):
    """月次計画編集"""
    plan = get_object_or_404(MonthlyPlan, pk=pk)
    from django.http import JsonResponse
    from datetime import datetime, timedelta


    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    # 過去月かどうかを判定
    current_year_month = datetime.now().strftime('%Y-%m')
    is_past_month = plan.year_month < current_year_month

    if request.method == 'POST':
        # デバッグ: POSTデータを確認
        logger.info(f"POST data: bonus_gross_salary={request.POST.get('bonus_gross_salary')}, bonus_deductions={request.POST.get('bonus_deductions')}")

        # チェックボックスの文字列値をbooleanに変換
        post_data = request.POST.copy()
        # MonthlyPlanDefaultからクレカ項目の除外フラグを動的に生成
        checkbox_fields = []
        default_items = get_active_defaults_ordered()
        for item in default_items:
            if item.key and item.is_credit_card():
                checkbox_fields.append(f'exclude_{item.key}')
        for field in checkbox_fields:
            if field in post_data:
                # "true"の場合はチェックボックスとしてそのまま（Trueになる）
                # "false"の場合は削除（Falseになる）
                if post_data[field] == 'false':
                    post_data.pop(field)

        # デバッグ: チェックボックスの値を確認
        logger.info(f"Checkbox values after processing: {[(f, post_data.get(f)) for f in checkbox_fields if f in post_data]}")

        # POSTデータに含まれるフィールドで給与のみの編集かを判定
        # 給与関連フィールドのみの場合はPastSalaryFormを使用
        salary_only_fields = {
            'csrfmiddlewaretoken', 'year', 'month', 'year_month',
            'salary', 'bonus', 'gross_salary', 'deductions', 'transportation',
            'bonus_gross_salary', 'bonus_deductions'
        }
        post_keys = set(request.POST.keys())
        is_salary_only = post_keys.issubset(salary_only_fields)

        # リファラーをチェック（補助的な判定）
        referer = request.META.get('HTTP_REFERER', '')
        is_from_salary_list = 'salaries' in referer
        logger.info(f"POST keys: {post_keys}")
        logger.info(f"is_salary_only: {is_salary_only}, Referer: {referer}")

        # AJAX編集の場合は常にMonthlyPlanFormを使用（画面内編集）
        # 給与一覧からの編集の場合はPastSalaryFormを使用
        # その他は全てMonthlyPlanFormを使用（動的フィールド対応）
        if is_ajax:
            form = MonthlyPlanForm(post_data, instance=plan)
            logger.info("Using MonthlyPlanForm (AJAX)")
        elif is_salary_only:
            from .forms import PastSalaryForm
            form = PastSalaryForm(post_data, instance=plan)
            logger.info("Using PastSalaryForm (salary only)")
        else:
            form = MonthlyPlanForm(post_data, instance=plan)
            logger.info("Using MonthlyPlanForm (default)")
        if form.is_valid():
            plan = form.save()

            # 臨時項目を処理
            temporary_items = []
            for key in request.POST:
                if key.startswith('temp_name_'):
                    index = key.replace('temp_name_', '')
                    name = request.POST.get(f'temp_name_{index}', '')
                    amount_str = request.POST.get(f'temp_amount_{index}', '0')
                    date_str = request.POST.get(f'temp_date_{index}', '1')
                    item_type = request.POST.get(f'temp_type_{index}', 'expense')

                    if name.strip():  # 名前が空でない場合のみ追加
                        try:
                            amount = int(amount_str) if amount_str else 0
                            # 支出の場合はマイナスに変換
                            if item_type == 'expense' and amount > 0:
                                amount = -amount
                            date = int(date_str) if date_str else 1
                            date = max(1, min(31, date))  # 1-31の範囲に制限
                            temporary_items.append({
                                'name': name,
                                'amount': amount,
                                'date': date,
                                'type': item_type
                            })
                        except ValueError:
                            pass

            # 日付順にソート
            temporary_items.sort(key=lambda x: x['date'])
            plan.temporary_items = temporary_items
            plan.save()

            display_month = format_year_month_display(plan.year_month)
            if is_ajax:
                response_data = {
                    'status': 'success',
                    'message': f'{display_month} の計画を更新しました。',
                }
                # リファラーをチェックして適切なページを判定
                referer = request.META.get('HTTP_REFERER', '')
                if 'past-transactions' in referer:
                    # 過去の明細ページから編集した場合
                    target_url = reverse('budget_app:past_transactions') + f'#plan-content-{plan.year_month}'
                    response_data['target_url'] = target_url
                elif not is_past_month:
                    # 通常の月次計画ページで過去月以外
                    target_url = reverse('budget_app:index') + f'#plan-{plan.year_month}'
                    response_data['target_url'] = target_url
                return JsonResponse(response_data)
            messages.success(request, f'{display_month} の計画を更新しました。')
            # リファラーをチェックして適切なページにリダイレクト
            referer = request.META.get('HTTP_REFERER', '')
            if 'past-transactions' in referer:
                return redirect('budget_app:past_transactions')
            elif 'salaries' in referer:
                return redirect('budget_app:salary_list')
            elif is_past_month:
                return redirect('budget_app:salary_list')
            # 通常は更新した月にリダイレクト
            return redirect(reverse('budget_app:index') + f'#plan-{plan.year_month}')
        else:
            # フォームエラーをログに出力
            logger.error(f"Plan edit form validation failed. Errors: {form.errors}")
            logger.error(f"POST data: {request.POST}")
            if is_ajax:
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
            # 非AJAXの場合、エラーのあるformをそのまま使ってレンダリング
            # （formは既にエラー情報を持っている）

    if request.method == 'GET':
        # GETリクエストの場合のみ新しいフォームを作成
        # リファラーをチェックして給与一覧からのアクセスかを判定
        referer = request.META.get('HTTP_REFERER', '')
        is_from_salary_list = 'salaries' in referer

        # 給与一覧からの編集の場合はPastSalaryFormを使用
        # その他は全てMonthlyPlanFormを使用（動的フィールド対応）
        if is_from_salary_list:
            from .forms import PastSalaryForm
            form = PastSalaryForm(instance=plan)
        else:
            form = MonthlyPlanForm(instance=plan)

    # デフォルト項目の情報をJavaScript用にJSON形式で渡す
    import json

    default_items = get_active_defaults_ordered()
    default_items_data = [
        {
            'key': item.key,
            'title': item.title,
            'withdrawal_day': item.withdrawal_day,
            'is_withdrawal_end_of_month': item.is_withdrawal_end_of_month,
            'is_credit_card': item.is_credit_card()
        }
        for item in default_items
    ]

    # 登録済みの年月リストを取得（新規作成時のドロップダウンから除外するため）
    registered_months = list(
        MonthlyPlan.objects.values_list('year_month', flat=True)
    )

    return render(request, 'budget_app/plan_form.html', {
        'form': form,
        'title': f'{format_year_month_display(plan.year_month)} の編集',
        'is_past_mode': is_past_month,
        'default_items_json': json.dumps(default_items_data),
        'registered_months_json': json.dumps(registered_months)
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

    # 事前に上書きデータを取得して辞書に格納（金額、カード種別、2回払い、利用日、USD情報）
    # N+1クエリを防ぐため select_related で default を取得
    overrides = DefaultChargeOverride.objects.select_related('default').all()
    override_map = {(ov.default_id, ov.year_month): {'amount': ov.amount, 'card_type': ov.card_type, 'is_split_payment': ov.is_split_payment, 'purchase_date_override': ov.purchase_date_override, 'is_usd': ov.is_usd, 'usd_amount': ov.usd_amount} for ov in overrides}
    estimates = list(CreditEstimate.objects.all().order_by('-year_month', 'card_type', 'due_date', 'created_at'))
    credit_defaults = list(CreditDefault.objects.filter(is_active=True).order_by('payment_day', 'id'))

    # サマリー（年月 -> カード -> {total, entries}）
    # card_id -> タイトル、支払日、締め日情報 のマッピングを MonthlyPlanDefault から取得
    card_labels = {}
    card_due_days = {}
    card_info = {}  # is_end_of_month, closing_day を保存

    for item in get_active_card_defaults():
        if item.card_id:
            card_labels[item.card_id] = item.title
            # keyでも引けるようにする（card_typeにはkeyが格納されるため）
            card_labels[item.key] = item.title
            if item.withdrawal_day:
                card_due_days[item.card_id] = item.withdrawal_day
                card_due_days[item.key] = item.withdrawal_day
            # 締め日情報を記録
            card_info[item.card_id] = {
                'is_end_of_month': item.is_end_of_month,
                'closing_day': item.closing_day
            }
            card_info[item.key] = card_info[item.card_id]

    # カード名に支払日を追加する関数
    def get_card_label_with_due_day(card_type, is_bonus=False, year_month=None):
        from datetime import date
        import calendar

        base_label = card_labels.get(card_type, card_type)
        due_day = card_due_days.get(card_type, '')

        if due_day and year_month:
            # year_monthは既にbilling_month（支払月）として渡される
            payment_year, payment_month = map(int, year_month.split('-'))

            # 支払月の最終日を取得
            last_day = calendar.monthrange(payment_year, payment_month)[1]
            # 支払日が月の日数を超える場合は最終日に調整
            actual_due_day = min(due_day, last_day)

            # 営業日に調整（土日祝なら翌営業日）
            payment_date = adjust_to_next_business_day(date(payment_year, payment_month, actual_due_day))

            label = f'{base_label} ({payment_date.month}/{payment_date.day}支払)'
        elif due_day:
            label = f'{base_label} ({due_day}日)'
        else:
            label = base_label

        if is_bonus:
            label = f'{base_label}【ボーナス払い】'

        return label

    summary = OrderedDict()

    # 設定からVIEWカードのデフォルト値を取得
    config = SimulationConfig.objects.filter(is_active=True).first()

    today = timezone.now()

    for est in estimates:
        # 通常払いの場合、締め日が過ぎたら非表示
        if not est.is_bonus_payment:
            year, month = map(int, est.year_month.split('-'))
            from datetime import date
            import calendar

            # 分割払いの2回目も1回目と同じyear_monthを使用
            # （締め日チェックも同じロジック、billing_monthだけが異なる）

            # MonthlyPlanDefaultから締め日を取得
            card_default = get_card_plan(est.card_type)
            if card_default:
                if card_default.is_end_of_month:
                    # 月末締めの場合：year_month = 利用月 → 締め日 = year_month の月末
                    last_day = calendar.monthrange(year, month)[1]
                    closing_date = date(year, month, last_day)
                elif card_default.closing_day:
                    # 指定日締めの場合：year_month = 締め日の前月 → 締め日 = (year_month+1) の closing_day日
                    closing_month = month + 1
                    closing_year = year
                    if closing_month > 12:
                        closing_month = 1
                        closing_year += 1
                    closing_date = date(closing_year, closing_month, card_default.closing_day)
                else:
                    # デフォルト: 月末締め
                    last_day = calendar.monthrange(year, month)[1]
                    closing_date = date(year, month, last_day)
            else:
                # デフォルト: 月末締め
                last_day = calendar.monthrange(year, month)[1]
                closing_date = date(year, month, last_day)

            # 締め日の翌日以降は非表示
            if today.date() > closing_date:
                continue
        # ボーナス払いは支払日が過ぎたら非表示
        elif est.is_bonus_payment and est.due_date:
            if today.date() >= est.due_date:
                continue

        # ボーナス払いも通常払いも引き落とし月でグルーピング
        if est.is_bonus_payment and est.due_date:
            display_month = est.due_date.strftime('%Y-%m')  # ボーナス払いも支払月で同じセクションに
        else:
            # billing_monthがある場合はそれを使用、なければyear_monthを使用（下位互換性）
            display_month = est.billing_month if est.billing_month else est.year_month

        month_group = summary.setdefault(display_month, OrderedDict())

        # カードキーとラベルを設定
        # ボーナス払いの場合はcard_typeに_bonusサフィックスを付ける
        card_key = f"{est.card_type}_bonus" if est.is_bonus_payment else est.card_type
        due_day = card_due_days.get(est.card_type, '')

        if est.is_bonus_payment:
            # ボーナス払いの場合、カード名 + 支払日 + 【ボーナス払い】を表示
            if due_day and est.due_date:
                billing_year = est.due_date.year
                billing_month = est.due_date.month
                label = card_labels.get(est.card_type, est.card_type)
                card_label = f"{label} ({billing_month}/{due_day}支払)【ボーナス払い】"
            else:
                label = card_labels.get(est.card_type, est.card_type)
                card_label = label + '【ボーナス払い】'
        else:
            # 通常払いの場合、カード名 + 支払日を表示
            if due_day and display_month:
                billing_year, billing_month = map(int, display_month.split('-'))
                label = card_labels.get(est.card_type, est.card_type)
                card_label = f"{label} ({billing_month}/{due_day}支払)"
            else:
                card_label = card_labels.get(est.card_type, est.card_type)

        card_group = month_group.setdefault(card_key, {
            'label': card_label,
            'total': 0,
            'manual_total': 0,  # 手動入力の合計
            'default_total': 0,  # 定期項目の合計
            'entries': [],
            'year_month': display_month,  # 表示月（支払月＝billing_month）
            'is_bonus_section': est.is_bonus_payment,  # ボーナス払いかどうか
        })
        card_group['total'] += est.amount
        card_group['manual_total'] += est.amount  # 手動入力として加算
        # 通常のCreditEstimateオブジェクトにis_defaultフラグを追加
        est.is_default = False
        card_group['entries'].append(est)

    # 既存の引き落とし月を収集（定期デフォルトはこれらの月にのみ追加）
    # ただし、通常払いがある月のみを対象とする（ボーナス払いのみの月は除外）
    existing_billing_months = set()
    for billing_month, month_group in summary.items():
        # この月に通常払い（ボーナス払いでない）のカードがあるかチェック
        has_normal_payment = any(
            not card_data.get('is_bonus_section', False)
            for card_data in month_group.values()
        )
        if has_normal_payment:
            existing_billing_months.add(billing_month)

    # 現在の年月を取得
    current_year_month = f"{today.year}-{today.month:02d}"

    # 過去の全ての月を自動的に追加（定期デフォルト表示のため）
    # MonthlyPlanから過去の年月をすべて取得
    # MonthlyPlanのyear_monthは既に引き落とし月（計画月）を表している
    past_plans = MonthlyPlan.objects.filter(year_month__lt=current_year_month).values_list('year_month', flat=True)
    for past_month_str in past_plans:
        # past_month_strは既に引き落とし月なので、そのまま追加
        existing_billing_months.add(past_month_str)

    # 定期デフォルトを追加する利用月を決定
    # 既存の引き落とし月から逆算して、対応する利用月を計算
    # {(usage_month, card_id): billing_month} の辞書として保存
    candidate_usage_cards = {}

    from dateutil.relativedelta import relativedelta

    for billing_month in existing_billing_months:
        billing_year, billing_month_num = map(int, billing_month.split('-'))

        # billing_monthからyear_monthを逆算
        for card_id, info in card_info.items():
            if info['is_end_of_month']:
                # 月末締め: billing_month = year_month + 1 → year_month = billing_month - 1
                usage_month_num = billing_month_num - 1
            else:
                # 指定日締め: billing_month = year_month + 2 → year_month = billing_month - 2
                usage_month_num = billing_month_num - 2

            usage_year = billing_year
            if usage_month_num < 1:
                usage_month_num += 12
                usage_year -= 1
            usage_month = f"{usage_year}-{usage_month_num:02d}"
            # 過去3ヶ月以降を追加（定期デフォルト表示のため）
            three_months_ago = (today - relativedelta(months=3)).strftime('%Y-%m')
            if usage_month >= three_months_ago:
                candidate_usage_cards[(usage_month, card_id)] = billing_month

    # 利用月のリストを取得してソート（重複削除）
    candidate_usage_months = sorted(list(set(key[0] for key in candidate_usage_cards.keys())))

    # 各年月の各カードに定期デフォルトを追加
    for year_month in candidate_usage_months:
        # 年月から月を取得（奇数月判定用）
        year, month = map(int, year_month.split('-'))
        is_odd_month_flag = is_odd_month(year_month)

        # 定期項目も締め日チェックを行う（通常払いと同じロジック）
        # VIEW/VERMILLIONカードの締め日（翌月5日）をチェック
        from datetime import date
        import calendar

        # VIEW/VERMILLIONカード用の締め日
        view_closing_month = month + 1
        view_closing_year = year
        if view_closing_month > 12:
            view_closing_month = 1
            view_closing_year += 1
        view_closing_date = date(view_closing_year, view_closing_month, 5)

        # その他のカード用の締め日（月末）
        last_day = calendar.monthrange(year, month)[1]
        other_closing_date = date(year, month, last_day)

        # VIEW/VERMILLIONの締め日が過ぎているかチェック
        view_closed = today.date() > view_closing_date
        # その他のカードの締め日が過ぎているかチェック
        other_closed = today.date() > other_closing_date

        # 定期デフォルトを該当カードのエントリーとして追加
        for default in credit_defaults:
            # 奇数月のみ適用フラグが立っている場合、偶数月はスキップ
            if default.apply_odd_months_only and not is_odd_month_flag:
                continue

            # 上書きデータを確認
            override_data = override_map.get((default.id, year_month))

            # 上書きデータが存在しない場合、自動作成する（初回表示時にスナップショットを取る）
            if not override_data:
                # DefaultChargeOverrideを作成して、現在のデフォルト値をコピー
                new_override = DefaultChargeOverride.objects.create(
                    default=default,
                    year_month=year_month,
                    amount=default.amount,
                    card_type=default.card_type,
                    is_split_payment=False,  # 初回はデフォルトで分割払いなし
                    is_usd=default.is_usd if hasattr(default, 'is_usd') else False,
                    usd_amount=default.usd_amount if hasattr(default, 'usd_amount') else None
                )
                # override_mapとoverride_dataを更新
                override_data = {
                    'amount': new_override.amount,
                    'card_type': new_override.card_type,
                    'is_split_payment': new_override.is_split_payment,
                    'purchase_date_override': new_override.purchase_date_override,
                    'is_usd': new_override.is_usd,
                    'usd_amount': new_override.usd_amount
                }
                override_map[(default.id, year_month)] = override_data

            # 実際に使用するカード種別を決定（上書きがあればそれを使用）
            actual_card_type = override_data.get('card_type') if override_data and override_data.get('card_type') else default.card_type

            # このカード×利用月の組み合わせが候補に含まれているかチェック
            if (year_month, actual_card_type) not in candidate_usage_cards:
                continue

            # 分割払いかどうかを確認
            is_split = override_data.get('is_split_payment', False) if override_data else False

            # 引き落とし月を計算（締め日情報から）
            from datetime import datetime
            usage_date = datetime.strptime(year_month, '%Y-%m')

            # カード情報を取得
            info = card_info.get(actual_card_type, {'is_end_of_month': False})

            if info['is_end_of_month']:
                # 月末締め: 利用月 → 利用月末締め → 翌月払い
                # 例: 1月利用 → 1/31締め → 2月払い
                billing_month_num = usage_date.month + 1
            else:
                # 指定日締め: 利用月 → 翌月締め → 翌々月払い
                # 例: 1月利用 → 2/5締め → 3月払い（VIEWカードは3/4払い）
                billing_month_num = usage_date.month + 2

            billing_year = usage_date.year
            while billing_month_num > 12:
                billing_month_num -= 12
                billing_year += 1
            billing_month = f"{billing_year}-{billing_month_num:02d}"

            # この引き落とし月に既存の見積もりがない場合はスキップ
            if billing_month not in existing_billing_months:
                continue

            # 引き落とし月でグループ化
            month_group = summary.setdefault(billing_month, OrderedDict())

            # 該当カードのグループを取得または作成（実際のカード種別を使用）
            # カード名 + 支払日のラベル作成（get_card_label_with_due_day関数を使用）
            default_label = get_card_label_with_due_day(actual_card_type, is_bonus=False, year_month=year_month)

            card_group = month_group.setdefault(actual_card_type, {
                'label': default_label,
                'total': 0,
                'manual_total': 0,  # 手動入力の合計
                'default_total': 0,  # 定期項目の合計
                'entries': [],
                # 反映機能で billing_month が参照される
                'year_month': billing_month,
                'is_bonus_section': False,
            })

            # 疑似的なCreditEstimateオブジェクトを作成
            class DefaultEntry:
                def __init__(self, default_obj, entry_year_month, override_data, actual_card_type, split_part=None, total_amount=None, original_year_month=None, card_plan_info=None):
                    self.pk = None  # 削除・編集不可を示すためにNone
                    # 上書きされた金額とカード種別があればそれを使用
                    self.year_month = entry_year_month
                    self.card_type = actual_card_type
                    # 元の年月を保持（編集時に使用）
                    self.original_year_month = original_year_month if original_year_month else entry_year_month
                    # 定期項目で分割の場合、説明に「(月分)」を追加
                    if split_part and original_year_month:
                        # 元の年月を「MM月分」形式で追加
                        original_month = int(original_year_month.split('-')[1])
                        self.description = f"{default_obj.label} ({original_month}月分)"
                    else:
                        self.description = default_obj.label
                    # 2回払いの場合は金額を分割
                    if split_part and total_amount is not None:
                        # 2回目の金額を10の位まで0にする（100で切り捨て）
                        second_payment = (total_amount // 2) // 100 * 100
                        if split_part == 2:
                            self.amount = second_payment
                        else:
                            # 1回目: 残り
                            self.amount = total_amount - second_payment
                        # 元の合計金額を保持（編集時に使用）
                        self.original_amount = total_amount
                    else:
                        self.amount = override_data.get('amount') if override_data else default_obj.amount
                        # 元の金額も同じ
                        self.original_amount = self.amount

                    # USD情報を追加
                    if override_data:
                        self.is_usd = override_data.get('is_usd', False)
                        self.usd_amount = override_data.get('usd_amount')
                    else:
                        self.is_usd = default_obj.is_usd if hasattr(default_obj, 'is_usd') else False
                        self.usd_amount = default_obj.usd_amount if hasattr(default_obj, 'usd_amount') else None

                    self.is_overridden = override_data is not None # 上書きされているかどうかのフラグ
                    # due_dateを計算（請求年月 + payment_day）
                    # entry_year_month は請求月（billing_month）なので、その月のpayment_day日をdue_dateとする
                    try:
                        year, month = map(int, entry_year_month.split('-'))
                        # payment_dayが月の最終日を超える場合は、その月の最終日にする
                        max_day = calendar.monthrange(year, month)[1]
                        actual_day = min(default_obj.payment_day, max_day)
                        self.due_date = date(year, month, actual_day)
                    except (ValueError, AttributeError):
                        self.due_date = None
                    # 上書きデータにis_split_paymentがあればそれを使用、なければFalse
                    self.is_split_payment = override_data.get('is_split_payment', False) if override_data else False
                    self.split_payment_part = split_part  # 1 or 2
                    self.is_bonus_payment = False
                    self.is_default = True  # デフォルトエントリーであることを示すフラグ
                    self.default_id = default_obj.id  # デフォルト項目のID
                    self.payment_day = default_obj.payment_day  # 毎月の利用日
                    # purchase_dateを計算（上書きがあればそれを使用）
                    if override_data and override_data.get('purchase_date_override'):
                        self.purchase_date = override_data.get('purchase_date_override')
                    else:
                        # original_year_monthは「利用月」を表す（分割2回目でも同じ）
                        try:
                            usage_ym = original_year_month if original_year_month else self.year_month
                            year, month = map(int, usage_ym.split('-'))

                            if card_plan_info and not card_plan_info.get('is_end_of_month') and card_plan_info.get('closing_day'):
                                # 指定日締めの場合：payment_dayと締め日を比較
                                closing_day = card_plan_info['closing_day']
                                payment_day = default_obj.payment_day

                                if payment_day > closing_day:
                                    # payment_dayが締め日より大きい：year_monthの月のpayment_day日
                                    max_day = calendar.monthrange(year, month)[1]
                                    actual_day = min(payment_day, max_day)
                                    self.purchase_date = date(year, month, actual_day)
                                else:
                                    # payment_dayが締め日以下：year_month+1の月のpayment_day日
                                    closing_month = month + 1
                                    closing_year = year
                                    if closing_month > 12:
                                        closing_month = 1
                                        closing_year += 1
                                    max_day = calendar.monthrange(closing_year, closing_month)[1]
                                    actual_day = min(payment_day, max_day)
                                    self.purchase_date = date(closing_year, closing_month, actual_day)
                            else:
                                # 月末締めの場合：year_monthのpayment_day日
                                max_day = calendar.monthrange(year, month)[1]
                                actual_day = min(default_obj.payment_day, max_day)
                                self.purchase_date = date(year, month, actual_day)
                        except (ValueError, AttributeError):
                            self.purchase_date = None

            # 2回払いの場合は2つのエントリを作成
            is_split = override_data.get('is_split_payment', False) if override_data else False
            if is_split:
                total_amount = override_data.get('amount') if override_data else default.amount

                # 1回目の締め日チェック（過去月の場合はスキップ）
                # 1回目の利用月year_monthの締め日が過ぎていなければ表示
                first_payment_closed = False
                current_year_month_str = f"{today.year}-{today.month:02d}"

                # カード情報を取得（2回目の締め日計算でも使用）
                card_plan = get_card_plan(actual_card_type)

                # billing_monthが過去月または現在月の場合のみ締め日チェック
                if billing_month >= current_year_month_str:
                    if card_plan and card_plan.closing_day and not card_plan.is_end_of_month:
                        # 指定日締めの場合：year_monthの締め日を計算
                        split_year, split_month = map(int, year_month.split('-'))
                        split_closing_month = split_month + 1
                        split_closing_year = split_year
                        if split_closing_month > 12:
                            split_closing_month = 1
                            split_closing_year += 1
                        split_closing_date = date(split_closing_year, split_closing_month, card_plan.closing_day)
                        first_payment_closed = today.date() > split_closing_date
                    else:
                        # 月末締めの場合：year_monthの月末を締め日とする
                        split_year, split_month = map(int, year_month.split('-'))
                        split_last_day = calendar.monthrange(split_year, split_month)[1]
                        split_closing_date = date(split_year, split_month, split_last_day)
                        first_payment_closed = today.date() > split_closing_date

                # 1回目（利用月のbilling_monthに表示）
                if not first_payment_closed:
                    plan_info = info if info else {}
                    default_entry_1 = DefaultEntry(default, year_month, override_data, actual_card_type, split_part=1, total_amount=total_amount, original_year_month=year_month, card_plan_info=plan_info)
                    if default_entry_1.amount > 0:
                        card_group['entries'].append(default_entry_1)
                        card_group['total'] += default_entry_1.amount
                        card_group['default_total'] += default_entry_1.amount

                # 2回目の引き落とし月を計算（1回目のbilling_month + 1ヶ月）
                billing_date = datetime.strptime(billing_month, '%Y-%m')
                next_billing_date = (billing_date.replace(day=1) + timedelta(days=32)).replace(day=1)
                next_billing_month = next_billing_date.strftime('%Y-%m')

                # 2回目の締め日チェック
                # 2回目も1回目と同じyear_monthなので、締め日チェックも同じ
                # （引き落とし月だけが異なる）

                # 2回目の表示可否は1回目と同じ締め日チェック結果を使用
                if not first_payment_closed:
                    # 2回目の引き落とし月のカードグループを取得または作成
                    next_month_group = summary.setdefault(next_billing_month, OrderedDict())

                    # 2回目のラベル作成
                    if due_day:
                        next_b_year, next_b_month = map(int, next_billing_month.split('-'))
                        next_label = f"{card_labels.get(actual_card_type, actual_card_type)} ({next_b_month}/{due_day}支払)"
                    else:
                        next_label = card_labels.get(actual_card_type, actual_card_type)

                    next_card_group = next_month_group.setdefault(actual_card_type, {
                        'label': next_label,
                        'total': 0,
                        'manual_total': 0,  # 手動入力の合計
                        'default_total': 0,  # 定期項目の合計
                        'entries': [],
                        'year_month': next_billing_month,
                        'is_bonus_section': False,
                    })

                    # 2回目のエントリ（利用月は1回目と同じyear_month、引き落とし月はnext_billing_month）
                    plan_info = info if info else {}
                    default_entry_2 = DefaultEntry(default, next_billing_month, override_data, actual_card_type, split_part=2, total_amount=total_amount, original_year_month=year_month, card_plan_info=plan_info)
                    if default_entry_2.amount > 0:
                        next_card_group['entries'].append(default_entry_2)
                        next_card_group['total'] += default_entry_2.amount
                        next_card_group['default_total'] += default_entry_2.amount
            else:
                # 通常の1回払い
                # 締め日チェック（過去月の場合はスキップ）
                payment_closed = False
                current_year_month_str = f"{today.year}-{today.month:02d}"

                # billing_monthが過去月または現在月の場合のみ締め日チェック
                if billing_month >= current_year_month_str:
                    # カード情報を取得
                    card_plan = get_card_plan(actual_card_type)
                    if card_plan and card_plan.closing_day and not card_plan.is_end_of_month:
                        # 指定日締めの場合：year_monthの締め日を計算
                        year, month = map(int, year_month.split('-'))
                        closing_month = month + 1
                        closing_year = year
                        if closing_month > 12:
                            closing_month = 1
                            closing_year += 1
                        this_closing_date = date(closing_year, closing_month, card_plan.closing_day)
                        payment_closed = today.date() > this_closing_date
                    else:
                        # 月末締めの場合：year_monthの月末を締め日とする
                        year, month = map(int, year_month.split('-'))
                        last_day = calendar.monthrange(year, month)[1]
                        this_closing_date = date(year, month, last_day)
                        payment_closed = today.date() > this_closing_date

                # 締め日が過ぎていなければ表示（過去月は常に表示）
                if not payment_closed:
                    # カード情報を辞書形式で作成
                    plan_info = info if info else {}
                    default_entry = DefaultEntry(default, year_month, override_data, actual_card_type, card_plan_info=plan_info)
                    # 金額が0の場合は追加しない（削除された定期項目）
                    if default_entry.amount > 0:
                        card_group['entries'].append(default_entry)
                        card_group['total'] += default_entry.amount
                        card_group['default_total'] += default_entry.amount

    # 各カードのエントリーを利用日順にソート（日付は降順＝新しい順）
    for year_month, month_group in summary.items():
        for card_type, card_data in month_group.items():
            card_data['entries'].sort(key=lambda x: -(
                x.purchase_date.toordinal() if (hasattr(x, 'purchase_date') and x.purchase_date)
                else (x.due_date.toordinal() if (hasattr(x, 'due_date') and x.due_date) else 0)
            ))

    # 各月のカードを支払日順にソート
    for year_month, month_group in summary.items():
        def get_card_sort_key(item):
            card_key, card_data = item

            # 支払日をbilling_monthとカード種別から計算
            # 注意: due_dateは通常払いの場合は利用日、ボーナス払いの場合は支払日を意味するため、
            #       ソートには使えない。billing_monthとcard_typeから支払日を計算する。
            from datetime import date
            import calendar
            due_day = card_due_days.get(card_key)
            if due_day:
                billing_year, billing_month = map(int, year_month.split('-'))
                # 月の最終日を取得
                last_day = calendar.monthrange(billing_year, billing_month)[1]
                # 支払日が月の日数を超える場合は最終日に調整
                actual_due_day = min(due_day, last_day)
                # 営業日調整
                payment_date = adjust_to_next_business_day(date(billing_year, billing_month, actual_due_day))
            else:
                # due_dayがない場合は月初
                billing_year, billing_month = map(int, year_month.split('-'))
                payment_date = date(billing_year, billing_month, 1)

            # ボーナス払いかどうかをセカンダリキーにする（同じ日付なら通常払いを先に）
            is_bonus = card_data.get('is_bonus_section', False)
            return (payment_date, is_bonus)

        sorted_cards = OrderedDict(sorted(
            month_group.items(),
            key=get_card_sort_key
        ))
        summary[year_month] = sorted_cards

    # 空のカードグループ（エントリーが0件のカード）を削除
    for year_month in list(summary.keys()):
        month_group = summary[year_month]
        # エントリーが空のカードを削除
        cards_to_remove = [card_type for card_type, card_data in month_group.items() if len(card_data.get('entries', [])) == 0]
        for card_type in cards_to_remove:
            del month_group[card_type]
        # 月全体が空になったら削除
        if len(month_group) == 0:
            del summary[year_month]

    # summaryを現在、未来、過去に分割
    today = timezone.now()
    current_month_str = today.strftime('%Y-%m')
    current_day = today.day
    current_month_summary = OrderedDict()
    future_summary = OrderedDict()
    past_summary = OrderedDict()

    # VIEWカードは5日締めなので、5日までは先月の見積りを表示
    view_display_month = current_month_str
    if current_day <= 5:
        # 先月を計算
        prev_month_date = (today.replace(day=1) - timedelta(days=1))
        view_display_month = prev_month_date.strftime('%Y-%m')

    for ym, cards in summary.items():
        # ymが '2024-08_bonus' のような形式の場合、年月部分を取得
        ym_date_part = ym.split('_')[0]

        # ボーナス払いセクションかどうかを判定
        # ボーナス払いは支払日（due_date）で判定、通常払いは月で判定
        has_bonus_section = any(card_data.get('is_bonus_section', False) for card_data in cards.values())


        if has_bonus_section:
            # ボーナス払いの場合、最初のエントリーのdue_dateを取得
            first_entry = None
            for card_data in cards.values():
                if card_data.get('entries'):
                    first_entry = card_data['entries'][0]
                    break

            # due_dateで過去/未来を判定
            if first_entry and hasattr(first_entry, 'due_date') and first_entry.due_date:
                if first_entry.due_date < today.date():
                    # 支払日が過去
                    past_summary[ym] = cards
                elif first_entry.due_date.strftime('%Y-%m') == current_month_str:
                    # 支払日が今月
                    current_month_summary[ym] = cards
                else:
                    # 支払日が未来
                    future_summary[ym] = cards
            else:
                # due_dateがない場合は月で判定（フォールバック）
                if ym_date_part == current_month_str:
                    current_month_summary[ym] = cards
                elif ym_date_part > current_month_str:
                    future_summary[ym] = cards
                else:
                    past_summary[ym] = cards
            continue

        # 締め日が5日のカードの特別処理
        # MonthlyPlanDefaultから締め日が5日のカードを取得
        cards_with_5th_closing = set()
        for item in get_cards_by_closing_day(5):
            if item.key:
                cards_with_5th_closing.add(item.key)
                cards_with_5th_closing.add(f"{item.key}_bonus")

        if current_day <= 5 and ym_date_part == view_display_month:
            # 5日までは、先月の締め日5日のカードを当月として扱う
            has_special_closing = any(card_type in cards_with_5th_closing for card_type in cards.keys())
            if has_special_closing:
                # 締め日5日のカードのみを当月に移動
                view_cards = OrderedDict()
                other_cards = OrderedDict()
                for card_type, card_data in cards.items():
                    if card_type in cards_with_5th_closing:
                        view_cards[card_type] = card_data
                    else:
                        other_cards[card_type] = card_data

                # VIEW/VERMILLIONカードを当月に追加
                if view_cards:
                    if ym not in current_month_summary:
                        current_month_summary[ym] = OrderedDict()
                    current_month_summary[ym].update(view_cards)

                # その他のカードは過去として扱う
                if other_cards:
                    if ym not in past_summary:
                        past_summary[ym] = OrderedDict()
                    past_summary[ym].update(other_cards)
                continue

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
            card_type = request.POST.get('card_type')
            is_split_payment = request.POST.get('is_split_payment') == 'on'
            purchase_date_str = request.POST.get('purchase_date')

            try:
                default_instance = get_object_or_404(CreditDefault, pk=default_id)

                # ドル入力の場合、円に変換
                is_usd = request.POST.get('is_usd') == 'on'
                if is_usd:
                    from budget_app.utils.currency import convert_usd_to_jpy
                    from decimal import Decimal

                    usd_amount_str = request.POST.get('usd_amount')
                    if usd_amount_str:
                        usd_amount = Decimal(usd_amount_str)
                        amount = convert_usd_to_jpy(usd_amount)
                        defaults_dict = {
                            'amount': amount,
                            'is_usd': True,
                            'usd_amount': usd_amount
                        }
                    else:
                        amount_str = request.POST.get('amount')
                        amount = int(amount_str)
                        defaults_dict = {
                            'amount': amount,
                            'is_usd': False,
                            'usd_amount': None
                        }
                else:
                    amount_str = request.POST.get('amount')
                    amount = int(amount_str)
                    defaults_dict = {
                        'amount': amount,
                        'is_usd': False,
                        'usd_amount': None
                    }

                # カード種別は常に保存する（上書きで管理）
                if card_type:
                    defaults_dict['card_type'] = card_type
                # 2回払いフラグを保存
                defaults_dict['is_split_payment'] = is_split_payment
                # 利用日を保存
                if purchase_date_str:
                    from datetime import datetime
                    purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d').date()
                    defaults_dict['purchase_date_override'] = purchase_date

                override, created = DefaultChargeOverride.objects.update_or_create(
                    default=default_instance,
                    year_month=year_month,
                    defaults=defaults_dict
                )

                return JsonResponse({
                    'status': 'success',
                    'message': f'{format_year_month_display(year_month)}の「{default_instance.label}」を更新しました。'
                })
            except (ValueError, TypeError):
                return JsonResponse({'status': 'error', 'message': '無効な金額が入力されました。'}, status=400)

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

                # DefaultChargeOverrideを完全に削除
                deleted_count, _ = DefaultChargeOverride.objects.filter(
                    default=default_instance,
                    year_month=year_month
                ).delete()

                if deleted_count > 0:
                    message = f'{format_year_month_display(year_month)}の「{default_label}」を削除しました。'
                else:
                    # 上書きデータが存在しない場合、金額0の上書きを作成して非表示化
                    DefaultChargeOverride.objects.create(
                        default=default_instance,
                        year_month=year_month,
                        amount=0,
                        card_type=default_instance.card_type,
                        is_usd=False,
                        usd_amount=None
                    )
                    message = f'{format_year_month_display(year_month)}の「{default_label}」を非表示にしました。'

                return JsonResponse({
                    'status': 'success',
                    'message': message
                })
            except CreditDefault.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': '削除対象の定期項目が見つかりません。'}, status=404)

        elif action == 'reflect_card':
            year_month = request.POST.get('year_month')
            card_id = request.POST.get('card_type')  # 実際には card_id
            total_amount_str = request.POST.get('total_amount')  # フロントエンドから送られた合計金額
            is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

            # card_idからボーナス払いフラグを判定
            is_bonus = card_id.endswith('_bonus')
            if is_bonus:
                actual_card_id = card_id.replace('_bonus', '')
            else:
                actual_card_id = card_id

            # card_idからMonthlyPlanDefaultのkeyを取得
            # ボーナス払いの場合は is_bonus_payment=True の項目を検索（例: item_6 → item_7）
            try:
                if is_bonus:
                    # ボーナス払いの場合: 基本カードを取得し、それに対応するボーナス払い項目を検索
                    # actual_card_idは基本カードのID（例: item_6）
                    # まず基本カードの情報を取得
                    base_card = MonthlyPlanDefault.objects.get(
                        key=actual_card_id,
                        is_active=True
                    )

                    # 基本カードと同じカード種類でボーナス払い項目を検索
                    # card_idベースで検索（例: item_6の基本カードに対してitem_7のボーナス払い項目）
                    # ただし、item_7のcard_idはitem_7なので、タイトルベースで検索する
                    card_item = MonthlyPlanDefault.objects.filter(
                        is_bonus_payment=True,
                        is_active=True
                    ).filter(
                        title__icontains=base_card.title.replace('【ボーナス払い】', '').replace(' (ボーナス払い)', '').replace('(ボーナス払い)', '').strip()
                    ).first()

                    if not card_item:
                        raise MonthlyPlanDefault.DoesNotExist()
                else:
                    # 通常払いの場合: actual_card_idをそのまま使用
                    card_item = MonthlyPlanDefault.objects.get(
                        key=actual_card_id,
                        is_bonus_payment=False,
                        is_active=True
                    )

                monthly_plan_key = card_item.key
            except MonthlyPlanDefault.DoesNotExist:
                bonus_text = "ボーナス払い" if is_bonus else "通常払い"
                error_message = f'カードID {actual_card_id} の{bonus_text}に対応する月次計画項目が見つかりません。'
                if is_ajax:
                    return JsonResponse({'status': 'error', 'message': error_message}, status=400)
                else:
                    messages.error(request, error_message)
                    return redirect('budget_app:credit_estimates')

            # フロントエンドから内訳が送られている場合はそれを使用（再計算しない）
            manual_total_str = request.POST.get('manual_total')
            default_total_str = request.POST.get('default_total')

            if manual_total_str and default_total_str:
                # フロントエンドから内訳が送られている場合
                try:
                    manual_total = int(manual_total_str)
                    regular_total = int(default_total_str)
                except (ValueError, TypeError):
                    manual_total = 0
                    regular_total = 0
            else:
                # 内訳が送られていない場合は再計算（後方互換性のため）
                from django.db.models import Sum

                # 該当するCreditEstimateを検索
                estimates_query = CreditEstimate.objects.filter(
                    card_type=actual_card_id,
                    is_bonus_payment=is_bonus
                )

                # ボーナス払いの場合は支払月（due_date）でフィルタ
                if is_bonus:
                    estimates_query = estimates_query.filter(
                        due_date__year=int(year_month.split('-')[0]),
                        due_date__month=int(year_month.split('-')[1])
                    )
                else:
                    # 通常払いの場合はbilling_monthでフィルタ
                    estimates_query = estimates_query.filter(billing_month=year_month)

                # 手動入力データの合計額を計算
                result = estimates_query.aggregate(total=Sum('amount'))
                manual_total = result['total'] or 0

                # 定期項目の合計額を計算
                # 該当する定期項目を取得
                defaults = CreditDefault.objects.filter(
                    card_type=actual_card_id,
                    is_active=True
                )
                regular_total = 0
                for default_item in defaults:
                    # 上書きがあるか確認
                    override = DefaultChargeOverride.objects.filter(
                        default=default_item,
                        year_month=year_month
                    ).first()

                    if override:
                        # 上書きがある場合はその金額を使用
                        regular_total += override.amount
                    else:
                        # 上書きがない場合はデフォルト金額を使用
                        regular_total += default_item.amount

            # フロントエンドから送られた金額を使用（優先）
            if total_amount_str:
                try:
                    total_amount = int(total_amount_str)
                except (ValueError, TypeError):
                    total_amount = manual_total + regular_total
            else:
                # total_amountが送られていない場合は再計算
                total_amount = manual_total + regular_total

            if total_amount == 0:
                error_message = 'カードデータが見つかりません。'
                if is_ajax:
                    return JsonResponse({'status': 'error', 'message': error_message}, status=400)
                else:
                    messages.error(request, error_message)
                    return redirect('budget_app:credit_estimates')

            # カードラベルを取得
            card_item_for_label = get_card_by_key(actual_card_id)
            if card_item_for_label:
                card_label = card_item_for_label.title
                if is_bonus:
                    card_label += '【ボーナス払い】'
            else:
                card_label = actual_card_id

            # 反映先の年月を計算
            # クレカ見積もりページでは、通常払いもボーナス払いも
            # 既に支払月（billing_month）で表示されているため、そのまま使用
            target_year_month = year_month

            # 月次計画を取得または作成
            plan, created = MonthlyPlan.objects.get_or_create(year_month=target_year_month)

            # set_itemメソッドを使用（items JSONFieldに保存）
            plan.set_item(monthly_plan_key, total_amount)
            plan.save()

            # 内訳を含むメッセージ作成
            breakdown = []
            if manual_total > 0:
                breakdown.append(f'手動入力: {manual_total:,}円')
            if regular_total > 0:
                breakdown.append(f'定期項目: {regular_total:,}円')
            breakdown_text = ' (' + ', '.join(breakdown) + ')' if breakdown else ''
            success_message = f'{format_year_month_display(year_month)}の「{card_label}」を{format_year_month_display(target_year_month)}の月次計画に反映しました（合計: {total_amount:,}円{breakdown_text}）'

            if is_ajax:
                response_data = {
                    'status': 'success',
                    'message': success_message,
                    'target_year_month': target_year_month,
                }
                # 現在月以降の場合は target_url を返してリダイレクト（新規作成でも既存でも）
                # （一覧に表示されない過去の月の場合はリダイレクトしない）
                from datetime import date
                today = date.today()
                current_year_month = f"{today.year}-{today.month:02d}"

                # 現在月以降の場合のみリダイレクト（新規作成でも既存でも）
                if target_year_month >= current_year_month:
                    target_url = reverse('budget_app:index') + f'#plan-{target_year_month}'
                    response_data['target_url'] = target_url
                return JsonResponse(response_data)
            else:
                messages.success(request, success_message)
                # リファラーをチェックして適切なページにリダイレクト
                referer = request.META.get('HTTP_REFERER', '')
                if 'past-transactions' in referer:
                    return redirect('budget_app:past_transactions')
                return redirect('budget_app:credit_estimates')

        elif action == 'reflect':
            from django.db.models import Sum

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

                        # 手動入力と定期項目を分けて計算
                        # 手動入力データの合計
                        if is_bonus:
                            estimates = CreditEstimate.objects.filter(
                                card_type=card_type,
                                is_bonus_payment=True,
                                due_date__year=int(year_month.split('-')[0]),
                                due_date__month=int(year_month.split('-')[1])
                            )
                        else:
                            estimates = CreditEstimate.objects.filter(
                                card_type=card_type,
                                billing_month=year_month,
                                is_bonus_payment=False
                            )
                        manual_total = estimates.aggregate(total=Sum('amount'))['total'] or 0

                        # 定期項目の合計（ボーナス払いは定期項目対象外）
                        regular_total = 0
                        if not is_bonus:
                            # カード情報を取得して締め日タイプを確認
                            card_plan = get_card_plan(card_type)

                            if card_plan:
                                # billing_monthからyear_monthを逆算
                                billing_year, billing_month_num = map(int, year_month.split('-'))

                                if card_plan.is_end_of_month:
                                    usage_month_num = billing_month_num - 1
                                else:
                                    usage_month_num = billing_month_num - 2

                                usage_year = billing_year
                                if usage_month_num < 1:
                                    usage_month_num += 12
                                    usage_year -= 1

                                usage_year_month = f"{usage_year}-{usage_month_num:02d}"

                                # 該当するDefaultChargeOverrideを取得
                                overrides = DefaultChargeOverride.objects.filter(
                                    year_month=usage_year_month,
                                    card_type=card_type
                                ).select_related('default')

                                # 奇数月のみ適用フラグのチェック
                                usage_month_int = int(usage_month_num)
                                is_odd_month_flag = (usage_month_int % 2 == 1)

                                for override in overrides:
                                    if override.default.apply_odd_months_only and not is_odd_month:
                                        continue
                                    regular_total += override.amount

                        # 合計額
                        total_amount = manual_total + regular_total

                        # 反映先の年月を計算
                        current_date = datetime.strptime(year_month, '%Y-%m')

                        # year_monthは既にbilling_month（支払月）なので、そのまま使用
                        target_year_month = year_month

                        # 月次計画を取得または作成
                        # MonthlyPlanDefaultからデフォルト値を取得
                        default_items = get_active_defaults_ordered()
                        items_defaults = {}
                        for item in default_items:
                            if item.key:
                                items_defaults[item.key] = item.amount or 0

                        plan, _ = MonthlyPlan.objects.get_or_create(
                            year_month=target_year_month,
                            defaults={'items': items_defaults}
                        )

                        # 通常払いまたはボーナス払いを反映
                        if is_bonus:
                            field_name = f'{card_type}_card_bonus'
                        else:
                            field_name = f'{card_type}_card'

                        # set_itemメソッドを使用（items JSONFieldに保存）
                        plan.set_item(field_name, total_amount)
                        plan.save()

                        # 反映詳細を記録（内訳付き）
                        plan_display = format_year_month_display(target_year_month)
                        card_label = data.get('label', card_type)
                        if plan_display not in reflected_details:
                            reflected_details[plan_display] = []

                        # 内訳を含むメッセージ作成
                        breakdown = []
                        if manual_total > 0:
                            breakdown.append(f'手動入力: {manual_total:,}円')
                        if regular_total > 0:
                            breakdown.append(f'定期項目: {regular_total:,}円')
                        breakdown_text = ' (' + ', '.join(breakdown) + ')' if breakdown else ''

                        reflected_details[plan_display].append(f"{card_label}: {total_amount:,}円{breakdown_text}")

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

                # ドル入力の場合、円に変換
                is_usd = request.POST.get('is_usd') == 'on'
                if is_usd:
                    from budget_app.utils.currency import convert_usd_to_jpy
                    from decimal import Decimal

                    usd_amount_str = request.POST.get('usd_amount')
                    if usd_amount_str:
                        usd_amount = Decimal(usd_amount_str)
                        estimate.is_usd = True
                        estimate.usd_amount = usd_amount
                        estimate.amount = convert_usd_to_jpy(usd_amount)
                    else:
                        estimate.is_usd = False
                        estimate.usd_amount = None
                else:
                    estimate.is_usd = False
                    estimate.usd_amount = None

                # ボーナス払いの場合、年月を直近の1月/8月に変更
                if estimate.is_bonus_payment:
                    estimate.year_month = get_next_bonus_month(estimate.year_month)

                instance = form.save() # 分割払い対応のためsaveメソッドを使う

                # 追加した見積もりが表示される年月を取得
                target_month = None
                if instance.billing_month:
                    target_month = instance.billing_month
                elif instance.is_bonus_payment and instance.due_date:
                    target_month = instance.due_date.strftime('%Y-%m')
                elif instance.year_month:
                    target_month = instance.year_month

                # 締め日チェック：過去の見積もりか現在/未来の見積もりかを判定
                from datetime import date as dt_date
                import calendar
                current_date = timezone.now().date()
                is_past_estimate = False

                try:
                    if not instance.is_bonus_payment and instance.year_month and instance.card_type:
                        # 通常払いの場合、締め日が過ぎたかチェック
                        closing_date = calculate_closing_date(instance.year_month, instance.card_type)
                        # 締め日の翌日以降なら過去の見積もり
                        if closing_date and current_date > closing_date:
                            is_past_estimate = True
                    elif instance.is_bonus_payment and instance.due_date:
                        # ボーナス払いの場合、支払日が過ぎたかチェック
                        if current_date >= instance.due_date:
                            is_past_estimate = True
                except Exception as e:
                    # 締め日チェックでエラーが発生した場合はログに記録してスキップ
        
        
                    logger.error(f'Error in closing date check: {e}')

                # 過去の見積もりなら past_transactions ページへ、そうでなければ credit_estimates ページへ
                if is_past_estimate:
                    target_page = 'budget_app:past_transactions'
                else:
                    target_page = 'budget_app:credit_estimates'

                # アンカー付きURLを生成
                if target_month:
                    anchor = f'#estimate-content-{target_month}'
                else:
                    anchor = ''

                if is_ajax:
                    target_url = reverse(target_page) + anchor
                    return JsonResponse({
                        'status': 'success',
                        'message': 'クレカ見積りを追加しました。',
                        'target_url': target_url
                    })
                messages.success(request, 'クレカ見積りを追加しました。')
                return HttpResponseRedirect(reverse(target_page) + anchor)
            else:
                if is_ajax:
                    return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
                messages.error(request, f'エラー: {form.errors.as_text()}')
                return redirect('budget_app:credit_estimates')

        # どのactionにも一致しない場合は、単にリダイレクト
        return redirect('budget_app:credit_estimates')
    
    # GETリクエストの場合、またはPOSTでエラーがあり再表示する場合のフォームを定義
    # このスコープで定義することで、POST処理後に変数が未定義になることを防ぐ
    initial_data = {'year': timezone.now().year, 'month': f"{timezone.now().month:02d}"}
    if 'form' not in locals():
        form = CreditEstimateForm(initial=initial_data)

    # カード選択肢を取得（新規追加モーダル用）
    card_choices = get_card_choices_for_form()

    context = {
        'form': form,
        'card_labels': card_labels,
        'card_choices': card_choices,
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
        # 分割払いの場合、カード種別の変更をチェック
        if estimate.split_payment_group and estimate.split_payment_part is not None:
            new_card_type = request.POST.get('card_type')
            if new_card_type and new_card_type != estimate.card_type:
                if is_ajax:
                    return JsonResponse({
                        'status': 'error',
                        'message': '分割払いのため、カード種別は変更できません。'
                    }, status=400)
                messages.error(request, '分割払いのため、カード種別は変更できません。')
                referer = request.META.get('HTTP_REFERER', '')
                if 'past-transactions' in referer:
                    return redirect('budget_app:past_transactions')
                return redirect('budget_app:credit_estimates')

        form = CreditEstimateForm(request.POST, instance=estimate)
        if form.is_valid():
            updated_estimate = form.save(commit=False)

            # ドル入力の場合、円に変換
            is_usd = request.POST.get('is_usd') == 'on'
            if is_usd:
                from budget_app.utils.currency import convert_usd_to_jpy
                from decimal import Decimal

                usd_amount_str = request.POST.get('usd_amount')
                if usd_amount_str:
                    usd_amount = Decimal(usd_amount_str)
                    updated_estimate.is_usd = True
                    updated_estimate.usd_amount = usd_amount
                    updated_estimate.amount = convert_usd_to_jpy(usd_amount)
                else:
                    updated_estimate.is_usd = False
                    updated_estimate.usd_amount = None
            else:
                updated_estimate.is_usd = False
                updated_estimate.usd_amount = None

            # フォームのsave()メソッドで分割払いとボーナス払いの処理を含めて保存
            updated_estimate.save()

            # 更新後の見積もりが表示される年月を取得
            target_month = None
            if updated_estimate.billing_month:
                target_month = updated_estimate.billing_month
            elif updated_estimate.is_bonus_payment and updated_estimate.due_date:
                target_month = updated_estimate.due_date.strftime('%Y-%m')
            elif updated_estimate.year_month:
                target_month = updated_estimate.year_month

            # 締め日をチェックして、過去の明細かクレカ見積もりか判定
            from datetime import datetime, date
            import calendar

            current_date = datetime.now().date()
            is_past_transaction = False

            # ボーナス払いの場合は支払日で判定
            if updated_estimate.is_bonus_payment and updated_estimate.due_date:
                is_past_transaction = updated_estimate.due_date < current_date
            # 通常払いの場合は締め日で判定
            elif updated_estimate.year_month:
                closing_date = calculate_closing_date(updated_estimate.year_month, updated_estimate.card_type)
                # 締め日の翌日以降なら過去の明細
                is_past_transaction = current_date > closing_date if closing_date else False

            # 締め日チェックの結果に基づいてページを判定
            if is_past_transaction:
                target_page = 'budget_app:past_transactions'
            else:
                target_page = 'budget_app:credit_estimates'

            # アンカー付きURLを生成
            if target_month:
                anchor = f'#estimate-content-{target_month}'
            else:
                anchor = ''

            if is_ajax:
                target_url = reverse(target_page) + anchor
                return JsonResponse({
                    'status': 'success',
                    'message': 'クレカ見積りを更新しました。',
                    'target_url': target_url
                })
            messages.success(request, 'クレカ見積りを更新しました。')
            return HttpResponseRedirect(reverse(target_page) + anchor)
        else:
            if is_ajax:
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
            messages.error(request, '更新に失敗しました。入力内容を確認してください。')
            # リファラーをチェックして適切なページにリダイレクト
            referer = request.META.get('HTTP_REFERER', '')
            if 'past-transactions' in referer:
                return redirect('budget_app:past_transactions')
            return redirect('budget_app:credit_estimates')

    # GETリクエストやAjaxでないPOSTの場合は、ここでは何も返さず、リダイレクトさせる
    referer = request.META.get('HTTP_REFERER', '')
    if 'past-transactions' in referer:
        return redirect('budget_app:past_transactions')
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

                # 削除前に表示先の情報を取得
                target_month = None
                if estimate.billing_month:
                    target_month = estimate.billing_month
                elif estimate.is_bonus_payment and estimate.due_date:
                    target_month = estimate.due_date.strftime('%Y-%m')
                elif estimate.year_month:
                    target_month = estimate.year_month

                # 分割払いの場合、ペアも一緒に削除
                if estimate.is_split_payment and estimate.split_payment_group:
                    # 同じグループIDを持つ他のレコードも削除
                    CreditEstimate.objects.filter(
                        split_payment_group=estimate.split_payment_group
                    ).delete()
                    message = '分割払いのクレカ見積り（両方）を削除しました。'
                else:
                    estimate.delete()
                    message = 'クレカ見積りを削除しました。'

            # リファラーをチェックして適切なページを判定
            referer = request.META.get('HTTP_REFERER', '')
            if 'past-transactions' in referer:
                target_page = 'budget_app:past_transactions'
            else:
                target_page = 'budget_app:credit_estimates'

            # アンカー付きURLを生成
            if target_month:
                anchor = f'#estimate-content-{target_month}'
            else:
                anchor = ''

            if is_ajax:
                target_url = reverse(target_page) + anchor
                return JsonResponse({
                    'status': 'success',
                    'message': message,
                    'target_url': target_url
                })
            else:
                messages.success(request, message)
                return HttpResponseRedirect(reverse(target_page) + anchor)

        except Exception as e:


            logger.error(f'Error deleting credit estimate: {e}', exc_info=True)
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': '削除中にエラーが発生しました。'}, status=500)
            else:
                messages.error(request, '削除中にエラーが発生しました。')
                referer = request.META.get('HTTP_REFERER', '')
                if 'past-transactions' in referer:
                    return redirect('budget_app:past_transactions')
                return redirect('budget_app:credit_estimates')

    # POST以外のリクエストはリダイレクト
    return redirect('budget_app:credit_estimates')


def credit_default_list(request):
    """定期デフォルト（サブスク・固定費）の編集"""
    defaults = CreditDefault.objects.filter(is_active=True).order_by('payment_day', 'id')

    # POST時の処理
    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        action = request.POST.get('action')

        if action == 'create':
            form = CreditDefaultForm(request.POST)
            if form.is_valid():
                instance = form.save(commit=False)

                # ドル入力の場合、円に変換
                is_usd = request.POST.get('is_usd') == 'on'
                if is_usd:
                    from budget_app.utils.currency import convert_usd_to_jpy
                    from decimal import Decimal

                    usd_amount_str = request.POST.get('usd_amount')
                    if usd_amount_str:
                        usd_amount = Decimal(usd_amount_str)
                        instance.is_usd = True
                        instance.usd_amount = usd_amount
                        instance.amount = convert_usd_to_jpy(usd_amount)
                    else:
                        instance.is_usd = False
                        instance.usd_amount = None
                else:
                    instance.is_usd = False
                    instance.usd_amount = None

                instance.save()

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

            # 保存前の値を記録
            old_amount = instance.amount
            old_card_type = instance.card_type
            old_payment_day = instance.payment_day

            form = CreditDefaultForm(request.POST, instance=instance)
            if form.is_valid():
                instance = form.save(commit=False)

                # ドル入力の場合、円に変換
                is_usd = request.POST.get('is_usd') == 'on'
                if is_usd:
                    from budget_app.utils.currency import convert_usd_to_jpy
                    from decimal import Decimal

                    usd_amount_str = request.POST.get('usd_amount')
                    if usd_amount_str:
                        usd_amount = Decimal(usd_amount_str)
                        instance.is_usd = True
                        instance.usd_amount = usd_amount
                        instance.amount = convert_usd_to_jpy(usd_amount)
                    else:
                        instance.is_usd = False
                        instance.usd_amount = None
                else:
                    instance.is_usd = False
                    instance.usd_amount = None

                instance.save()

                # 今月以降の上書きデータを更新
                from datetime import datetime
                today = timezone.now()
                current_year_month = f"{today.year}-{today.month:02d}"

                # 今月以降の全ての上書きデータを取得
                future_overrides = DefaultChargeOverride.objects.filter(
                    default=instance,
                    year_month__gte=current_year_month
                )

                updated_count = 0
                for override in future_overrides:
                    needs_update = False
                    # 金額が変更された場合、元の金額と同じ場合のみ更新（手動変更を尊重）
                    if old_amount != instance.amount and override.amount == old_amount:
                        override.amount = instance.amount
                        override.is_usd = instance.is_usd
                        override.usd_amount = instance.usd_amount
                        needs_update = True
                    # カード種別が変更された場合、元のカード種別と同じ場合のみ更新
                    if old_card_type != instance.card_type and override.card_type == old_card_type:
                        override.card_type = instance.card_type
                        needs_update = True

                    if needs_update:
                        override.save()
                        updated_count += 1

                if is_ajax:
                    # Get card type display name from MonthlyPlanDefault
                    card_type_display = instance.card_type
                    if instance.card_type:
                        card_item = get_card_by_key(instance.card_type)
                        if card_item:
                            card_type_display = card_item.title

                    message = f'{instance.label} を更新しました。'
                    if updated_count > 0:
                        message += f' 今月以降の{updated_count}件の見積もりにも反映しました。'

                    return JsonResponse({
                        'status': 'success',
                        'message': message,
                        'default': {
                            'id': instance.id,
                            'label': instance.label,
                            'card_type': instance.card_type,
                            'card_type_display': card_type_display,
                            'amount': instance.amount,
                        }
                    })

                success_message = f'{instance.label} を更新しました。'
                if updated_count > 0:
                    success_message += f' 今月以降の{updated_count}件の見積もりにも反映しました。'
                messages.success(request, success_message)
            else:
                if is_ajax:
                    return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
                messages.error(request, f'エラー: {form.errors.as_text()}')
        
        return redirect('budget_app:credit_defaults')

    # GETリクエスト、またはバリデーションエラーがあった場合のフォーム
    form = CreditDefaultForm()
    forms_by_id = {d.id: CreditDefaultForm(instance=d, prefix=str(d.id)) for d in defaults}

    # カード種別の選択肢を取得（MonthlyPlanDefaultから）
    # card_idが設定されているものをクレジットカード項目とみなす
    # is_active=Falseのカードも含める（ユーザーが登録したカードを全て表示）
    card_choices = get_card_choices_for_form()

    return render(request, 'budget_app/credit_defaults.html', {
        'defaults': defaults,
        'forms_by_id': forms_by_id,
        'form': form,  # 'create_form' から 'form' に変更
        'card_choices': card_choices,
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


def monthly_plan_default_list(request):
    """月次計画デフォルト項目の管理"""
    defaults = get_active_defaults_ordered()

    # POST時の処理
    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        action = request.POST.get('action')

        if action == 'create':
            form = MonthlyPlanDefaultForm(request.POST)
            if form.is_valid():
                instance = form.save(commit=False)
                # 表示順を設定（最後尾に追加）
                max_order = MonthlyPlanDefault.objects.filter(is_active=True).aggregate(
                    max_order=django_models.Max('order')
                )['max_order']
                instance.order = (max_order or 0) + 1
                instance.save()
                if is_ajax:
                    return JsonResponse({
                        'status': 'success',
                        'message': f'デフォルト項目「{instance.title}」を作成しました。',
                        'default': {
                            'id': instance.id,
                            'title': instance.title,
                            'amount': instance.amount,
                            'withdrawal_day': instance.withdrawal_day,
                            'is_withdrawal_end_of_month': instance.is_withdrawal_end_of_month,
                            'consider_holidays': instance.consider_holidays,
                            'closing_day': instance.closing_day,
                            'is_end_of_month': instance.is_end_of_month,
                        }
                    })
                messages.success(request, f'デフォルト項目「{instance.title}」を作成しました。')
            else:
                if is_ajax:
                    return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
                messages.error(request, f'エラー: {form.errors.as_text()}')

        elif action == 'update':
            target_id = request.POST.get('id')
            instance = get_object_or_404(MonthlyPlanDefault, pk=target_id)
            # 現在のorderを保存
            current_order = instance.order
            # 元の金額を保存（auto-propagation用）
            old_amount = instance.amount
            old_key = instance.key

            form = MonthlyPlanDefaultForm(request.POST, instance=instance)
            if form.is_valid():
                instance = form.save(commit=False)
                # orderを復元（フォームに含まれていないため）
                instance.order = current_order
                instance.save()

                # Auto-propagation: 今月以降の月次計画に反映
                from datetime import date
                current_year_month = date.today().strftime('%Y-%m')
                updated_count = 0

                if old_amount != instance.amount:
                    # 今月以降のMonthlyPlanを取得
                    future_plans = MonthlyPlan.objects.filter(year_month__gte=current_year_month)

                    for plan in future_plans:
                        # itemsの中に該当キーがあり、金額が古い金額と一致する場合のみ更新
                        if old_key in plan.items and plan.items[old_key] == old_amount:
                            plan.items[old_key] = instance.amount
                            plan.save()
                            updated_count += 1

                message = f'{instance.title} を更新しました。'
                if updated_count > 0:
                    message += f' ({updated_count}件の月次計画を更新しました)'

                if is_ajax:
                    return JsonResponse({
                        'status': 'success',
                        'message': message,
                        'default': {
                            'id': instance.id,
                            'title': instance.title,
                            'amount': instance.amount,
                            'withdrawal_day': instance.withdrawal_day,
                            'is_withdrawal_end_of_month': instance.is_withdrawal_end_of_month,
                            'consider_holidays': instance.consider_holidays,
                            'closing_day': instance.closing_day,
                            'is_end_of_month': instance.is_end_of_month,
                        }
                    })
                messages.success(request, message)
            else:
                if is_ajax:
                    return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
                messages.error(request, f'エラー: {form.errors.as_text()}')

        return redirect('budget_app:monthly_plan_defaults')

    # GETリクエスト、またはバリデーションエラーがあった場合のフォーム
    form = MonthlyPlanDefaultForm()
    forms_by_id = {d.id: MonthlyPlanDefaultForm(instance=d, prefix=str(d.id)) for d in defaults}

    # デフォルト金額の有無で分ける
    defaults_with_amount = [d for d in defaults if d.amount]
    defaults_without_amount = [d for d in defaults if not d.amount]

    return render(request, 'budget_app/monthly_plan_defaults.html', {
        'defaults': defaults,
        'defaults_with_amount': defaults_with_amount,
        'defaults_without_amount': defaults_without_amount,
        'forms_by_id': forms_by_id,
        'form': form,
    })


def monthly_plan_default_delete(request, pk):
    """月次計画デフォルト項目削除（論理削除）"""
    default = get_object_or_404(MonthlyPlanDefault, pk=pk)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        title = default.title
        # 論理削除：is_activeをFalseに設定
        default.is_active = False
        default.save()
        if is_ajax:
            return JsonResponse({'status': 'success', 'message': f'{title} を削除しました。'})
        messages.success(request, f'{title} を削除しました。')

    if is_ajax:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)
    return redirect('budget_app:monthly_plan_defaults')


def salary_list(request):
    """給与一覧"""
    from .models import Salary
    import json

    # 全ての給与明細を取得（新しい順）
    salaries = Salary.objects.all().order_by('-year_month')

    # 全ての年を取得
    all_years = set()
    for salary in salaries:
        year = int(salary.year_month.split('-')[0])
        all_years.add(year)

    # 年を降順でソート（新しい年が先）
    sorted_years = sorted(all_years, reverse=True)

    # 各年の年間集計を計算
    annual_summaries = []
    for year in sorted_years:
        # その年のデータを取得
        year_salaries = salaries.filter(year_month__startswith=str(year))

        # データがない年はスキップ
        if year_salaries.count() == 0:
            continue

        # その年の集計（通常給与 + ボーナス）
        total_gross = sum(s.gross_salary for s in year_salaries)
        total_bonus_gross = sum(s.bonus_gross_salary for s in year_salaries if s.has_bonus)
        total_transportation = sum(s.transportation for s in year_salaries)
        total_deductions = sum(s.deductions for s in year_salaries)
        total_bonus_deductions = sum(s.bonus_deductions for s in year_salaries if s.has_bonus)
        total_net = sum(s.get_net_salary() + s.get_net_bonus() for s in year_salaries)

        # 合計
        total_all_gross = total_gross + total_bonus_gross
        total_all_deductions = total_deductions + total_bonus_deductions
        total_all_net = total_net
        gross_minus_transport = total_all_gross - total_transportation

        # 総支給額が0円の年もスキップ
        if total_all_gross == 0:
            continue

        # 平均控除率を計算
        avg_deduction_rate = 0.0
        if gross_minus_transport > 0:
            avg_deduction_rate = (total_all_deductions / gross_minus_transport) * 100

        annual_summaries.append({
            'year': year,
            'total_gross': total_gross,
            'total_bonus_gross': total_bonus_gross,
            'total_all_gross': total_all_gross,
            'total_transportation': total_transportation,
            'total_deductions': total_deductions,
            'total_bonus_deductions': total_bonus_deductions,
            'total_all_deductions': total_all_deductions,
            'total_net': total_net,
            'total_all_net': total_all_net,
            'gross_minus_transport': gross_minus_transport,
            'avg_deduction_rate': round(avg_deduction_rate, 1),
            'count': year_salaries.count(),
        })

    # 登録済みの年月リストを取得（モーダルで除外するため）
    registered_year_months = list(
        Salary.objects.values_list('year_month', flat=True)
    )

    context = {
        'salaries': salaries,
        'annual_summaries': annual_summaries,
        'registered_year_months': json.dumps(registered_year_months),
    }
    return render(request, 'budget_app/salary_list.html', context)


@require_http_methods(["POST"])
def salary_create(request):
    """給与明細の新規登録"""
    from .models import Salary
    from django.contrib import messages

    try:
        year = request.POST.get('year')
        month = request.POST.get('month')
        year_month = f"{year}-{month}"

        # 既に存在する場合はエラー
        if Salary.objects.filter(year_month=year_month).exists():
            return JsonResponse({
                'status': 'error',
                'message': f'{year}年{int(month)}月の給与明細は既に登録されています。'
            }, status=400)

        # 給与明細作成
        salary = Salary.objects.create(
            year_month=year_month,
            gross_salary=int(request.POST.get('gross_salary', 0)),
            deductions=int(request.POST.get('deductions', 0)),
            transportation=int(request.POST.get('transportation', 0)),
            has_bonus=request.POST.get('has_bonus') == 'true',
            bonus_gross_salary=int(request.POST.get('bonus_gross_salary', 0)),
            bonus_deductions=int(request.POST.get('bonus_deductions', 0)),
        )

        # モバイル表示時に対象月にスクロールするためのアンカーを追加
        target_url = reverse('budget_app:salary_list') + f'#salary-{year_month}'
        return JsonResponse({
            'status': 'success',
            'message': f'{year}年{int(month)}月の給与明細を登録しました。',
            'target_url': target_url
        })

    except Exception as e:


        logger.error(f'Error creating salary: {e}', exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': '給与明細の登録に失敗しました。'
        }, status=500)


@require_http_methods(["POST"])
def salary_edit(request, salary_id):
    """給与明細の編集"""
    from .models import Salary
    from django.contrib import messages

    try:
        salary = Salary.objects.get(pk=salary_id)

        # 給与明細更新
        salary.gross_salary = int(request.POST.get('gross_salary', 0))
        salary.deductions = int(request.POST.get('deductions', 0))
        salary.transportation = int(request.POST.get('transportation', 0))

        # ボーナス明細更新（ボーナス未登録の場合のみ）
        if not salary.has_bonus:
            has_bonus_param = request.POST.get('has_bonus') == 'true'
            if has_bonus_param:
                salary.has_bonus = True
                salary.bonus_gross_salary = int(request.POST.get('bonus_gross_salary', 0))
                salary.bonus_deductions = int(request.POST.get('bonus_deductions', 0))

        salary.save()

        # モバイル表示時に対象月にスクロールするためのアンカーを追加
        target_url = reverse('budget_app:salary_list') + f'#salary-{salary.year_month}'
        return JsonResponse({
            'status': 'success',
            'message': f'{salary.year_month}の給与明細を更新しました。',
            'target_url': target_url
        })

    except Salary.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': '給与明細が見つかりません。'
        }, status=404)
    except Exception as e:


        logger.error(f'Error updating salary: {e}', exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': '給与明細の更新に失敗しました。'
        }, status=500)


@require_http_methods(["POST"])
def salary_edit_bonus(request, salary_id):
    """ボーナス明細の編集"""
    from .models import Salary
    from django.contrib import messages

    try:
        salary = Salary.objects.get(pk=salary_id)

        # ボーナス明細更新
        salary.bonus_gross_salary = int(request.POST.get('bonus_gross_salary', 0))
        salary.bonus_deductions = int(request.POST.get('bonus_deductions', 0))
        salary.has_bonus = salary.bonus_gross_salary > 0 or salary.bonus_deductions > 0
        salary.save()

        # モバイル表示時に対象月にスクロールするためのアンカーを追加
        target_url = reverse('budget_app:salary_list') + f'#salary-{salary.year_month}'
        return JsonResponse({
            'status': 'success',
            'message': f'{salary.year_month}のボーナス明細を更新しました。',
            'target_url': target_url
        })

    except Salary.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': '給与明細が見つかりません。'
        }, status=404)
    except Exception as e:


        logger.error(f'Error updating bonus: {e}', exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': 'ボーナス明細の更新に失敗しました。'
        }, status=500)


@require_http_methods(["POST"])
def salary_delete(request, salary_id):
    """給与明細の削除"""
    from .models import Salary
    from django.contrib import messages

    try:
        salary = Salary.objects.get(pk=salary_id)
        year_month = salary.year_month
        salary.delete()

        messages.success(request, f'{year_month}の給与明細を削除しました。')
        return JsonResponse({'status': 'success'})

    except Salary.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': '給与明細が見つかりません。'
        }, status=404)
    except Exception as e:


        logger.error(f'Error deleting salary: {e}', exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': '給与明細の削除に失敗しました。'
        }, status=500)


def past_transactions_list(request):
    """過去の明細一覧（アーカイブ）"""
    from datetime import datetime, date as dt_date
    import calendar
    from django.http import JsonResponse

    # POST処理: 定期項目の金額編集
    if request.method == 'POST':
        action = request.POST.get('form_action')  # form_action に変更
        if action == 'edit_default_amount':
            default_id = request.POST.get('default_id')
            year_month = request.POST.get('year_month')
            card_type = request.POST.get('card_type')
            amount = request.POST.get('amount')
            purchase_date = request.POST.get('purchase_date')  # 利用日を取得

            try:
                # DefaultChargeOverrideを取得または作成
                defaults_dict = {'card_type': card_type, 'amount': amount}
                if purchase_date:
                    defaults_dict['purchase_date_override'] = purchase_date

                override, created = DefaultChargeOverride.objects.get_or_create(
                    default_id=default_id,
                    year_month=year_month,
                    defaults=defaults_dict
                )
                if not created:
                    # 既存の場合は金額、カード種別、利用日を更新
                    override.amount = amount
                    override.card_type = card_type
                    if purchase_date:
                        override.purchase_date_override = purchase_date
                    override.save()

                # Ajaxリクエストの場合はJSONレスポンスを返す
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    # 定期項目の名前を取得
                    default = CreditDefault.objects.get(id=default_id)

                    # billing_monthを計算（引き落とし月のセクションにジャンプするため）
                    year, month = map(int, year_month.split('-'))
                    card_plan = get_card_plan(card_type)

                    if card_plan:
                        if card_plan.is_end_of_month:
                            billing_month_num = month + 1
                        else:
                            billing_month_num = month + 2

                        billing_year = year
                        if billing_month_num > 12:
                            billing_month_num -= 12
                            billing_year += 1
                        billing_month = f"{billing_year}-{billing_month_num:02d}"
                    else:
                        billing_month = year_month

                    # 過去の明細画面のアンカー付きURLを生成
                    target_url = reverse('budget_app:past_transactions') + f'#estimate-content-{billing_month}'

                    return JsonResponse({
                        'status': 'success',
                        'message': f'{default.label}を更新しました。',
                        'target_url': target_url
                    })
                else:
                    return redirect('budget_app:past_transactions')
            except Exception as e:
    
    
                logger.error(f'Error updating default charge override: {e}', exc_info=True)
                return JsonResponse({'status': 'error', 'message': '更新中にエラーが発生しました。'}, status=400)

    current_date = datetime.now().date()
    current_year_month = datetime.now().strftime('%Y-%m')

    # 過去のMonthlyPlanを取得（当月より前、年月で昇順ソート）
    past_plans_qs = MonthlyPlan.objects.filter(
        year_month__lt=current_year_month
    ).order_by('year_month')

    # 当月のプランで今日以降の明細がないものも含める
    current_month_plan = MonthlyPlan.objects.filter(year_month=current_year_month).first()
    past_plans = list(past_plans_qs)

    if current_month_plan:
        # 当月のタイムラインを計算して、今日以降の明細があるかチェック
        # タイムラインを生成（plan_listと同じロジック）
        timeline = []
        default_items = get_active_defaults_ordered()

        for item in default_items:
            if not item.should_display_for_month(current_month_plan.year_month):
                continue

            value = current_month_plan.get_item(item.key)
            if value and value != 0:
                # 引落日 / 振込日を計算
                year, month = map(int, current_month_plan.year_month.split('-'))

                if item.is_withdrawal_end_of_month:
                    day = calendar.monthrange(year, month)[1]
                else:
                    day = item.withdrawal_day or 1
                    day = min(day, calendar.monthrange(year, month)[1])

                from datetime import date as dt_date
                item_date = dt_date(year, month, day)

                timeline.append({
                    'date': item_date,
                    'amount': value,
                })

        # 今日以降の明細があるかチェック
        today = current_date
        future_items = [item for item in timeline if item.get('date') and item['date'] >= today and item.get('amount', 0) != 0]

        # 今日以降の明細がない場合、過去の明細に含める
        if not future_items:
            past_plans.append(current_month_plan)  # 末尾に追加（昇順なので）

    # 過去のクレカ見積りを取得
    # 締め日が過ぎたものを表示するため、未来の引き落とし月も含めて取得
    # （例：11月利用分は1月引き落とし、締め日は12月5日 → 12月6日には過去の明細に表示）
    # billing_monthがない古いデータにも対応するため、year_monthもチェック
    from dateutil.relativedelta import relativedelta

    # 当月から3ヶ月先までのデータを取得（VIEWカードは翌々月払いなので）
    future_limit_date = current_date + relativedelta(months=3)
    future_limit_year_month = future_limit_date.strftime('%Y-%m')

    # ボーナス払いは支払日（due_date）で判定、通常払いはbilling_monthで判定

    all_estimates = CreditEstimate.objects.all()
    past_credit_estimates = []

    for est in all_estimates:
        # ボーナス払いの場合は支払日で判定
        if est.is_bonus_payment and est.due_date:
            if est.due_date < current_date:
                past_credit_estimates.append(est)
        # 通常払いの場合はbilling_monthで判定（締め日が過ぎているもの）
        else:
            billing_month = est.billing_month if est.billing_month else est.year_month
            if billing_month and billing_month <= future_limit_year_month:
                # 締め日チェック（MonthlyPlanDefaultから取得）
                year, month = map(int, est.year_month.split('-'))

                card_plan = get_card_plan(est.card_type)
                if card_plan:
                    if card_plan.is_end_of_month:
                        # 月末締めの場合：year_month = 利用月 → 締め日 = year_month の月末
                        last_day = calendar.monthrange(year, month)[1]
                        closing_date = dt_date(year, month, last_day)
                    elif card_plan.closing_day:
                        # 指定日締めの場合：year_month = 締め日の前月 → 締め日 = (year_month+1) の closing_day日
                        closing_month = month + 1
                        closing_year = year
                        if closing_month > 12:
                            closing_month = 1
                            closing_year += 1
                        closing_date = dt_date(closing_year, closing_month, card_plan.closing_day)
                    else:
                        # デフォルト: 月末締め
                        last_day = calendar.monthrange(year, month)[1]
                        closing_date = dt_date(year, month, last_day)
                else:
                    # デフォルト: 月末締め
                    last_day = calendar.monthrange(year, month)[1]
                    closing_date = dt_date(year, month, last_day)

                # 締め日の翌日以降なら過去の明細に含める
                if current_date > closing_date:
                    past_credit_estimates.append(est)

    # 定期項目（DefaultChargeOverride）も過去の明細に追加
    # 現在月以前のデータのみを取得（未来月のデータは除外）
    current_year_month = current_date.strftime('%Y-%m')
    all_overrides = DefaultChargeOverride.objects.filter(year_month__lte=current_year_month).select_related('default')

    # DefaultChargeOverrideを year_month ごとにグループ化
    for override in all_overrides:
        if not override.default.is_active:
            continue

        year_month = override.year_month
        year, month = map(int, year_month.split('-'))

        # 奇数月のみ適用フラグのチェック
        if override.default.apply_odd_months_only and not is_odd_month(year_month):
            continue

        # カード情報を取得
        card_plan = get_card_plan(override.card_type)
        if not card_plan:
            continue

        # 締め日を計算
        if card_plan.is_end_of_month:
            # 月末締めの場合：year_month = 利用月 → 締め日 = year_month の月末
            last_day = calendar.monthrange(year, month)[1]
            closing_date = dt_date(year, month, last_day)
        elif card_plan.closing_day:
            # 指定日締めの場合：year_month = 締め日の前月 → 締め日 = (year_month+1) の closing_day日
            closing_month = month + 1
            closing_year = year
            if closing_month > 12:
                closing_month = 1
                closing_year += 1
            closing_date = dt_date(closing_year, closing_month, card_plan.closing_day)
        else:
            # デフォルト: 月末締め
            last_day = calendar.monthrange(year, month)[1]
            closing_date = dt_date(year, month, last_day)

        # 締め日の翌日以降なら過去の明細に含める
        if current_date > closing_date:
            # billing_monthを計算
            if card_plan.is_end_of_month:
                billing_month_num = month + 1
            else:
                billing_month_num = month + 2

            billing_year = year
            if billing_month_num > 12:
                billing_month_num -= 12
                billing_year += 1
            billing_month = f"{billing_year}-{billing_month_num:02d}"

            # 利用日を計算（purchase_date_overrideがあればそれを使用）
            if override.purchase_date_override:
                purchase_date = override.purchase_date_override
            else:
                payment_day = override.default.payment_day
                if card_plan.is_end_of_month:
                    # 月末締めの場合：year_monthのpayment_day日
                    max_day_usage = calendar.monthrange(year, month)[1]
                    actual_day_usage = min(payment_day, max_day_usage)
                    purchase_date = dt_date(year, month, actual_day_usage)
                else:
                    # 指定日締めの場合：payment_dayと締め日を比較
                    if payment_day > card_plan.closing_day:
                        # payment_dayが締め日より大きい：year_monthの月のpayment_day日
                        max_day_usage = calendar.monthrange(year, month)[1]
                        actual_day_usage = min(payment_day, max_day_usage)
                        purchase_date = dt_date(year, month, actual_day_usage)
                    else:
                        # payment_dayが締め日以下：締め日の月のpayment_day日
                        max_day_usage = calendar.monthrange(closing_year, closing_month)[1]
                        actual_day_usage = min(payment_day, max_day_usage)
                        purchase_date = dt_date(closing_year, closing_month, actual_day_usage)

            # 引落日を計算（billing_monthのwithdrawal_day日）
            max_day_billing = calendar.monthrange(billing_year, billing_month_num)[1]
            actual_day_billing = min(card_plan.withdrawal_day, max_day_billing)
            due_date = dt_date(billing_year, billing_month_num, actual_day_billing)

            # 疑似CreditEstimateオブジェクトを作成
            class DefaultEstimate:
                def __init__(self, override_obj, year_month, billing_month, purchase_date, due_date, card_type, split_part=None, total_amount=None):
                    self.id = override_obj.id  # DefaultChargeOverrideのID
                    self.pk = override_obj.id  # DefaultChargeOverrideのID
                    self.year_month = year_month
                    self.billing_month = billing_month
                    self.card_type = card_type
                    self.description = override_obj.default.label
                    # 分割支払いの場合は金額を正しく計算
                    if split_part and total_amount is not None:
                        # 2回目の金額を10の位まで0にする（100で切り捨て）
                        second_payment = (total_amount // 2) // 100 * 100
                        if split_part == 2:
                            self.amount = second_payment
                        else:
                            # 1回目: 残り
                            self.amount = total_amount - second_payment
                    else:
                        self.amount = override_obj.amount
                    self.due_date = due_date  # 引落日
                    self.purchase_date = purchase_date  # 利用日（利用月のpayment_day）
                    self.is_bonus_payment = False
                    self.is_split_payment = override_obj.is_split_payment
                    self.split_payment_part = split_part  # 分割支払いの回数（1 or 2）
                    self.is_default = True  # 定期項目フラグ
                    self.default_id = override_obj.default.id
                    self.override_id = override_obj.id  # DefaultChargeOverrideのID
                    self.payment_day = override_obj.default.payment_day
                    self.created_at = override_obj.created_at if hasattr(override_obj, 'created_at') else None

            # 分割支払いの場合は2回分のエントリを作成
            if override.is_split_payment:
                total_amount = override.amount
                # 1回目
                default_est_1 = DefaultEstimate(override, year_month, billing_month, purchase_date, due_date, override.card_type, split_part=1, total_amount=total_amount)
                past_credit_estimates.append(default_est_1)

                # 2回目（翌月引き落とし）
                billing_month_num_2 = billing_month_num + 1
                billing_year_2 = billing_year
                if billing_month_num_2 > 12:
                    billing_month_num_2 = 1
                    billing_year_2 += 1
                billing_month_2 = f"{billing_year_2}-{billing_month_num_2:02d}"

                max_day_billing_2 = calendar.monthrange(billing_year_2, billing_month_num_2)[1]
                actual_day_billing_2 = min(card_plan.withdrawal_day, max_day_billing_2)
                due_date_2 = dt_date(billing_year_2, billing_month_num_2, actual_day_billing_2)

                default_est_2 = DefaultEstimate(override, year_month, billing_month_2, purchase_date, due_date_2, override.card_type, split_part=2, total_amount=total_amount)
                past_credit_estimates.append(default_est_2)
            else:
                default_est = DefaultEstimate(override, year_month, billing_month, purchase_date, due_date, override.card_type)
                past_credit_estimates.append(default_est)

    # 並び替え（billing_month降順、year_month降順）
    past_credit_estimates.sort(key=lambda x: (x.billing_month if x.billing_month else x.year_month, x.year_month), reverse=True)

    # 年ごとにグループ化して、月ごとの収入・支出を集計
    yearly_data = {}

    # 月次計画データを追加
    for plan in past_plans:
        from datetime import date
        year = plan.year_month[:4]

        if year not in yearly_data:
            yearly_data[year] = {
                'months': [],
                'credit_months': {},
                'total_income': 0,
                'total_expenses': 0,
                'total_net_income': 0,
                'total_credit': 0
            }

        plan_year, plan_month = map(int, plan.year_month.split('-'))
        last_day = calendar.monthrange(plan_year, plan_month)[1]

        # 収入の合計（給与、ボーナス、その他収入）
        income = plan.get_total_income()

        # 支出の合計（全ての支出項目）
        expenses = plan.get_total_expenses()

        # 支出が0円の月はスキップ
        if expenses == 0:
            continue

        def clamp_day(day: int) -> int:
            return min(max(day, 1), last_day)

        # MonthlyPlanDefaultから動的にトランザクションを生成
        default_items = MonthlyPlanDefault.objects.all().order_by('order', 'id')
        transactions = []

        for item in default_items:
            # この月に表示すべき項目かチェック
            if not item.should_display_for_month(plan.year_month):
                continue

            key = item.key
            if not key:
                continue

            # 金額を取得
            amount = plan.get_item(key)
            if amount == 0:
                continue

            # 引落日 / 振込日を計算
            day = get_day_for_field(key, plan_year, plan_month)
            item_date = date(plan_year, plan_month, clamp_day(day))

            # 休日を考慮して日付を調整
            if item.consider_holidays:
                if item.payment_type == 'deposit':
                    # 振込（給与など）: 休日なら前営業日
                    item_date = adjust_to_previous_business_day(item_date)
                else:
                    if item.title == '食費':
                        # 引き落とし: 休日なら前営業日
                        item_date = adjust_to_previous_business_day(item_date)
                    else:
                        # 引き落とし: 休日なら翌営業日
                        item_date = adjust_to_next_business_day(item_date)
            # 収入か支出かを判定
            transaction_type = 'income' if item.payment_type == 'deposit' else 'expense'

            transactions.append({
                'date': item_date,
                'name': item.title,
                'amount': amount,
                'type': transaction_type,
                'priority': item.order
            })

        # 日付順にソート（日付がないものは最後、同日は収入が先、同タイプはpriorityで並べる）
        def sort_key(x):
            return (x['date'] if x['date'] is not None else date.max, 1 if x['type'] == 'expense' else 0, x.get('priority', 0))
        transactions.sort(key=sort_key)

        # 期限が過ぎた明細のみをフィルタリング
        past_transactions = [t for t in transactions if t['date'] is None or t['date'] <= current_date]

        # 過去の明細がある場合のみ追加
        if past_transactions:
            # 実際の収入・支出を再計算
            actual_income = sum(t['amount'] for t in past_transactions if t['type'] == 'income')
            actual_expenses = sum(t['amount'] for t in past_transactions if t['type'] == 'expense')
            net_income = actual_income - actual_expenses

            yearly_data[year]['months'].append({
                'year_month': plan.year_month,
                'income': actual_income,
                'expenses': actual_expenses,
                'net_income': net_income,
                'transactions': past_transactions,
                'plan': plan
            })
            yearly_data[year]['total_income'] += actual_income
            yearly_data[year]['total_expenses'] += actual_expenses
            yearly_data[year]['total_net_income'] += net_income

    # クレカ見積りデータを月別→カード別にグループ化
    # billing_month（引き落とし月）でグループ化
    for estimate in past_credit_estimates:
        # クレカ見積もりと同じロジックで、締め日/支払日が過ぎたかチェック
        # 締め日が過ぎていないものは表示しない

        # 通常払いの場合、締め日が過ぎたかチェック
        if not estimate.is_bonus_payment:
            year, month = map(int, estimate.year_month.split('-'))
            import calendar

            # MonthlyPlanDefaultから締め日を取得
            card_plan = get_card_plan(estimate.card_type)
            if card_plan and not card_plan.is_end_of_month and card_plan.closing_day:
                # 指定日締め（翌月の締め日）
                closing_month = month + 1
                closing_year = year
                if closing_month > 12:
                    closing_month = 1
                    closing_year += 1
                closing_date = dt_date(closing_year, closing_month, card_plan.closing_day)
            else:
                # 月末締め
                last_day = calendar.monthrange(year, month)[1]
                closing_date = dt_date(year, month, last_day)

            # 締め日の翌日以降のみ表示
            if current_date <= closing_date:
                continue
        # ボーナス払いの場合、支払日が過ぎたかチェック
        elif estimate.is_bonus_payment and estimate.due_date:
            if current_date < estimate.due_date:
                continue

        billing_month = estimate.billing_month or estimate.year_month

        # billing_monthベースで年を取得
        billing_month = estimate.billing_month or estimate.year_month
        year = billing_month[:4]

        if year not in yearly_data:
            yearly_data[year] = {
                'months': [],
                'credit_months': {},
                'total_income': 0,
                'total_expenses': 0,
                'total_net_income': 0,
                'total_credit': 0
            }

        # 引き落とし月ごとにグループ化
        if billing_month not in yearly_data[year]['credit_months']:
            yearly_data[year]['credit_months'][billing_month] = {
                'year_month': billing_month,  # テンプレート互換性のため
                'cards': {},
                'total_amount': 0
            }

        # その月の中でカード別にグループ化
        # カード名に支払日を追加
        # Get card type display name from MonthlyPlanDefault
        card_type_display = estimate.card_type
        card_due_day_value = None
        if estimate.card_type:
            card_item = get_card_by_key(estimate.card_type)
            if card_item:
                card_type_display = card_item.title
                card_due_day_value = card_item.withdrawal_day

        # カードタイプと支払日のマッピング（後方互換性のため残す）
        card_due_days = {
            'view': 4,
            'rakuten': 27,
            'paypay': 27,
            'vermillion': 4,
            'amazon': 26,
            'olive': 26,
        }

        # 支払日を追加したカード名を生成
        # Use card_due_day_value from MonthlyPlanDefault if available, otherwise fall back to legacy mapping
        due_day = card_due_day_value if card_due_day_value else card_due_days.get(estimate.card_type, '')
        if due_day and billing_month:
            billing_year, billing_month_num = map(int, billing_month.split('-'))
            import calendar
            # 支払月の最終日を取得
            last_day = calendar.monthrange(billing_year, billing_month_num)[1]
            # 支払日が月の日数を超える場合は最終日に調整
            actual_due_day = min(due_day, last_day)
            # 営業日に調整（土日祝なら翌営業日）
            payment_date = adjust_to_next_business_day(dt_date(billing_year, billing_month_num, actual_due_day))
            card_name = f'{card_type_display} ({payment_date.month}/{payment_date.day}支払)'
        else:
            card_name = card_type_display

        if estimate.is_bonus_payment:
            card_name = f'{card_name}【ボーナス払い】'

        if card_name not in yearly_data[year]['credit_months'][billing_month]['cards']:
            yearly_data[year]['credit_months'][billing_month]['cards'][card_name] = {
                'card_name': card_name,
                'card_type': f"{estimate.card_type}{'_bonus' if estimate.is_bonus_payment else ''}",
                'estimates': [],
                'total_amount': 0,
                'manual_amount': 0,
                'default_amount': 0
            }

        # is_default属性を追加（過去の明細では通常の見積もりはFalse）
        # 定期項目（DefaultEstimate）の場合はすでにis_default=Trueが設定されているので上書きしない
        if not hasattr(estimate, 'is_default'):
            estimate.is_default = False

        yearly_data[year]['credit_months'][billing_month]['cards'][card_name]['estimates'].append({
            'card_type': estimate.card_type,
            'amount': estimate.amount,
            'memo': estimate.description,
            'estimate': estimate
        })
        yearly_data[year]['credit_months'][billing_month]['cards'][card_name]['total_amount'] += estimate.amount
        # 手動入力と定期項目を分けて集計
        if hasattr(estimate, 'is_default') and estimate.is_default:
            yearly_data[year]['credit_months'][billing_month]['cards'][card_name]['default_amount'] += estimate.amount
        else:
            yearly_data[year]['credit_months'][billing_month]['cards'][card_name]['manual_amount'] += estimate.amount
        yearly_data[year]['credit_months'][billing_month]['total_amount'] += estimate.amount
        yearly_data[year]['total_credit'] += estimate.amount

    # クレカ見積りの月別データをリストに変換してソート
    # billing_month（引き落とし月）でソート（降順 = 新しい順）
    for year in yearly_data:
        credit_months_list = sorted(
            yearly_data[year]['credit_months'].values(),
            key=lambda x: x['year_month'],  # year_monthはbilling_monthが入っている
            reverse=True
        )
        # 各月のカード別データをリストに変換
        for month_data in credit_months_list:
            cards_list = []
            for card_name, card_data in month_data['cards'].items():
                # 各カードの明細を利用日順にソート（降順 = 新しい順）
                def get_sort_key(est):
                    # purchase_dateを優先、なければdue_date、それもなければyear_month
                    purchase = est['estimate'].purchase_date
                    due = est['estimate'].due_date
                    is_bonus = est['estimate'].is_bonus_payment

                    # ソートキー：日付（purchase_date優先）、is_bonus_payment、id
                    date_key = purchase if purchase else (due if due else dt_date.max)
                    return (date_key, is_bonus, est['estimate'].id if hasattr(est['estimate'], 'id') else 0)

                card_data['estimates'] = sorted(card_data['estimates'], key=get_sort_key, reverse=True)
                cards_list.append(card_data)

            # カードの表示順をモデルの定義順に合わせる
            card_order = {
                display_name: i
                for i, (_, display_name) in enumerate(CreditEstimate.CARD_TYPES)
            }
            month_data['cards'] = sorted(
                cards_list, key=lambda x: card_order.get(x['card_name'], 99)
            )

        yearly_data[year]['credit_months'] = credit_months_list

    # 月次計画データを降順にソート（新しい月が上に来るように）
    for year in yearly_data:
        yearly_data[year]['months'] = sorted(
            yearly_data[year]['months'],
            key=lambda x: x['year_month'],
            reverse=True
        )

    # 給与データ以外（支出データ）がない年を除外
    filtered_yearly_data = {}
    for year, data in yearly_data.items():
        # 月次計画の支出データがあるか、またはクレカ見積りがあるかをチェック
        has_expense_data = (
            len(data['months']) > 0 or  # 月次計画の支出データ（支出が0円の月は既にスキップされている）
            len(data['credit_months']) > 0  # クレカ見積りデータ
        )
        if has_expense_data:
            filtered_yearly_data[year] = data

    # 年ごとに降順ソート
    sorted_years = sorted(filtered_yearly_data.keys(), reverse=True)

    # MonthlyPlanDefaultから有効な項目を取得（テンプレートで使用）
    default_items = get_active_defaults_ordered()

    # ハードコードされたフィールド（既存のテンプレートとの互換性のため）
    # 古いフィールド名と新しいkey名の両方を含める
    # 動的フィールド（MonthlyPlanDefaultから取得）
    hardcoded_fields = [item.key for item in default_items if item.key]

    # カード選択肢を取得（新規追加モーダル用）
    card_choices = get_card_choices_for_form()

    context = {
        'yearly_data': filtered_yearly_data,
        'sorted_years': sorted_years,
        'default_items': default_items,
        'hardcoded_fields': hardcoded_fields,
        'card_choices': card_choices,
    }
    return render(request, 'budget_app/past_transactions.html', context)
