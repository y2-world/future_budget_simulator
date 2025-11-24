from django import forms
from datetime import datetime
import calendar
from .models import SimulationConfig, MonthlyPlan, CreditEstimate, CreditDefault


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
            'initial_balance',
            'default_salary',
            'default_food',
            'default_view_card',
            'savings_enabled',
            'savings_amount',
            'savings_start_month',
        ]
        widgets = {
            'initial_balance': forms.NumberInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': '例: 500000'
            }),
            'default_salary': forms.NumberInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': '例: 271919'
            }),
            'default_food': forms.NumberInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': '例: 50000',
                'min': 0
            }),
            'default_view_card': forms.NumberInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': '例: 50000',
                'min': 0
            }),
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
            'initial_balance': '初期残高（円）',
            'default_salary': 'デフォルト給与（円）',
            'default_food': 'デフォルト食費（円）',
            'default_view_card': 'VIEWカードデフォルト利用額（円）',
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


class MonthlyPlanForm(forms.ModelForm):
    """月次計画フォーム"""
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
            'salary', 'bonus',
            'food', 'rent',
            'lake',
            'view_card', 'view_card_bonus', 'rakuten_card', 'paypay_card',
            'vermillion_card', 'amazon_card',
            'loan_borrowing', 'other'
        ]

        widgets = {
            'year_month': forms.HiddenInput(),
        }

        labels = {
            'year_month': '年月（YYYY-MM）',
            'salary': '給与',
            'bonus': 'ボーナス',
            'food': '食費',
            'rent': '家賃',
            'lake': 'レイク返済',
            'view_card': 'VIEWカード（4日）',
            'view_card_bonus': 'VIEWボーナス払い（4日）',
            'rakuten_card': '楽天カード（27日）',
            'paypay_card': 'PayPayカード（27日）',
            'vermillion_card': 'VERMILLION CARD（4日）',
            'amazon_card': 'Amazonカード（26日）',
            'loan_borrowing': 'マネーアシスト借入',
            'other': 'その他',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 年の選択肢を生成（現在の年から前後3年）
        current_year = datetime.now().year
        year_choices = [(str(year), str(year)) for year in range(current_year - 3, current_year + 4)]
        self.fields['year'].choices = year_choices
        
        # 月の選択肢を生成
        month_choices = [
            ('01', '1月'), ('02', '2月'), ('03', '3月'), ('04', '4月'),
            ('05', '5月'), ('06', '6月'), ('07', '7月'), ('08', '8月'),
            ('09', '9月'), ('10', '10月'), ('11', '11月'), ('12', '12月')
        ]
        self.fields['month'].choices = month_choices
        
        # 選択された年月を取得
        selected_year = None
        selected_month = None
        
        # 既存のインスタンスがある場合、年と月を設定
        if self.instance and self.instance.pk and self.instance.year_month:
            try:
                selected_year, selected_month = self.instance.year_month.split('-')
                self.fields['year'].initial = selected_year
                self.fields['month'].initial = selected_month
            except ValueError:
                pass
        
        # POSTデータから年月を取得（新規作成時）
        if not selected_year and args and len(args) > 0:
            post_data = args[0]
            selected_year = post_data.get('year')
            selected_month = post_data.get('month')
        
        # デフォルト値（現在の年月）
        if not selected_year:
            selected_year = str(current_year)
            self.fields['year'].initial = selected_year
        if not selected_month:
            selected_month = f"{datetime.now().month:02d}"
            self.fields['month'].initial = selected_month
        
        # 年月に基づいてラベルを動的に設定
        if selected_year and selected_month:
            try:
                year_int = int(selected_year)
                month_int = int(selected_month)
                month_name = f"{month_int}月"
                
                # 前月を計算（クレカ引落用）
                if month_int == 1:
                    prev_year = year_int - 1
                    prev_month = 12
                else:
                    prev_year = year_int
                    prev_month = month_int - 1
                prev_month_name = f"{prev_month}月"
                
                # 各フィールドのラベルを動的に設定
                self.fields['salary'].label = f'給与（{year_int}年{month_name}25日）'
                self.fields['food'].label = f'食費（{year_int}年{month_name}1日）'
                self.fields['rent'].label = f'家賃（{year_int}年{month_name}27日）'
                self.fields['lake'].label = f'レイク返済（{year_int}年{month_name}27日）'
                self.fields['view_card'].label = f'VIEWカード（{year_int}年{month_name}4日）'
                self.fields['rakuten_card'].label = f'楽天カード（{year_int}年{month_name}27日）'
                self.fields['paypay_card'].label = f'PayPayカード（{year_int}年{month_name}27日）'
                self.fields['vermillion_card'].label = f'VERMILLION CARD（{year_int}年{month_name}4日）'
                self.fields['amazon_card'].label = f'Amazonカード（{year_int}年{month_name}26日）'
                self.fields['loan_borrowing'].label = f'マネーアシスト借入（{year_int}年{month_name}1日）'

                # レイク返済は2026年6月以降は表示しない
                if year_int > 2026 or (year_int == 2026 and month_int > 5):
                    if 'lake' in self.fields:
                        del self.fields['lake']

                # ボーナス払いフィールドは1月と8月のみ表示
                if selected_month not in ['01', '08']:
                    # VIEWカード以外のボーナス払いフィールドは常に削除
                    bonus_fields = [
                        'view_card_bonus'
                    ]
                    for field in bonus_fields:
                        if field in self.fields:
                            del self.fields[field]
                else:
                    if 'view_card_bonus' in self.fields:
                        self.fields['view_card_bonus'].label = f'VIEWボーナス払い（{year_int}年{month_name}4日）'
            except (ValueError, TypeError):
                pass

        # すべての数値入力フィールドに共通のクラスを適用
        for field_name in self.fields:
            if field_name not in ['year_month', 'year', 'month']:
                self.fields[field_name].widget.attrs.update({
                    'class': 'w-full p-2 border rounded',
                    'placeholder': '0'
                })
                # 条件付きフィールド（bonus, view_card_bonus, lake）はrequiredをFalseに
                if field_name in ['bonus', 'view_card_bonus', 'lake']:
                    self.fields[field_name].required = False

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

        return cleaned_data


class CreditEstimateForm(forms.ModelForm):
    """クレカ見積りフォーム"""

    year = forms.ChoiceField(
        label='請求年',
        widget=forms.Select(attrs={
            'class': 'w-full p-2 border rounded'
        })
    )
    month = forms.ChoiceField(
        label='請求月',
        widget=forms.Select(attrs={
            'class': 'w-full p-2 border rounded'
        })
    )

    class Meta:
        model = CreditEstimate
        fields = ['year_month', 'card_type', 'description', 'amount', 'due_date', 'is_split_payment', 'is_bonus_payment']
        widgets = {
            'year_month': forms.HiddenInput(),
            'card_type': forms.Select(attrs={
                'class': 'w-full p-2 border rounded',
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
            'due_date': forms.DateInput(attrs={
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
            'year_month': '請求月（YYYY-MM）',
            'card_type': 'カード種別',
            'description': 'メモ（任意）',
            'amount': '見積額（円）',
            'due_date': '請求日（任意）',
            'is_split_payment': '分割2回払い',
            'is_bonus_payment': 'ボーナス払い',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['year_month'].required = False
        self.fields['year'].widget.attrs.update({'data-year-select': 'true'})
        self.fields['month'].widget.attrs.update({'data-month-select': 'true'})
        self.fields['year_month'].widget.attrs.update({'data-year-month': 'true'})
        
        # 編集モーダルで使われるIDを設定
        self.fields['card_type'].widget.attrs.update({'id': 'edit_card_type'})


        # 年の選択肢（現在の年から前後3年）
        current_year = datetime.now().year
        year_choices = [(str(year), str(year)) for year in range(current_year - 3, current_year + 4)]
        self.fields['year'].choices = year_choices

        # 月の選択肢
        month_choices = [
            ('01', '1月'), ('02', '2月'), ('03', '3月'), ('04', '4月'),
            ('05', '5月'), ('06', '6月'), ('07', '7月'), ('08', '8月'),
            ('09', '9月'), ('10', '10月'), ('11', '11月'), ('12', '12月')
        ]
        self.fields['month'].choices = month_choices

        # 既存インスタンスの場合、初期値を設定
        if self.instance and self.instance.pk and self.instance.year_month:
            try:
                year, month = self.instance.year_month.split('-')
                self.fields['year'].initial = year
                self.fields['month'].initial = month
            except ValueError:
                pass

        # 新規作成時のデフォルト（当月）
        if not self.fields['year'].initial:
            self.fields['year'].initial = str(current_year)
        if not self.fields['month'].initial:
            self.fields['month'].initial = f"{datetime.now().month:02d}"

        # カード種別のデフォルトをVIEWカードに設定
        if not self.instance.pk:
            self.fields['card_type'].initial = 'view'

    def clean(self):
        cleaned_data = super().clean()
        year = cleaned_data.get('year')
        month = cleaned_data.get('month')

        if year and month:
            cleaned_data['year_month'] = f"{year}-{month}"

        return cleaned_data

    def save(self, commit=True):
        from datetime import datetime, timedelta
        from .models import CreditEstimate

        instance = super().save(commit=False)

        # ボーナス払いの場合、年月を調整
        # 新規作成時、または通常払いからボーナス払いに変更した場合のみ再計算
        if instance.is_bonus_payment:
            # 既存エントリーの場合は、元々ボーナス払いだったかチェック
            was_bonus_payment = False
            if instance.pk:
                try:
                    original = CreditEstimate.objects.get(pk=instance.pk)
                    was_bonus_payment = original.is_bonus_payment
                except CreditEstimate.DoesNotExist:
                    pass

            # 新規作成 または 通常払い→ボーナス払いへの変更の場合のみ再計算
            if not instance.pk or not was_bonus_payment:
                instance.year_month = get_next_bonus_month(instance.year_month)

        # 既に分割済みのエントリー（descriptionに「分割」が含まれる）は分割処理しない
        is_already_split = '(分割' in (instance.description or '')

        # 分割払いが選択されている場合は分割処理を実行（新規・編集どちらでも）
        if instance.is_split_payment and not is_already_split:
            total_amount = instance.amount
            # descriptionから既存の分割テキストを除去
            original_description = (instance.description or "").replace(" (分割1回目)", "").replace(" (分割2回目)", "").strip()

            # 2回目の金額を10の位まで0にする（100で切り捨て）
            second_payment = (total_amount // 2) // 100 * 100
            first_payment = total_amount - second_payment

            # 当月のインスタンス（1回目）を更新
            instance.amount = first_payment
            instance.description = f"{original_description} (分割1回目)".strip()
            instance.is_split_payment = False  # 保存後は分割フラグをオフ

            if commit:
                instance.save()

            # 次月を計算
            current_date = datetime.strptime(instance.year_month, '%Y-%m')
            next_month_date = (current_date.replace(day=1) + timedelta(days=32)).replace(day=1)
            next_month_str = next_month_date.strftime('%Y-%m')

            # 次月のエントリー（2回目）を作成
            CreditEstimate.objects.create(
                year_month=next_month_str,
                card_type=instance.card_type,
                description=f"{original_description} (分割2回目)".strip(),
                amount=second_payment,
                due_date=instance.due_date,
                is_split_payment=False,  # 2回目は分割フラグをオフ
                is_bonus_payment=instance.is_bonus_payment,
            )
        else:
            # 分割払いチェックボックスがオフの場合、または既に分割済みの場合
            if instance.is_split_payment and is_already_split:
                # 既に分割済みの場合は分割フラグをオフ
                instance.is_split_payment = False

        if commit:
            instance.save()

        return instance


class CreditDefaultForm(forms.ModelForm):
    """定期デフォルト編集・作成用フォーム"""

    class Meta:
        model = CreditDefault
        fields = ['label', 'card_type', 'amount', 'apply_odd_months_only']
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
            'apply_odd_months_only': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded',
            }),
        }
        labels = {
            'label': '項目名',
            'card_type': 'カード種別',
            'amount': '金額（円）',
            'apply_odd_months_only': '奇数月のみ適用（例：水道代）',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 新規作成時のみカード種別のデフォルト値をVIEWカードに設定
        if not self.instance.pk:
            self.fields['card_type'].initial = 'view'
        # 既存インスタンスの場合、金額にカンマを追加して表示
        if self.instance.pk and self.instance.amount:
            self.fields['amount'].initial = f"{self.instance.amount:,}"

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
