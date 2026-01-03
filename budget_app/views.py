from django import forms
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
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

def get_monthly_plan_defaults():
    """
    月次計画のデフォルト値を取得する
    MonthlyPlanDefaultテーブルから有効なデフォルト項目を取得し、
    keyをキーとした辞書を返す
    """
    defaults = {}
    default_items = MonthlyPlanDefault.objects.filter(is_active=True).order_by('order', 'id')

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
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Form validation errors: {form.errors}")
            logger.error(f"POST data: {request.POST}")
            messages.error(request, 'エラーが発生しました。入力内容を確認してください。')
    else:
        form = SimulationConfigForm(instance=config)

    # 月次計画デフォルト項目のデータを取得（論理削除されていないもののみ）
    defaults = MonthlyPlanDefault.objects.filter(is_active=True).order_by('order', 'id')
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
        if plan.has_savings:
            cumulative_savings += savings_amount
        plan.savings_amount_display = cumulative_savings if plan.has_savings else 0

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

            # 引き落とし日/振込日を計算
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

            # item_14（マネーアシスト返済）の場合、借入月情報を追加
            display_name = item.title
            if key == 'item_14':
                # 前月の借入情報を取得
                from datetime import datetime
                from dateutil.relativedelta import relativedelta
                try:
                    current_date = datetime.strptime(plan.year_month, '%Y-%m')
                    previous_date = current_date - relativedelta(months=1)
                    previous_year_month = previous_date.strftime('%Y-%m')
                    previous_plan = MonthlyPlan.objects.filter(year_month=previous_year_month).first()

                    if previous_plan:
                        borrowing_amount = previous_plan.get_item('item_15')
                        if borrowing_amount > 0:
                            # item_15（借入）の依存元キーを動的に取得
                            # depends_on_keyがitem_14を参照している項目を探す
                            borrowing_item = None
                            for default_item in default_items:
                                if default_item.depends_on_key == key and default_item.key != key:
                                    borrowing_item = default_item
                                    break

                            # 見つからない場合はitem_15を直接検索（後方互換性）
                            if not borrowing_item:
                                borrowing_item = MonthlyPlanDefault.objects.filter(key='item_15').first()

                            if borrowing_item:
                                # 借入日を計算
                                borrowing_day = get_day_for_field(borrowing_item.key, previous_date.year, previous_date.month)
                                prev_month = previous_date.month
                                display_name = f"{item.title} ({prev_month}/{borrowing_day}借入分)"
                except Exception:
                    pass

            transactions.append({
                'date': item_date,
                'name': display_name,
                'amount': transaction_amount,
                'is_view_card': is_view_card,
                'is_excluded': is_excluded
            })

        # 日付順にソート（日付がNoneの場合は最後、同日の場合は収入を先に）
        transactions.sort(key=lambda x: (x['date'] if x['date'] is not None else date.max, -x['amount']))

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

            # 繰上げ返済でチェックされている場合は残高計算から除外
            if not transaction.get('is_excluded', False):
                current_balance += transaction['amount']

            timeline.append({
                'date': transaction['date'],
                'name': transaction['name'],
                'amount': transaction['amount'],
                'balance': current_balance,
                'is_income': transaction['amount'] > 0,
                'is_excluded': transaction.get('is_excluded', False)
            })
            # VIEWカード（通常払いまたはボーナス払い）の引き落とし後の残高を記録
            if transaction.get('is_view_card', False):
                view_card_balance = current_balance

        plan.timeline = timeline
        plan.past_timeline = past_timeline  # 過去の明細を保存
        plan.final_balance = current_balance
        # メイン預金残高を計算（VIEWカード引き落とし後の残高 - 定期預金残高）
        # VIEWカードの引き落としがない場合は月末残高を使用
        base_balance = view_card_balance if view_card_balance is not None else current_balance
        plan.main_balance = base_balance - cumulative_savings if plan.has_savings else base_balance
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
    default_items = MonthlyPlanDefault.objects.filter(is_active=True).order_by('order', 'id')

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
        import logging
        logger = logging.getLogger(__name__)

        # 過去月の場合はPastSalaryFormを使用
        if is_past_month:
            from .forms import PastSalaryForm
            form = PastSalaryForm(request.POST, instance=existing_plan)
        else:
            form = MonthlyPlanForm(request.POST, instance=existing_plan)

        if form.is_valid():
            plan = form.save()

            # マネーアシスト借入がある場合、翌月末に自動で返済を登録
            loan_borrowing = plan.get_item('item_15')  # マネーアシスト借入
            if loan_borrowing > 0:
                current_date = datetime.strptime(plan.year_month, '%Y-%m')
                # 翌月の1日を計算（月末の28日後 + 数日）
                next_month = (current_date.replace(day=1) + timedelta(days=32)).replace(day=1)
                next_month_str = next_month.strftime('%Y-%m')

                # 翌月の計画を取得または作成
                # MonthlyPlanDefaultからデフォルト値を取得
                default_items = MonthlyPlanDefault.objects.filter(is_active=True)
                items_defaults = {}
                for item in default_items:
                    if item.key:
                        items_defaults[item.key] = item.amount or 0

                next_plan, _ = MonthlyPlan.objects.get_or_create(
                    year_month=next_month_str,
                    defaults={'items': items_defaults}
                )

                # 翌月の返済額に借入額を加算
                loan_value = next_plan.get_item('item_14')  # マネーアシスト返済
                next_plan.set_item('item_14', loan_value + loan_borrowing)
                next_plan.save()

            # 成功メッセージを年月付きで作成
            year_month_display = format_year_month_display(plan.year_month)
            if is_past_month:
                success_message = f'{year_month_display}の給与情報を登録しました。'
            else:
                success_message = f'{year_month_display}の月次計画を登録しました。'

            if is_ajax:
                return JsonResponse({'status': 'success', 'message': success_message})
            messages.success(request, success_message)
            # 過去月の場合は給与一覧にリダイレクト
            if is_past_month:
                return redirect('budget_app:salary_list')
            return redirect('budget_app:plan_list')
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
                from .models import MonthlyPlanDefault
                default_items = MonthlyPlanDefault.objects.filter(is_active=True)
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
    from .models import MonthlyPlanDefault
    import json

    default_items = MonthlyPlanDefault.objects.filter(is_active=True).order_by('order', 'id')
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
                default_items = MonthlyPlanDefault.objects.filter(is_active=True)
                for item in default_items:
                    data[item.key] = item.amount or 0
            else:
                # 過去の月の場合は全て0
                default_items = MonthlyPlanDefault.objects.filter(is_active=True)
                for item in default_items:
                    data[item.key] = 0

            return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def plan_data(request, pk):
    """月次計画データをJSON形式で返す（モーダル用）"""
    from django.http import JsonResponse
    plan = get_object_or_404(MonthlyPlan, pk=pk)
    from .models import MonthlyPlanDefault

    # MonthlyPlanDefaultから収入・支出項目を取得
    default_items = MonthlyPlanDefault.objects.filter(is_active=True).order_by('order', 'id')

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
    import logging
    logger = logging.getLogger(__name__)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    # 過去月かどうかを判定
    current_year_month = datetime.now().strftime('%Y-%m')
    is_past_month = plan.year_month < current_year_month

    if request.method == 'POST':
        # 編集前の借入額を保存
        old_loan_borrowing = plan.get_item('item_15')  # マネーアシスト借入

        # デバッグ: POSTデータを確認
        logger.info(f"POST data: bonus_gross_salary={request.POST.get('bonus_gross_salary')}, bonus_deductions={request.POST.get('bonus_deductions')}")

        # チェックボックスの文字列値をbooleanに変換
        post_data = request.POST.copy()
        # MonthlyPlanDefaultからクレカ項目の除外フラグを動的に生成
        from .models import MonthlyPlanDefault
        checkbox_fields = []
        default_items = MonthlyPlanDefault.objects.filter(is_active=True)
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

            # マネーアシスト借入額が変更された場合、翌月の返済額を更新
            new_loan_borrowing = plan.get_item('item_15')  # マネーアシスト借入
            if new_loan_borrowing != old_loan_borrowing:
                current_date = datetime.strptime(plan.year_month, '%Y-%m')
                next_month = (current_date.replace(day=1) + timedelta(days=32)).replace(day=1)
                next_month_str = next_month.strftime('%Y-%m')

                # 翌月の計画を取得または作成
                # MonthlyPlanDefaultからデフォルト値を取得
                default_items = MonthlyPlanDefault.objects.filter(is_active=True)
                items_defaults = {}
                for item in default_items:
                    if item.key:
                        items_defaults[item.key] = item.amount or 0

                next_plan, _ = MonthlyPlan.objects.get_or_create(
                    year_month=next_month_str,
                    defaults={'items': items_defaults}
                )

                # 翌月の返済額を調整（古い借入額を引いて、新しい借入額を加算）
                loan_value = next_plan.get_item('item_14')  # マネーアシスト返済
                next_plan.set_item('item_14', loan_value - old_loan_borrowing + new_loan_borrowing)
                next_plan.save()

            display_month = format_year_month_display(plan.year_month)
            if is_ajax:
                return JsonResponse({'status': 'success', 'message': f'{display_month} の計画を更新しました。'})
            messages.success(request, f'{display_month} の計画を更新しました。')
            # リファラーをチェックして適切なページにリダイレクト
            referer = request.META.get('HTTP_REFERER', '')
            if 'past-transactions' in referer:
                return redirect('budget_app:past_transactions')
            elif 'salaries' in referer:
                return redirect('budget_app:salary_list')
            elif is_past_month:
                return redirect('budget_app:salary_list')
            return redirect('budget_app:plan_list')
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
    from .models import MonthlyPlanDefault
    import json

    default_items = MonthlyPlanDefault.objects.filter(is_active=True).order_by('order', 'id')
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

    # 事前に上書きデータを取得して辞書に格納（金額、カード種別、2回払い）
    overrides = DefaultChargeOverride.objects.all()
    override_map = {(ov.default_id, ov.year_month): {'amount': ov.amount, 'card_type': ov.card_type, 'is_split_payment': ov.is_split_payment} for ov in overrides}
    estimates = list(CreditEstimate.objects.all().order_by('-year_month', 'card_type', 'due_date', 'created_at'))
    credit_defaults = list(CreditDefault.objects.filter(is_active=True))

    # サマリー（年月 -> カード -> {total, entries}）
    # card_id -> タイトル、支払日、オフセット月 のマッピングを MonthlyPlanDefault から取得
    from .models import MonthlyPlanDefault
    card_labels = {}
    card_due_days = {}
    card_offset_months = {}

    for item in MonthlyPlanDefault.objects.filter(is_active=True, card_id__isnull=False):
        if item.card_id:
            card_labels[item.card_id] = item.title
            if item.withdrawal_day:
                card_due_days[item.card_id] = item.withdrawal_day
            # offset_monthsを記録（0=同月、1=翌月、2=翌々月）
            card_offset_months[item.card_id] = item.offset_months if item.offset_months else 0

    # カード名に支払日を追加する関数
    def get_card_label_with_due_day(card_type, is_bonus=False, year_month=None):
        from datetime import date
        import calendar

        base_label = card_labels.get(card_type, card_type)
        due_day = card_due_days.get(card_type, '')
        offset_months = card_offset_months.get(card_type, 0)

        if due_day and year_month:
            # 年月から年と月を取得
            year, month = map(int, year_month.split('-'))

            # ボーナス払いの場合はオフセット0、通常払いはoffset_monthsを使用
            if is_bonus:
                # ボーナス払いはその月に支払い
                months_to_add = 0
            else:
                # MonthlyPlanDefaultのoffset_monthsを使用
                months_to_add = offset_months

            payment_month = month + months_to_add
            payment_year = year
            while payment_month > 12:
                payment_month -= 12
                payment_year += 1

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

    today = datetime.now()

    for est in estimates:
        # 通常払いの場合、締め日が過ぎたら非表示
        if not est.is_bonus_payment:
            year, month = map(int, est.year_month.split('-'))
            from datetime import date
            import calendar

            # 分割払いの2回目の場合は、2回目の引き落とし月から逆算した締め日でチェック
            if est.is_split_payment and est.split_payment_part == 2:
                # billing_monthが設定されている場合はそれを使用
                if est.billing_month:
                    billing_year, billing_month = map(int, est.billing_month.split('-'))
                    # 引き落とし月から利用月を逆算（offset_monthsを使用）
                    offset = card_offset_months.get(est.card_type, 1)
                    usage_month = billing_month - offset
                    usage_year = billing_year
                    while usage_month < 1:
                        usage_month += 12
                        usage_year -= 1
                    year = usage_year
                    month = usage_month

            # MonthlyPlanDefaultから締め日を取得
            card_default = MonthlyPlanDefault.objects.filter(key=est.card_type, is_active=True).first()
            if card_default:
                if card_default.is_end_of_month or not card_default.closing_day:
                    # 月末締め
                    last_day = calendar.monthrange(year, month)[1]
                    closing_date = date(year, month, last_day)
                else:
                    # 指定日締め（翌月の締め日）
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
        card_key = est.card_type
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
            'entries': [],
            'year_month': display_month,  # 表示月（支払月＝billing_month）
            'is_bonus_section': est.is_bonus_payment,  # ボーナス払いかどうか
        })
        card_group['total'] += est.amount
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

    # 定期デフォルトを追加する利用月を決定
    # 既存の引き落とし月から逆算して、対応する利用月を計算
    # {(usage_month, card_id): billing_month} の辞書として保存
    candidate_usage_cards = {}
    current_year_month = f"{today.year}-{today.month:02d}"

    for billing_month in existing_billing_months:
        billing_year, billing_month_num = map(int, billing_month.split('-'))

        # 各カードのoffset_monthsを使って利用月を計算
        for card_id, offset_months in card_offset_months.items():
            usage_month_num = billing_month_num - offset_months
            usage_year = billing_year
            if usage_month_num < 1:
                usage_month_num += 12
                usage_year -= 1
            usage_month = f"{usage_year}-{usage_month_num:02d}"
            # 現在の月以降のみ追加
            if usage_month >= current_year_month:
                candidate_usage_cards[(usage_month, card_id)] = billing_month

    # 利用月のリストを取得してソート（重複削除）
    candidate_usage_months = sorted(list(set(key[0] for key in candidate_usage_cards.keys())))

    # 各年月の各カードに定期デフォルトを追加
    for year_month in candidate_usage_months:
        # 年月から月を取得（奇数月判定用）
        year, month = map(int, year_month.split('-'))
        is_odd_month = (month % 2 == 1)

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
            if default.apply_odd_months_only and not is_odd_month:
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
                    is_split_payment=False  # 初回はデフォルトで分割払いなし
                )
                # override_mapとoverride_dataを更新
                override_data = {
                    'amount': new_override.amount,
                    'card_type': new_override.card_type,
                    'is_split_payment': new_override.is_split_payment
                }
                override_map[(default.id, year_month)] = override_data

            # 実際に使用するカード種別を決定（上書きがあればそれを使用）
            actual_card_type = override_data.get('card_type') if override_data and override_data.get('card_type') else default.card_type

            # このカード×利用月の組み合わせが候補に含まれているかチェック
            if (year_month, actual_card_type) not in candidate_usage_cards:
                continue

            # 分割払いかどうかを確認
            is_split = override_data.get('is_split_payment', False) if override_data else False

            # 引き落とし月を計算（利用月year_monthから）
            from datetime import datetime
            usage_date = datetime.strptime(year_month, '%Y-%m')
            # card_offset_monthsを使用して引き落とし月を計算
            billing_offset = card_offset_months.get(actual_card_type, 1)  # デフォルトは翌月
            billing_month_num = usage_date.month + billing_offset
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
                'entries': [],
                # 反映機能で billing_month が参照される
                'year_month': billing_month,
                'is_bonus_section': False,
            })

            # 疑似的なCreditEstimateオブジェクトを作成
            class DefaultEntry:
                def __init__(self, default_obj, entry_year_month, override_data, actual_card_type, split_part=None, total_amount=None, original_year_month=None):
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
                    self.is_overridden = override_data is not None # 上書きされているかどうかのフラグ
                    self.due_date = None
                    # 上書きデータにis_split_paymentがあればそれを使用、なければFalse
                    self.is_split_payment = override_data.get('is_split_payment', False) if override_data else False
                    self.split_payment_part = split_part  # 1 or 2
                    self.is_bonus_payment = False
                    self.is_default = True  # デフォルトエントリーであることを示すフラグ
                    self.default_id = default_obj.id  # デフォルト項目のID

            # 2回払いの場合は2つのエントリを作成
            is_split = override_data.get('is_split_payment', False) if override_data else False
            if is_split:
                total_amount = override_data.get('amount') if override_data else default.amount

                # 1回目の締め日チェック
                # 1回目の利用月year_monthの締め日が過ぎていなければ表示
                first_payment_closed = False
                card_info = MonthlyPlanDefault.objects.filter(key=actual_card_type, is_active=True).first()
                if card_info and card_info.closing_day and not card_info.is_end_of_month:
                    # 指定日締めの場合（例: 5日締め）
                    first_payment_closed = view_closed
                else:
                    # 月末締めの場合
                    first_payment_closed = other_closed

                # 1回目（利用月のbilling_monthに表示）
                if not first_payment_closed:
                    default_entry_1 = DefaultEntry(default, year_month, override_data, actual_card_type, split_part=1, total_amount=total_amount, original_year_month=year_month)
                    if default_entry_1.amount > 0:
                        card_group['entries'].append(default_entry_1)
                        card_group['total'] += default_entry_1.amount

                # 2回目の引き落とし月を計算（1回目のbilling_month + 1ヶ月）
                billing_date = datetime.strptime(billing_month, '%Y-%m')
                next_billing_date = (billing_date.replace(day=1) + timedelta(days=32)).replace(day=1)
                next_billing_month = next_billing_date.strftime('%Y-%m')

                # 2回目の締め日チェック
                # 2回目の引き落とし月から逆算した利用月の締め日をチェック
                next_billing_year, next_billing_month_num = map(int, next_billing_month.split('-'))

                # 引き落とし月から利用月を逆算（offset_monthsを使用）
                offset = card_offset_months.get(actual_card_type, 1)
                second_usage_month = next_billing_month_num - offset
                second_usage_year = next_billing_year
                while second_usage_month < 1:
                    second_usage_month += 12
                    second_usage_year -= 1

                # 2回目の利用月の締め日を計算
                if card_info:
                    if card_info.is_end_of_month or not card_info.closing_day:
                        # 月末締め
                        second_last_day = calendar.monthrange(second_usage_year, second_usage_month)[1]
                        second_closing_date = date(second_usage_year, second_usage_month, second_last_day)
                    else:
                        # 指定日締め（翌月の締め日）
                        second_closing_month = second_usage_month + 1
                        second_closing_year = second_usage_year
                        if second_closing_month > 12:
                            second_closing_month = 1
                            second_closing_year += 1
                        second_closing_date = date(second_closing_year, second_closing_month, card_info.closing_day)
                else:
                    # デフォルト: 月末締め
                    second_last_day = calendar.monthrange(second_usage_year, second_usage_month)[1]
                    second_closing_date = date(second_usage_year, second_usage_month, second_last_day)

                # 2回目の締め日が過ぎていなければ表示
                if today.date() <= second_closing_date:
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
                        'entries': [],
                        'year_month': next_billing_month,
                        'is_bonus_section': False,
                    })

                    # 2回目のエントリ（利用月は1回目と同じyear_month）
                    default_entry_2 = DefaultEntry(default, year_month, override_data, actual_card_type, split_part=2, total_amount=total_amount, original_year_month=year_month)
                    if default_entry_2.amount > 0:
                        next_card_group['entries'].append(default_entry_2)
                        next_card_group['total'] += default_entry_2.amount
            else:
                # 通常の1回払い
                # 締め日チェック
                payment_closed = False
                # カード情報を取得
                card_info = MonthlyPlanDefault.objects.filter(key=actual_card_type, is_active=True).first()
                if card_info and card_info.closing_day and not card_info.is_end_of_month:
                    # 指定日締めの場合
                    payment_closed = view_closed
                else:
                    # 月末締めの場合
                    payment_closed = other_closed

                # 締め日が過ぎていなければ表示
                if not payment_closed:
                    default_entry = DefaultEntry(default, year_month, override_data, actual_card_type)
                    # 金額が0の場合は追加しない（削除された定期項目）
                    if default_entry.amount > 0:
                        card_group['entries'].append(default_entry)
                        card_group['total'] += default_entry.amount

    # 各カードのエントリーを支払日順にソート（定期デフォルトは最後、日付は降順）
    for year_month, month_group in summary.items():
        for card_type, card_data in month_group.items():
            card_data['entries'].sort(key=lambda x: (
                x.is_default if hasattr(x, 'is_default') else False,  # 定期デフォルトを最後に
                -(x.due_date.toordinal()) if x.due_date else float('-inf'),  # due_dateを降順に（新しい日付が先）
                x.is_bonus_payment if hasattr(x, 'is_bonus_payment') else False,  # 同じ日付なら通常払いを先に
                # 定期デフォルト項目の場合はdefault_idでソート、通常項目はpkでソート（降順）
                -(x.default_id if (hasattr(x, 'is_default') and x.is_default and hasattr(x, 'default_id')) else (x.pk if hasattr(x, 'pk') and x.pk else 0))
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
    today = datetime.now()
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
        for item in MonthlyPlanDefault.objects.filter(is_active=True, closing_day=5):
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
            amount_str = request.POST.get('amount')
            card_type = request.POST.get('card_type')
            is_split_payment = request.POST.get('is_split_payment') == 'on'

            try:
                amount = int(amount_str)
                default_instance = get_object_or_404(CreditDefault, pk=default_id)

                # 上書きオブジェクトを取得または作成
                defaults_dict = {'amount': amount}
                # カード種別は常に保存する（上書きで管理）
                if card_type:
                    defaults_dict['card_type'] = card_type
                # 2回払いフラグを保存
                defaults_dict['is_split_payment'] = is_split_payment

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

        elif action == 'reflect_card':
            year_month = request.POST.get('year_month')
            card_id = request.POST.get('card_type')  # 実際には card_id
            is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

            print(f"DEBUG REFLECT: card_id received = {card_id}")  # デバッグ用

            # card_idからボーナス払いフラグを判定
            is_bonus = card_id.endswith('_bonus')
            if is_bonus:
                actual_card_id = card_id.replace('_bonus', '')
            else:
                actual_card_id = card_id

            print(f"DEBUG REFLECT: is_bonus = {is_bonus}, actual_card_id = {actual_card_id}")  # デバッグ用

            # card_idからMonthlyPlanDefaultのkeyを取得
            # ボーナス払いの場合は is_bonus_payment=True の項目を検索（例: item_6 → item_7）
            from .models import MonthlyPlanDefault
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
                print(f"DEBUG REFLECT: Found monthly_plan_key = {monthly_plan_key}")  # デバッグ用
            except MonthlyPlanDefault.DoesNotExist:
                bonus_text = "ボーナス払い" if is_bonus else "通常払い"
                error_message = f'カードID {actual_card_id} の{bonus_text}に対応する月次計画項目が見つかりません。'
                if is_ajax:
                    return JsonResponse({'status': 'error', 'message': error_message}, status=400)
                else:
                    messages.error(request, error_message)
                    return redirect('budget_app:credit_estimates')

            # サマリーからカードデータを取得（キーはcard_idのまま）
            if year_month in summary and card_id in summary[year_month]:
                card_data = summary[year_month][card_id]
                total_amount = card_data['total']
                card_label = card_data['label']

                # 反映先の年月を計算
                # クレカ見積もりページでは、通常払いもボーナス払いも
                # 既に支払月（billing_month）で表示されているため、そのまま使用
                target_year_month = year_month

                # 月次計画を取得または作成
                plan, _ = MonthlyPlan.objects.get_or_create(year_month=target_year_month)

                # set_itemメソッドを使用（items JSONFieldに保存）
                plan.set_item(monthly_plan_key, total_amount)
                plan.save()

                success_message = f'{format_year_month_display(year_month)}の「{card_label}」を{format_year_month_display(target_year_month)}の月次計画に反映しました（{total_amount:,}円）'

                if is_ajax:
                    # 月次計画ページへのURLを生成（アンカー付き）
                    target_url = reverse('budget_app:index') + f'#plan-{plan.pk}'
                    return JsonResponse({
                        'status': 'success',
                        'message': success_message,
                        'target_year_month': target_year_month,
                        'target_url': target_url
                    })
                else:
                    messages.success(request, success_message)
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

                            # MonthlyPlanDefaultからoffset_monthsを取得
                            card_item = MonthlyPlanDefault.objects.filter(key=card_type, is_active=True).first()
                            offset = card_item.offset_months if card_item and card_item.offset_months else 1

                            payment_month = use_month + offset
                            payment_year = use_year
                            while payment_month > 12:
                                payment_month -= 12
                                payment_year += 1
                            target_year_month = f"{payment_year}-{payment_month:02d}"

                            # レガシー処理（互換性のため残しておく）
                            if not card_item:
                                payment_month = use_month + 1
                                payment_year = use_year
                                if payment_month > 12:
                                    payment_month -= 12
                                    payment_year += 1
                                target_year_month = f"{payment_year}-{payment_month:02d}"                            

                        # 月次計画を取得または作成
                        # MonthlyPlanDefaultからデフォルト値を取得
                        default_items = MonthlyPlanDefault.objects.filter(is_active=True)
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
    
    # GETリクエストの場合、またはPOSTでエラーがあり再表示する場合のフォームを定義
    # このスコープで定義することで、POST処理後に変数が未定義になることを防ぐ
    initial_data = {'year': timezone.now().year, 'month': f"{timezone.now().month:02d}"}
    if 'form' not in locals():
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
            # フォームのsave()メソッドで分割払いとボーナス払いの処理を含めて保存
            form.save()

            if is_ajax:
                return JsonResponse({'status': 'success', 'message': 'クレカ見積りを更新しました。'})
            messages.success(request, 'クレカ見積りを更新しました。')
            # リファラーをチェックして適切なページにリダイレクト
            referer = request.META.get('HTTP_REFERER', '')
            if 'past-transactions' in referer:
                return redirect('budget_app:past_transactions')
            return redirect('budget_app:credit_estimates')
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

            if is_ajax:
                return JsonResponse({'status': 'success', 'message': message})
            else:
                messages.success(request, message)
                # リファラーをチェックして適切なページにリダイレクト
                referer = request.META.get('HTTP_REFERER', '')
                if 'past-transactions' in referer:
                    return redirect('budget_app:past_transactions')
                return redirect('budget_app:credit_estimates')

        except Exception as e:
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': f'削除中にエラーが発生しました: {str(e)}'}, status=500)
            else:
                messages.error(request, f'削除中にエラーが発生しました: {str(e)}')
                referer = request.META.get('HTTP_REFERER', '')
                if 'past-transactions' in referer:
                    return redirect('budget_app:past_transactions')
                return redirect('budget_app:credit_estimates')

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
            print(f"DEBUG UPDATE: Received card_type = {request.POST.get('card_type')}")  # デバッグ用
            form = CreditDefaultForm(request.POST, instance=instance)
            print(f"DEBUG UPDATE: Form card_type choices = {form.fields['card_type'].choices}")  # デバッグ用
            if form.is_valid():
                instance = form.save()
                if is_ajax:
                    # Get card type display name from MonthlyPlanDefault
                    card_type_display = instance.card_type
                    if instance.card_type:
                        card_item = MonthlyPlanDefault.objects.filter(key=instance.card_type).first()
                        if card_item:
                            card_type_display = card_item.title

                    return JsonResponse({
                        'status': 'success',
                        'message': f'{instance.label} を更新しました。',
                        'default': {
                            'id': instance.id,
                            'label': instance.label,
                            'card_type': instance.card_type,
                            'card_type_display': card_type_display,
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

    # カード種別の選択肢を取得（MonthlyPlanDefaultから）
    # card_idが設定されているものをクレジットカード項目とみなす
    card_choices = MonthlyPlanDefault.objects.filter(
        is_active=True,
        card_id__isnull=False
    ).exclude(card_id='').exclude(is_bonus_payment=True).order_by('order', 'id').values('key', 'title')

    print(f"DEBUG: card_choices count = {card_choices.count()}")  # デバッグ用
    for choice in card_choices:
        print(f"  - {choice['key']}: {choice['title']}")  # デバッグ用

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
    defaults = MonthlyPlanDefault.objects.filter(is_active=True).order_by('order', 'id')

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
            form = MonthlyPlanDefaultForm(request.POST, instance=instance)
            if form.is_valid():
                instance = form.save(commit=False)
                # orderを復元（フォームに含まれていないため）
                instance.order = current_order
                instance.save()
                if is_ajax:
                    return JsonResponse({
                        'status': 'success',
                        'message': f'{instance.title} を更新しました。',
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
                messages.success(request, f'{instance.title} を更新しました。')
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

        messages.success(request, f'{year}年{int(month)}月の給与明細を登録しました。')
        return JsonResponse({'status': 'success'})

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'給与明細の登録に失敗しました: {str(e)}'
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

        messages.success(request, f'{salary.year_month}の給与明細を更新しました。')
        return JsonResponse({'status': 'success'})

    except Salary.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': '給与明細が見つかりません。'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'給与明細の更新に失敗しました: {str(e)}'
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

        messages.success(request, f'{salary.year_month}のボーナス明細を更新しました。')
        return JsonResponse({'status': 'success'})

    except Salary.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': '給与明細が見つかりません。'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'ボーナス明細の更新に失敗しました: {str(e)}'
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
        return JsonResponse({
            'status': 'error',
            'message': f'給与明細の削除に失敗しました: {str(e)}'
        }, status=500)


def past_transactions_list(request):
    """過去の明細一覧（アーカイブ）"""
    from datetime import datetime, date as dt_date
    import calendar

    current_date = datetime.now().date()
    current_year_month = datetime.now().strftime('%Y-%m')

    # 過去のMonthlyPlanを取得（当月より前、年月で降順ソート）
    past_plans_qs = MonthlyPlan.objects.filter(
        year_month__lt=current_year_month
    ).order_by('-year_month')

    # 当月のプランで今日以降の明細がないものも含める
    current_month_plan = MonthlyPlan.objects.filter(year_month=current_year_month).first()
    past_plans = list(past_plans_qs)

    if current_month_plan:
        # 当月のタイムラインを計算して、今日以降の明細があるかチェック
        from .models import MonthlyPlanDefault

        # タイムラインを生成（plan_listと同じロジック）
        timeline = []
        default_items = MonthlyPlanDefault.objects.filter(is_active=True).order_by('order', 'id')

        for item in default_items:
            if not item.should_display_for_month(current_month_plan.year_month):
                continue

            value = current_month_plan.get_item(item.key)
            if value and value != 0:
                # 引き落とし日/振込日を計算
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
            past_plans.insert(0, current_month_plan)  # 先頭に追加（降順なので）

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

                card_plan = MonthlyPlanDefault.objects.filter(key=est.card_type, is_active=True).first()
                if card_plan:
                    if card_plan.is_end_of_month or not card_plan.closing_day:
                        # 月末締め
                        last_day = calendar.monthrange(year, month)[1]
                        closing_date = dt_date(year, month, last_day)
                    else:
                        # 指定日締め（翌月の締め日）
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
                    past_credit_estimates.append(est)

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

            # 引き落とし日/振込日を計算
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
            card_plan = MonthlyPlanDefault.objects.filter(key=estimate.card_type, is_active=True).first()
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
            card_item = MonthlyPlanDefault.objects.filter(key=estimate.card_type).first()
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
                'estimates': []
            }

        yearly_data[year]['credit_months'][billing_month]['cards'][card_name]['estimates'].append({
            'card_type': estimate.card_type,
            'amount': estimate.amount,
            'memo': estimate.description,
            'estimate': estimate
        })
        yearly_data[year]['credit_months'][billing_month]['total_amount'] += estimate.amount
        yearly_data[year]['total_credit'] += estimate.amount

    # クレカ見積りの月別データをリストに変換してソート
    # billing_month（引き落とし月）でソート
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
                # 各カードの明細を引落日順にソート（年月日全体で）
                def get_sort_key(est):
                    due = est['estimate'].due_date
                    is_bonus = est['estimate'].is_bonus_payment
                    if due is None:
                        # due_dateがない場合は最後に表示
                        return (dt_date.max, False, est['estimate'].id)
                    else:
                        # due_date、is_bonus_payment（通常払いを先に）、idの順でソート
                        return (due, is_bonus, est['estimate'].id)

                card_data['estimates'] = sorted(card_data['estimates'], key=get_sort_key)
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
    default_items = MonthlyPlanDefault.objects.filter(is_active=True).order_by('order', 'id')

    # ハードコードされたフィールド（既存のテンプレートとの互換性のため）
    # 古いフィールド名と新しいkey名の両方を含める
    # 動的フィールド（MonthlyPlanDefaultから取得）
    hardcoded_fields = [item.key for item in default_items if item.key]

    context = {
        'yearly_data': filtered_yearly_data,
        'sorted_years': sorted_years,
        'default_items': default_items,
        'hardcoded_fields': hardcoded_fields,
    }
    return render(request, 'budget_app/past_transactions.html', context)
