from django import forms
from datetime import datetime, timedelta
import calendar
from .models import SimulationConfig, MonthlyPlan, CreditEstimate, CreditDefault, MonthlyPlanDefault


def get_bonus_month_from_date(purchase_date) -> str:
    """利用日からボーナス払い請求月を計算
    対象期間:
    - 12/6〜6/5の購入 → 8/4請求（同年または翌年の8月）
    - 7/6〜11/5の購入 → 1/4請求（翌年の1月）

    対象外期間:
    - 6/6〜7/5（ボーナス払い不可）
    - 11/6〜12/5（ボーナス払い不可）
    """
    from datetime import date

    if isinstance(purchase_date, str):
        from datetime import datetime
        purchase_date = datetime.strptime(purchase_date, '%Y-%m-%d').date()

    if not isinstance(purchase_date, date):
        return None

    year = purchase_date.year
    month = purchase_date.month
    day = purchase_date.day

    # 対象外期間のチェック
    # 6/6〜7/5は対象外
    if month == 6 and day >= 6:
        return None
    if month == 7 and day <= 5:
        return None

    # 11/6〜12/5は対象外
    if month == 11 and day >= 6:
        return None
    if month == 12 and day <= 5:
        return None

    # 対象期間の処理
    # 12/6〜6/5 → 8月請求
    if month == 12 and day >= 6:
        # 12/6〜12/31 → 翌年8月
        return f"{year + 1}-08"
    elif 1 <= month <= 5:
        # 1/1〜5/31 → 同年8月
        return f"{year}-08"
    elif month == 6 and day <= 5:
        # 6/1〜6/5 → 同年8月
        return f"{year}-08"

    # 7/6〜11/5 → 翌年1月請求
    elif month == 7 and day >= 6:
        # 7/6〜7/31 → 翌年1月
        return f"{year + 1}-01"
    elif 8 <= month <= 10:
        # 8/1〜10/31 → 翌年1月
        return f"{year + 1}-01"
    elif month == 11 and day <= 5:
        # 11/1〜11/5 → 翌年1月
        return f"{year + 1}-01"

    return None


def get_bonus_due_date_from_purchase(purchase_date):
    """利用日からボーナス払いの支払日（due_date）を計算
    - 12/6〜6/5の購入 → 8/4支払い
    - 7/6〜11/5の購入 → 1/4支払い
    """
    from datetime import date

    if isinstance(purchase_date, str):
        from datetime import datetime
        purchase_date = datetime.strptime(purchase_date, '%Y-%m-%d').date()

    if not isinstance(purchase_date, date):
        return None

    year = purchase_date.year
    month = purchase_date.month
    day = purchase_date.day

    # 対象外期間のチェック
    if month == 6 and day >= 6:
        return None
    if month == 7 and day <= 5:
        return None
    if month == 11 and day >= 6:
        return None
    if month == 12 and day <= 5:
        return None

    # 12/6〜6/5 → 8/4支払い
    if month == 12 and day >= 6:
        return date(year + 1, 8, 4)
    elif 1 <= month <= 5:
        return date(year, 8, 4)
    elif month == 6 and day <= 5:
        return date(year, 8, 4)

    # 7/6〜11/5 → 1/4支払い
    elif month == 7 and day >= 6:
        return date(year + 1, 1, 4)
    elif 8 <= month <= 10:
        return date(year + 1, 1, 4)
    elif month == 11 and day <= 5:
        return date(year + 1, 1, 4)

    return None


def get_next_bonus_month(year_month: str) -> str:
    """指定された購入月から請求月を返す
    - 12/6〜6/5の購入 → 8/4請求（同年または翌年の8月）
    - 7/6〜11/5の購入 → 1/4請求（翌年の1月）

    ※編集モーダルで入力される年月は「購入月」を想定
    """
    try:
        year, month = map(int, year_month.split('-'))
    except (ValueError, AttributeError):
        return year_month

    # 12/6〜6/5の購入 → 8月請求
    if month == 12 or 1 <= month <= 5:
        # 12月の購入は翌年8月、1-5月の購入は同年8月
        if month == 12:
            return f"{year + 1}-08"
        else:
            return f"{year}-08"
    # 6月の購入 → 同年8月請求
    elif month == 6:
        return f"{year}-08"
    # 7月〜11月の購入 → 翌年1月請求
    else:  # 7 <= month <= 11
        return f"{year + 1}-01"


class SimulationConfigForm(forms.ModelForm):
    """シミュレーション設定フォーム"""
    savings_year = forms.ChoiceField(
        label='定期預金開始年',
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full p-2 border rounded'
        })
    )
    savings_month = forms.ChoiceField(
        label='定期預金開始月',
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full p-2 border rounded'
        })
    )

    class Meta:
        model = SimulationConfig
        fields = [
            'savings_enabled',
            'savings_amount',
            'savings_start_month',
        ]
        widgets = {
            'savings_enabled': forms.CheckboxInput(attrs={
                'class': 'rounded',
                'id': 'savings_enabled_checkbox'
            }),
            'savings_amount': forms.NumberInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': '例: 50000',
                'id': 'savings_amount_field',
                'min': 0
            }),
            'savings_start_month': forms.HiddenInput(),
        }
        labels = {
            'savings_amount': '定期預金額（円）',
            'savings_start_month': '定期預金開始月',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 年の選択肢を生成（現在の年から前後3年）
        current_year = datetime.now().year
        year_choices = [(str(year), str(year)) for year in range(current_year - 3, current_year + 4)]
        self.fields['savings_year'].choices = [('', '選択してください')] + year_choices
        
        # 月の選択肢を生成
        month_choices = [
            ('01', '1月'), ('02', '2月'), ('03', '3月'), ('04', '4月'),
            ('05', '5月'), ('06', '6月'), ('07', '7月'), ('08', '8月'),
            ('09', '9月'), ('10', '10月'), ('11', '11月'), ('12', '12月')
        ]
        self.fields['savings_month'].choices = [('', '選択してください')] + month_choices
        
        # 既存のインスタンスがある場合、年と月を設定
        if self.instance and self.instance.pk and self.instance.savings_start_month:
            try:
                year, month = self.instance.savings_start_month.split('-')
                self.fields['savings_year'].initial = year
                self.fields['savings_month'].initial = month
            except (ValueError, AttributeError):
                pass

    def clean(self):
        cleaned_data = super().clean()
        savings_year = cleaned_data.get('savings_year')
        savings_month = cleaned_data.get('savings_month')
        savings_enabled = cleaned_data.get('savings_enabled')

        # 定期預金が有効な場合のみ、年月の入力をチェック
        if savings_enabled:
            if savings_year and savings_month:
                cleaned_data['savings_start_month'] = f"{savings_year}-{savings_month}"
            elif savings_year or savings_month:
                # 片方だけ選択されている場合はエラー
                if not savings_year:
                    self.add_error('savings_year', '定期預金開始年を選択してください')
                if not savings_month:
                    self.add_error('savings_month', '定期預金開始月を選択してください')
            else:
                # 両方とも選択されていない場合はNone
                cleaned_data['savings_start_month'] = None
        else:
            # 定期預金が無効な場合は、年月の入力は不要
            cleaned_data['savings_start_month'] = None

        return cleaned_data


class MonthlyPlanForm(forms.Form):
    """月次計画フォーム（完全動的フィールド生成）"""
    year = forms.ChoiceField(
        label='年',
        required=False,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded'})
    )
    month = forms.ChoiceField(
        label='月',
        required=False,
        widget=forms.Select(attrs={'class': 'w-full p-2 border rounded'})
    )
    year_month = forms.CharField(widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

        from .models import MonthlyPlanDefault

        # MonthlyPlanDefaultから動的にフィールドを生成
        default_items = MonthlyPlanDefault.objects.filter(is_active=True).order_by('order', 'id')

        # 給与明細の固定フィールドを追加
        detail_fields = {
            'gross_salary': '総支給額',
            'deductions': '控除額',
            'transportation': '交通費',
            'bonus_gross_salary': 'ボーナス総支給額',
            'bonus_deductions': 'ボーナス控除額',
        }

        for field_name, label in detail_fields.items():
            self.fields[field_name] = forms.IntegerField(
                label=label,
                required=False,
                initial=0,
                widget=forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'placeholder': '0'})
            )

        # MonthlyPlanDefaultから動的フィールドを生成（keyを使用）
        for item in default_items:
            # keyをフィールド名として使用
            field_name = item.key
            if not field_name:
                continue

            # ラベルを生成（編集時は最新のtitleを反映）
            # 引落日をラベルに含める
            withdrawal_day_str = ''
            if item.is_withdrawal_end_of_month:
                withdrawal_day_str = '（末日）'
            elif item.withdrawal_day:
                withdrawal_day_str = f'（{item.withdrawal_day}日）'

            label = f'{item.title}{withdrawal_day_str}'

            # 金額フィールドを追加
            # 編集時はitemsから取得、新規作成時はデフォルト値を使用
            if self.instance and self.instance.pk:
                # 編集時: itemsに値がある場合はその値、ない場合は0（デフォルト値は使わない）
                initial_value = self.instance.items.get(field_name, 0) if isinstance(self.instance.items, dict) else 0
            else:
                # 新規作成時: デフォルト値を使用
                initial_value = item.amount

            self.fields[field_name] = forms.IntegerField(
                label=label,
                required=False,
                initial=initial_value,
                widget=forms.NumberInput(attrs={'class': 'w-full p-2 border rounded', 'placeholder': '0'})
            )

            # クレカ項目の場合、繰上げ返済チェックボックスを追加
            if item.is_credit_card():
                exclude_field = f'exclude_{field_name}'
                self.fields[exclude_field] = forms.BooleanField(
                    label='繰上げ返済',
                    required=False,
                    initial=self.instance.get_exclusion(field_name) if self.instance else False,
                    widget=forms.CheckboxInput(attrs={'class': 'rounded'})
                )

        # 年の選択肢を生成
        current_year = datetime.now().year
        if self.instance and self.instance.pk:
            year_choices = [(str(year), str(year)) for year in range(current_year - 3, current_year + 4)]
        else:
            year_choices = [(str(year), str(year)) for year in range(current_year, current_year + 4)]
        self.fields['year'].choices = year_choices

        # 月の選択肢を生成
        month_choices = [
            ('01', '1月'), ('02', '2月'), ('03', '3月'), ('04', '4月'),
            ('05', '5月'), ('06', '6月'), ('07', '7月'), ('08', '8月'),
            ('09', '9月'), ('10', '10月'), ('11', '11月'), ('12', '12月')
        ]
        self.fields['month'].choices = month_choices

        # 編集時は年月フィールドを削除
        if self.instance and self.instance.pk and self.instance.year_month:
            if 'year' in self.fields:
                del self.fields['year']
            if 'month' in self.fields:
                del self.fields['month']
            # 既存データをフォームに設定
            self.initial['year_month'] = self.instance.year_month

    def save(self, commit=True):
        """フォームデータをMonthlyPlanインスタンスに保存"""
        from .models import MonthlyPlan, MonthlyPlanDefault

        if self.instance and self.instance.pk:
            plan = self.instance
        else:
            plan = MonthlyPlan(year_month=self.cleaned_data['year_month'])

        # 給与明細の固定フィールドを保存
        for field_name in ['gross_salary', 'deductions', 'transportation',
                          'bonus_gross_salary', 'bonus_deductions']:
            value = self.cleaned_data.get(field_name)
            # Noneや空文字列の場合のみ0にする（0自体は有効な値として扱う）
            if value is None or value == '':
                value = 0
            plan.set_item(field_name, value)

        # MonthlyPlanDefaultから動的フィールドを保存（keyベース）
        default_items = MonthlyPlanDefault.objects.filter(is_active=True)
        for item in default_items:
            field_name = item.key
            if not field_name:
                continue

            # フォームに含まれている場合のみ更新（含まれていない場合は既存値を保持）
            if field_name in self.cleaned_data:
                value = self.cleaned_data.get(field_name)
                # Noneや空文字列の場合のみ0にする（0自体は有効な値として扱う）
                if value is None or value == '':
                    value = 0
                plan.set_item(field_name, value)

            # 繰上げ返済フラグを保存
            exclude_field = f'exclude_{field_name}'
            if exclude_field in self.cleaned_data:
                plan.set_exclusion(field_name, self.cleaned_data.get(exclude_field, False))

        if commit:
            plan.save()

        return plan

    def clean(self):
        cleaned_data = super().clean()
        year = cleaned_data.get('year')
        month = cleaned_data.get('month')
        year_month = cleaned_data.get('year_month')

        # year_monthが既に設定されている場合（インライン編集時）はそのまま使用
        # 設定されていない場合（新規作成時）はyearとmonthから生成
        if not year_month:
            if year and month:
                cleaned_data['year_month'] = f"{year}-{month}"
            else:
                raise forms.ValidationError('年と月を選択してください。')

        # 新規作成時のみ、今月以降の月次計画のみ許可（編集時は制限しない）
        if not (self.instance and self.instance.pk):
            current_year_month = datetime.now().strftime('%Y-%m')
            selected_year_month = cleaned_data.get('year_month')
            if selected_year_month and selected_year_month < current_year_month:
                raise forms.ValidationError('今月以降の月次計画のみ作成できます。過去の給与情報は「過去の給与新規作成」から登録してください。')

        # 数値フィールドの空白を0に変換（データベースのNOT NULL制約対策）
        # フォームに存在するフィールドのみ処理
        numeric_fields = [
            'salary', 'bonus', 'gross_salary', 'deductions', 'transportation',
            'bonus_gross_salary', 'bonus_deductions'
        ]

        # MonthlyPlanDefaultから動的にフィールドを追加
        from .models import MonthlyPlanDefault
        for default_item in MonthlyPlanDefault.objects.filter(is_active=True):
            numeric_fields.append(default_item.key)

        for field_name in numeric_fields:
            # フォームに存在し、かつ空の場合のみ0に変換
            if field_name in self.fields and field_name in cleaned_data:
                value = cleaned_data[field_name]
                if value is None or value == '':
                    cleaned_data[field_name] = 0

        return cleaned_data


class CreditEstimateForm(forms.ModelForm):
    """クレカ見積りフォーム"""

    class Meta:
        model = CreditEstimate
        fields = ['card_type', 'description', 'amount', 'purchase_date', 'is_split_payment', 'is_bonus_payment']
        widgets = {
            'card_type': forms.RadioSelect(attrs={
                'class': 'card-type-radio',
            }),
            'description': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': '例: 旅行、家電などのメモ',
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': '例: 30000',
                'min': 0,
            }),
            'purchase_date': forms.DateInput(attrs={
                'class': 'w-full p-2 border rounded',
                'type': 'date',
            }),
            'is_split_payment': forms.CheckboxInput(attrs={
                'class': 'rounded',
            }),
            'is_bonus_payment': forms.CheckboxInput(attrs={
                'class': 'rounded',
            }),
        }
        labels = {
            'card_type': 'カード種別',
            'description': 'メモ（任意）',
            'amount': '見積額（円）',
            'purchase_date': '利用日',
            'is_split_payment': '分割2回払い',
            'is_bonus_payment': 'ボーナス払い',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # カード選択肢を動的に生成
        from .models import CreditEstimate
        self.fields['card_type'].widget.choices = CreditEstimate.get_card_choices()

        # 編集モーダルで使われるIDを設定
        self.fields['card_type'].widget.attrs.update({'id': 'edit_card_type'})

        # card_typeフィールドから空の選択肢を削除
        self.fields['card_type'].required = True
        # choicesを明示的に設定して空の選択肢を除外
        self.fields['card_type'].choices = CreditEstimate.CARD_TYPES

        # purchase_dateを必須にする
        self.fields['purchase_date'].required = True

        # ドル入力時はamountが空でも通るようにする（ビューでUSD→JPY変換して設定する）
        self.fields['amount'].required = False

        # カード種別のデフォルトをVIEWカードに設定
        if not self.instance.pk:
            self.fields['card_type'].initial = 'item_6'
            # 新規作成時は利用日のデフォルトを本日に設定
            from datetime import date
            self.fields['purchase_date'].initial = date.today()
        else:
            # 編集時: 分割払いの場合は合計金額を表示
            if self.instance.is_split_payment and self.instance.split_payment_group:
                from django.db import models
                # 同じグループの全エントリーの合計金額を計算
                total_amount = CreditEstimate.objects.filter(
                    split_payment_group=self.instance.split_payment_group
                ).aggregate(total=models.Sum('amount'))['total'] or 0
                self.fields['amount'].initial = total_amount

    def clean(self):
        cleaned_data = super().clean()

        # ドル入力でない場合は金額が必須
        amount = cleaned_data.get('amount')
        is_usd = self.data.get('is_usd') == 'on'
        if not is_usd and not amount and amount != 0:
            self.add_error('amount', 'このフィールドは必須です。')

        # 分割払いとボーナス払いが同時に選択されていないかチェック
        is_split_payment = cleaned_data.get('is_split_payment')
        is_bonus_payment = cleaned_data.get('is_bonus_payment')
        card_type = cleaned_data.get('card_type')

        if is_split_payment and is_bonus_payment:
            raise forms.ValidationError('分割払いとボーナス払いは同時に選択できません。')

        # 分割払いまたはボーナス払いの場合、VIEWカードのみ使用可能
        if (is_split_payment or is_bonus_payment) and card_type != 'item_6':
            raise forms.ValidationError('分割払いとボーナス払いはVIEWカードでのみ利用できます。')

        # ボーナス払いの場合、利用日が有効な期間かチェック
        due_date = cleaned_data.get('due_date')
        purchase_date = cleaned_data.get('purchase_date')

        if is_bonus_payment:
            # purchase_dateが設定されている場合はそれを使用、なければdue_dateを使用
            check_date = purchase_date if purchase_date else due_date

            if check_date:
                # 対象外期間をチェック
                month = check_date.month
                day = check_date.day

                invalid_period = False
                if month == 6 and day >= 6:
                    invalid_period = True
                elif month == 7 and day <= 5:
                    invalid_period = True
                elif month == 11 and day >= 6:
                    invalid_period = True
                elif month == 12 and day <= 5:
                    invalid_period = True

                if invalid_period:
                    # purchase_dateがある場合はそちらにエラーを表示
                    error_field = 'purchase_date' if purchase_date else 'due_date'
                    self.add_error(error_field, 'ボーナス払いの対象外期間です。対象期間: 12/6〜6/5 (8/4支払) または 6/6〜11/5 (1/4支払)')
            else:
                # ボーナス払いなのに日付が設定されていない場合
                self.add_error('purchase_date', 'ボーナス払いの場合は利用日を入力してください。')

        return cleaned_data

    def save(self, commit=True):
        from datetime import datetime, timedelta
        from .models import CreditEstimate

        instance = super().save(commit=False)

        # purchase_dateからyear_monthとbilling_monthを計算
        if instance.purchase_date:
            # year_monthは利用日の年月
            instance.year_month = instance.purchase_date.strftime('%Y-%m')

            # billing_monthを計算
            from .models import MonthlyPlanDefault
            card_default = MonthlyPlanDefault.objects.filter(key=instance.card_type, is_active=True).first()

            if card_default:
                # 締め日を取得
                if card_default.is_end_of_month:
                    closing_day = 31
                elif card_default.closing_day:
                    closing_day = card_default.closing_day
                else:
                    # クレジットカードでない場合は締め日がないので、offsetをそのまま使用
                    closing_day = None

                # 締め日から支払い月を計算（offset_monthsは廃止）
                if closing_day:
                    if card_default.is_end_of_month:
                        # 月末締めの場合：締め期間は当月1日〜月末
                        # 例: 1/1利用 → 1/31締め → year_month=2026-01, billing_month=2026-02
                        closing_month = instance.purchase_date.month
                        closing_year = instance.purchase_date.year

                        # year_month = 利用日の月（締め期間は当月1日〜月末）
                        instance.year_month = f"{closing_year}-{closing_month:02d}"

                        # billing_month = 利用日の月 + 1
                        billing_month = closing_month + 1
                        billing_year = closing_year
                        if billing_month > 12:
                            billing_month = 1
                            billing_year += 1
                    else:
                        # 指定日締めの場合：締め期間は前月(締め日+1)〜当月締め日
                        # 利用日が締め日以内なら当月締め、締め日を超えたら翌月締め
                        if instance.purchase_date.day <= closing_day:
                            # 当月締め（例: 1/5利用 → 1/5締め）
                            closing_month = instance.purchase_date.month
                            closing_year = instance.purchase_date.year
                        else:
                            # 翌月締め（例: 1/7利用 → 2/5締め）
                            closing_month = instance.purchase_date.month + 1
                            closing_year = instance.purchase_date.year
                            if closing_month > 12:
                                closing_month = 1
                                closing_year += 1

                        # year_month = 締め日の前月（締め期間の識別子）
                        # 例: 1/5締め → year_month=2025-12（12/6〜1/5の期間を12月として扱う）
                        usage_month = closing_month - 1
                        usage_year = closing_year
                        if usage_month < 1:
                            usage_month = 12
                            usage_year -= 1
                        instance.year_month = f"{usage_year}-{usage_month:02d}"

                        # billing_month = 締め日の翌月（支払い日はwithdrawal_day日）
                        # 例: 1/5締め → billing_month=2026-02（2/4払い）
                        billing_month = closing_month + 1
                        billing_year = closing_year
                        if billing_month > 12:
                            billing_month = 1
                            billing_year += 1
                else:
                    # 締め日がない場合は利用日の月をそのまま使用
                    instance.year_month = instance.purchase_date.strftime('%Y-%m')
                    billing_month = instance.purchase_date.month + 1
                    billing_year = instance.purchase_date.year
                    if billing_month > 12:
                        billing_month = 1
                        billing_year += 1
            else:
                # デフォルト値（情報がない場合は翌月）
                billing_month = instance.purchase_date.month + 1
                billing_year = instance.purchase_date.year
                if billing_month > 12:
                    billing_month = 1
                    billing_year += 1

            instance.billing_month = f"{billing_year}-{billing_month:02d}"

        # 引き落とし月を計算
        def calculate_billing_month(usage_month, card_type, split_part=None):
            """利用月から引き落とし月を計算

            締め日ロジックに基づいて計算:
            - 月末締め: year_month = 利用月 → billing_month = 利用月 + 1
            - 指定日締め: year_month = 締め日の前月 → billing_month = 締め日の翌月 = year_month + 2
            - 分割2回目: billing_month + 1
            """
            from .models import MonthlyPlanDefault
            from calendar import monthrange

            year, month = map(int, usage_month.split('-'))

            # MonthlyPlanDefaultからカード情報を取得
            card_default = MonthlyPlanDefault.objects.filter(key=card_type, is_active=True).first()

            if card_default:
                if card_default.is_end_of_month:
                    # 月末締めの場合：year_month = 利用月 → billing_month = 利用月 + 1
                    billing_month = month + 1
                    billing_year = year
                else:
                    # 指定日締めの場合：year_month = 締め日の前月 → billing_month = year_month + 2
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

        # ボーナス払いの場合、年月を調整
        if instance.is_bonus_payment:
            # purchase_dateからyear_month（利用月）とdue_date（支払日）を設定
            if instance.purchase_date:
                # year_monthは利用月（購入月）
                instance.year_month = instance.purchase_date.strftime('%Y-%m')
                # 実際の支払日(due_date)を計算
                calculated_due_date = get_bonus_due_date_from_purchase(instance.purchase_date)
                if calculated_due_date:
                    instance.due_date = calculated_due_date
                    # ボーナス払いのbilling_monthは支払月（due_dateの月）
                    instance.billing_month = calculated_due_date.strftime('%Y-%m')
            else:
                # purchase_dateがない場合は、year_monthから計算
                instance.year_month = get_next_bonus_month(instance.year_month)
                # billing_monthもyear_monthと同じにする
                instance.billing_month = instance.year_month
        else:
            # ボーナス払いから通常払いに変更された場合
            if instance.pk:
                try:
                    original = CreditEstimate.objects.get(pk=instance.pk)
                    if original.is_bonus_payment:
                        # purchase_dateをdue_dateにコピー（利用日として扱う）
                        if original.purchase_date:
                            instance.due_date = original.purchase_date
                        # purchase_dateをクリア
                        instance.purchase_date = None
                except CreditEstimate.DoesNotExist:
                    pass

        # 既に分割済みのエントリーかチェック（split_payment_partが設定されているか）
        is_already_split = instance.split_payment_part is not None

        # 分割払いが選択されている場合
        if instance.is_split_payment:
            if not is_already_split:
                # 新規分割払い：2つのエントリーに分割
                import uuid
                total_amount = instance.amount

                # 2回目の金額を10の位まで0にする（100で切り捨て）
                second_payment = (total_amount // 2) // 100 * 100
                first_payment = total_amount - second_payment

                # 分割グループIDを生成
                group_id = str(uuid.uuid4())

                # 当月のインスタンス（1回目）を更新
                instance.amount = first_payment
                instance.split_payment_part = 1
                instance.split_payment_group = group_id

                # ボーナス払いの場合はbilling_monthを設定済み、通常払いは計算
                if not instance.is_bonus_payment:
                    instance.billing_month = calculate_billing_month(instance.year_month, instance.card_type, split_part=1)

                if commit:
                    instance.save()

                # 2回目のエントリー用のdue_dateとbilling_monthを計算
                # 通常払いの2回目は利用月から計算
                second_due_date = instance.due_date
                second_billing_month = calculate_billing_month(instance.year_month, instance.card_type, split_part=2)

                # 2回目のエントリー（2回目）を作成（利用月は同じ）
                CreditEstimate.objects.create(
                    year_month=instance.year_month,  # 利用月は1回目と同じ
                    billing_month=second_billing_month,
                    card_type=instance.card_type,
                    description=instance.description,
                    amount=second_payment,
                    purchase_date=instance.purchase_date,  # 利用日も1回目と同じ
                    due_date=second_due_date,
                    is_split_payment=True,
                    split_payment_part=2,
                    split_payment_group=group_id,
                )
            else:
                # 既に分割済みのエントリーを編集する場合、2回目のエントリーも更新
                if instance.split_payment_part == 1 and instance.split_payment_group:
                    # フォームから送信された金額は合計金額
                    total_amount = instance.amount
                    second_payment_amount = (total_amount // 2) // 100 * 100
                    first_payment_amount = total_amount - second_payment_amount
                    instance.amount = first_payment_amount

                    # 1回目のbilling_monthを設定
                    if not instance.is_bonus_payment:
                        instance.billing_month = calculate_billing_month(instance.year_month, instance.card_type, split_part=1)

                    # 2回目のエントリーを取得して更新
                    second_payment = CreditEstimate.objects.filter(
                        split_payment_group=instance.split_payment_group,
                        split_payment_part=2
                    ).first()

                    if second_payment:
                        second_payment.year_month = instance.year_month  # 利用月は1回目と同じ
                        second_payment.card_type = instance.card_type
                        second_payment.description = instance.description
                        second_payment.amount = second_payment_amount  # 金額を更新
                        second_payment.purchase_date = instance.purchase_date  # 利用日も1回目と同じ
                        second_payment.due_date = instance.due_date
                        second_payment.billing_month = calculate_billing_month(instance.year_month, instance.card_type, split_part=2)
                        second_payment.save()
                elif instance.split_payment_part == 2 and instance.split_payment_group:
                    # 2回目のみ編集する場合
                    # 金額を再計算
                    total_amount = instance.amount
                    second_payment_amount = (total_amount // 2) // 100 * 100
                    first_payment_amount = total_amount - second_payment_amount
                    instance.amount = second_payment_amount

                    if not instance.is_bonus_payment:
                        instance.billing_month = calculate_billing_month(instance.year_month, instance.card_type, split_part=2)

                    # 1回目のエントリーを取得して更新
                    first_payment = CreditEstimate.objects.filter(
                        split_payment_group=instance.split_payment_group,
                        split_payment_part=1
                    ).first()

                    if first_payment:
                        first_payment.amount = first_payment_amount
                        first_payment.save()
        else:
            # 分割払いチェックボックスがオフの場合
            if is_already_split:
                # 分割払いから通常払いに戻す処理
                if instance.split_payment_group:
                    # 同じグループの全エントリーを取得
                    all_payments = CreditEstimate.objects.filter(
                        split_payment_group=instance.split_payment_group
                    ).order_by('split_payment_part')

                    # 全エントリーの金額を合計
                    total_amount = sum(payment.amount for payment in all_payments)

                    # 1回目のエントリーを取得（元の月）
                    first_payment = all_payments.filter(split_payment_part=1).first()

                    if first_payment:
                        if first_payment.pk == instance.pk:
                            # 編集中のエントリーが1回目の場合
                            instance.amount = total_amount
                            # 2回目を削除
                            all_payments.exclude(pk=instance.pk).delete()
                        else:
                            # 編集中のエントリーが2回目の場合
                            # 1回目に合計金額を設定
                            first_payment.amount = total_amount
                            first_payment.split_payment_part = None
                            first_payment.split_payment_group = None
                            first_payment.is_split_payment = False
                            # billing_monthを再計算（分割なしの場合）
                            if not first_payment.is_bonus_payment:
                                first_payment.billing_month = calculate_billing_month(first_payment.year_month, first_payment.card_type, split_part=None)
                            first_payment.save()
                            # 現在のエントリー（2回目）を削除するため、commitをFalseに
                            if commit:
                                instance.delete()
                            return first_payment
                    else:
                        # 1回目が見つからない場合は現在のエントリーに合計
                        other_payments = all_payments.exclude(pk=instance.pk)
                        total_other_amount = sum(payment.amount for payment in other_payments)
                        instance.amount += total_other_amount
                        other_payments.delete()

                # 分割払い情報をクリア
                instance.split_payment_part = None
                instance.split_payment_group = None

        # 通常払い（分割なし）の場合、billing_monthを設定
        # ただし、ボーナス払いは既にdue_dateベースで設定済みなのでスキップ
        if not instance.is_bonus_payment and (not instance.is_split_payment or not instance.split_payment_part):
            instance.billing_month = calculate_billing_month(instance.year_month, instance.card_type, split_part=None)

        if commit:
            instance.save()

        return instance


class CreditDefaultForm(forms.ModelForm):
    """定期デフォルト編集・作成用フォーム"""

    class Meta:
        model = CreditDefault
        fields = ['label', 'card_type', 'amount', 'payment_day', 'apply_odd_months_only']
        widgets = {
            'label': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': '例: Netflix',
            }),
            'card_type': forms.Select(attrs={
                'class': 'w-full p-2 border rounded',
                'id': 'default_edit_card_type',
            }),
            'amount': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded amount-input',
                'id': 'default_edit_amount',
                'inputmode': 'numeric',
                'pattern': '[0-9,]*',
            }),
            'payment_day': forms.NumberInput(attrs={
                'class': 'w-full p-2 border rounded',
                'min': '1',
                'max': '31',
                'placeholder': '1-31',
            }),
            'apply_odd_months_only': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded',
            }),
        }
        labels = {
            'label': '項目名',
            'card_type': 'カード種別',
            'amount': '金額（円）',
            'payment_day': '毎月の利用日',
            'apply_odd_months_only': '奇数月のみ適用（例：水道代）',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # カード選択肢を動的に生成
        from .models import CreditEstimate
        card_choices = CreditEstimate.get_card_choices()
        self.fields['card_type'].choices = card_choices  # フィールドのchoicesを設定（バリデーション用）
        self.fields['card_type'].widget.choices = card_choices  # ウィジェットのchoicesも設定

        # 新規作成時のみカード種別のデフォルト値を設定（最初のカード）
        if not self.instance.pk and card_choices:
            self.fields['card_type'].initial = card_choices[0][0]

    def clean_amount(self):
        """カンマを除去して整数に変換"""
        amount_str = self.cleaned_data.get('amount', '')
        if isinstance(amount_str, str):
            amount_str = amount_str.replace(',', '')
        try:
            return int(amount_str)
        except (ValueError, TypeError):
            raise forms.ValidationError('正しい数値を入力してください。')

    def save(self, commit=True):
        instance = super().save(commit=False)
        # 新規作成時のみキーをラベルから自動生成
        if not instance.pk and not instance.key:
            import re
            label = self.cleaned_data.get('label', '')
            if label:
                key = re.sub(r'[^\w\s]', '', label)
                key = re.sub(r'\s+', '_', key.strip()).lower()
                base_key = key
                counter = 1
                while CreditDefault.objects.filter(key=key).exists():
                    key = f"{base_key}_{counter}"
                    counter += 1
                instance.key = key

        if commit:
            instance.save()
        return instance


class MonthlyPlanDefaultForm(forms.ModelForm):
    """月次計画デフォルト項目編集・作成用フォーム"""

    class Meta:
        model = MonthlyPlanDefault
        fields = ['title', 'amount', 'payment_type', 'withdrawal_day', 'is_withdrawal_end_of_month', 'consider_holidays', 'closing_day', 'is_end_of_month']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': '例: 家賃',
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'w-full p-2 border rounded',
                'min': '0',
                'placeholder': '50000',
            }),
            'payment_type': forms.Select(attrs={
                'class': 'w-full p-2 border rounded',
            }),
            'withdrawal_day': forms.NumberInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': '1-31',
                'min': '1',
                'max': '31',
                'id': 'withdrawal_day_input',
            }),
            'is_withdrawal_end_of_month': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded',
                'id': 'is_withdrawal_end_of_month_checkbox',
            }),
            'consider_holidays': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded',
            }),
            'closing_day': forms.NumberInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': '1-31（クレカの場合のみ）',
                'min': '1',
                'max': '31',
                'id': 'closing_day_input',
            }),
            'is_end_of_month': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded',
                'id': 'is_end_of_month_checkbox',
            }),
        }
        labels = {
            'title': '項目名',
            'amount': 'デフォルト金額（円）',
            'payment_type': '種別',
            'withdrawal_day': '引落日 / 振込日',
            'is_withdrawal_end_of_month': '引落日 / 振込日を月末にする',
            'consider_holidays': '休日を考慮',
            'closing_day': '締め日（クレカの場合）',
            'is_end_of_month': '締め日を月末にする',
        }

    def clean_withdrawal_day(self):
        """引落日のバリデーション"""
        day = self.cleaned_data.get('withdrawal_day')
        if day is not None and (day < 1 or day > 31):
            raise forms.ValidationError('1から31の範囲で入力してください。')
        return day

    def clean_closing_day(self):
        """締め日のバリデーション"""
        day = self.cleaned_data.get('closing_day')
        if day is not None and (day < 1 or day > 31):
            raise forms.ValidationError('1から31の範囲で入力してください。')
        return day


class PastMonthlyPlanForm(forms.ModelForm):
    """過去月次計画フォーム（収入・支出項目）"""

    year = forms.ChoiceField(
        label='年',
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full p-2 border rounded'
        })
    )
    month = forms.ChoiceField(
        label='月',
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full p-2 border rounded'
        })
    )

    class Meta:
        model = MonthlyPlan
        fields = [
            'year_month',
            'gross_salary', 'deductions', 'transportation',
            'bonus_gross_salary', 'bonus_deductions',
        ]

        widgets = {
            'year_month': forms.HiddenInput(),
        }

        labels = {
            'year_month': '年月（YYYY-MM）',
            'salary': '給与',
            'bonus': 'ボーナス',
            'gross_salary': '総支給額',
            'deductions': '控除額',
            'transportation': '交通費',
            'bonus_gross_salary': 'ボーナス総支給額',
            'bonus_deductions': 'ボーナス控除額',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 年の選択肢を生成（過去10年分）
        current_year = datetime.now().year
        year_choices = [(str(year), str(year)) for year in range(current_year - 10, current_year + 1)]
        self.fields['year'].choices = year_choices

        # 月の選択肢を生成
        month_choices = [
            ('01', '1月'), ('02', '2月'), ('03', '3月'), ('04', '4月'),
            ('05', '5月'), ('06', '6月'), ('07', '7月'), ('08', '8月'),
            ('09', '9月'), ('10', '10月'), ('11', '11月'), ('12', '12月')
        ]
        self.fields['month'].choices = month_choices

        # 既存のインスタンスがある場合、年と月のフィールドを削除（編集時は表示しない）
        if self.instance and self.instance.pk and self.instance.year_month:
            # 編集時は年月フィールドを表示しない
            if 'year' in self.fields:
                del self.fields['year']
            if 'month' in self.fields:
                del self.fields['month']

        # POSTデータから年月を取得（新規作成時）
        selected_year = None
        selected_month = None
        if args and len(args) > 0:
            post_data = args[0]
            selected_year = post_data.get('year')
            selected_month = post_data.get('month')

        # デフォルト値（現在の年月）- 新規作成時のみ
        if 'year' in self.fields and not selected_year:
            selected_year = str(current_year)
            self.fields['year'].initial = selected_year
        if 'month' in self.fields and not selected_month:
            selected_month = f"{datetime.now().month:02d}"
            self.fields['month'].initial = selected_month


        # すべての数値入力フィールドに共通のクラスを適用
        for field_name in self.fields:
            if field_name not in ['year_month', 'year', 'month']:
                self.fields[field_name].widget.attrs.update({
                    'class': 'w-full p-2 border rounded',
                    'placeholder': '0'
                })
                # bonusとtransportationはrequiredをFalseに（任意項目）
                if field_name in ['bonus', 'transportation']:
                    self.fields[field_name].required = False
                # その他の給与明細フィールドは必須
                else:
                    self.fields[field_name].required = True

    def clean(self):
        cleaned_data = super().clean()
        year = cleaned_data.get('year')
        month = cleaned_data.get('month')
        year_month = cleaned_data.get('year_month')

        # year_monthが既に設定されている場合（編集時）はそのまま使用
        # 設定されていない場合（新規作成時）はyearとmonthから生成
        if not year_month:
            if year and month:
                cleaned_data['year_month'] = f"{year}-{month}"
            else:
                raise forms.ValidationError('年と月を選択してください。')

        # 数値フィールドの空白を0に変換（データベースのNOT NULL制約対策）
        numeric_fields = [
            'salary', 'bonus', 'gross_salary', 'deductions', 'transportation',
            'bonus_gross_salary', 'bonus_deductions'
        ]

        # MonthlyPlanDefaultから動的にフィールドを追加
        from .models import MonthlyPlanDefault
        for default_item in MonthlyPlanDefault.objects.filter(is_active=True):
            numeric_fields.append(default_item.key)

        for field_name in numeric_fields:
            if field_name in self.fields and field_name in cleaned_data:
                value = cleaned_data[field_name]
                if value is None or value == '':
                    cleaned_data[field_name] = 0

        return cleaned_data

    def save(self, commit=True):
        """
        保存処理
        """
        instance = super().save(commit=False)

        if commit:
            instance.save()

        return instance


class PastSalaryForm(forms.ModelForm):
    """過去の給与情報新規作成フォーム（収入のみ）"""

    year = forms.ChoiceField(
        label='年',
        widget=forms.Select(attrs={
            'class': 'w-full p-2 border rounded'
        })
    )
    month = forms.ChoiceField(
        label='月',
        widget=forms.Select(attrs={
            'class': 'w-full p-2 border rounded'
        })
    )

    class Meta:
        model = MonthlyPlan
        fields = [
            'year_month',
            'gross_salary', 'deductions', 'transportation',
            'bonus_gross_salary', 'bonus_deductions',
        ]

        widgets = {
            'year_month': forms.HiddenInput(),
        }

        labels = {
            'year_month': '年月（YYYY-MM）',
            'gross_salary': '総支給額',
            'deductions': '控除額',
            'transportation': '交通費',
            'bonus_gross_salary': 'ボーナス総支給額',
            'bonus_deductions': 'ボーナス控除額',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 年の選択肢を生成（過去10年分、現在の月は含めない）
        current_year = datetime.now().year
        year_choices = [(str(year), str(year)) for year in range(current_year - 10, current_year + 1)]
        self.fields['year'].choices = year_choices

        # 月の選択肢を生成
        month_choices = [
            ('01', '1月'), ('02', '2月'), ('03', '3月'), ('04', '4月'),
            ('05', '5月'), ('06', '6月'), ('07', '7月'), ('08', '8月'),
            ('09', '9月'), ('10', '10月'), ('11', '11月'), ('12', '12月')
        ]
        self.fields['month'].choices = month_choices

        # 既存のインスタンスがある場合、年と月のフィールドを削除（編集時は表示しない）
        if self.instance and self.instance.pk and self.instance.year_month:
            # 編集時は年月フィールドを表示しない
            if 'year' in self.fields:
                del self.fields['year']
            if 'month' in self.fields:
                del self.fields['month']

        # POSTデータから年月を取得（新規作成時）
        selected_year = None
        selected_month = None
        if args and len(args) > 0:
            post_data = args[0]
            selected_year = post_data.get('year')
            selected_month = post_data.get('month')

        # デフォルト値（先月）- 新規作成時のみ
        if not selected_year or not selected_month:
            if 'year' in self.fields and 'month' in self.fields:
                last_month = datetime.now() - timedelta(days=30)
                selected_year = str(last_month.year)
                selected_month = f"{last_month.month:02d}"
                self.fields['year'].initial = selected_year
                self.fields['month'].initial = selected_month

        # すべての数値入力フィールドに共通のクラスを適用
        for field_name in self.fields:
            if field_name not in ['year_month', 'year', 'month']:
                self.fields[field_name].widget.attrs.update({
                    'class': 'w-full p-2 border rounded',
                    'placeholder': '0'
                })
                # bonus, transportation, bonus関連フィールドは任意項目
                if field_name in ['bonus', 'transportation', 'bonus_gross_salary', 'bonus_deductions']:
                    self.fields[field_name].required = False
                else:
                    self.fields[field_name].required = False  # 過去の給与は全て任意

    def clean(self):
        cleaned_data = super().clean()
        year = cleaned_data.get('year')
        month = cleaned_data.get('month')
        year_month = cleaned_data.get('year_month')

        # year_monthが既に設定されている場合（編集時）はそのまま使用
        # 設定されていない場合（新規作成時）はyearとmonthから生成
        if not year_month:
            if year and month:
                cleaned_data['year_month'] = f"{year}-{month}"
            else:
                raise forms.ValidationError('年と月を選択してください。')

        # 過去の月のみ許可（現在の月以降はエラー）
        # ただし、既存レコードの編集時はこのチェックをスキップ
        if not self.instance.pk:
            current_year_month = datetime.now().strftime('%Y-%m')
            selected_year_month = cleaned_data.get('year_month')
            if selected_year_month and selected_year_month >= current_year_month:
                raise forms.ValidationError('過去の月のみ選択できます。今月以降の計画は月次計画作成から登録してください。')

        # 数値フィールドの空白を0に変換（データベースのNOT NULL制約対策）
        numeric_fields = [
            'gross_salary', 'deductions', 'transportation',
            'bonus_gross_salary', 'bonus_deductions'
        ]
        for field_name in numeric_fields:
            if field_name in self.fields and field_name in cleaned_data:
                value = cleaned_data[field_name]
                if value is None or value == '':
                    cleaned_data[field_name] = 0

        return cleaned_data
