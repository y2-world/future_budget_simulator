from django.db import models
from django.core.validators import MinValueValidator


class AccountBalance(models.Model):
    """口座残高"""
    date = models.DateField(verbose_name="日付", unique=True)
    balance = models.IntegerField(verbose_name="残高")
    source = models.CharField(
        max_length=20,
        choices=[('manual', '手動入力'), ('api', 'API取得')],
        default='manual',
        verbose_name="データソース"
    )
    last_updated = models.DateTimeField(auto_now=True, verbose_name="最終更新日時")

    class Meta:
        verbose_name = "口座残高"
        verbose_name_plural = "口座残高"
        ordering = ['-date']

    def __str__(self):
        return f"{self.date}: ¥{self.balance:,}"


class MonthlyPlan(models.Model):
    """月次収支計画（フレキシブルな項目管理対応）"""
    year_month = models.CharField(max_length=7, unique=True, verbose_name="年月")  # YYYY-MM

    # 新しいフレキシブルな項目管理
    items = models.JSONField(
        default=dict,
        verbose_name="計画項目",
        help_text="MonthlyPlanDefaultで定義された項目の金額を格納 例: {'salary': 271919, 'food': 50000}"
    )
    exclusions = models.JSONField(
        default=dict,
        verbose_name="繰上げ返済フラグ",
        help_text="クレカ項目の繰上げ返済フラグ 例: {'view_card': True, 'rakuten_card': False}"
    )

    # 既存フィールド（後方互換性のため残す、段階的に非推奨化）
    # 収入
    salary = models.IntegerField(default=0, verbose_name="給与")
    bonus = models.IntegerField(default=0, verbose_name="ボーナス")

    # 給与明細の詳細
    gross_salary = models.IntegerField(default=0, verbose_name="総支給額")
    deductions = models.IntegerField(default=0, verbose_name="控除額")
    transportation = models.IntegerField(default=0, verbose_name="交通費")

    # ボーナス明細の詳細
    bonus_gross_salary = models.IntegerField(default=0, verbose_name="ボーナス総支給額")
    bonus_deductions = models.IntegerField(default=0, verbose_name="ボーナス控除額")

    # 支出
    food = models.IntegerField(default=0, verbose_name="食費")
    rent = models.IntegerField(default=0, verbose_name="家賃")
    lake = models.IntegerField(default=0, verbose_name="レイク返済")
    view_card = models.IntegerField(default=0, verbose_name="VIEWカード")
    view_card_bonus = models.IntegerField(default=0, verbose_name="ボーナス払い")
    rakuten_card = models.IntegerField(default=0, verbose_name="楽天カード")
    paypay_card = models.IntegerField(default=0, verbose_name="PayPayカード")
    vermillion_card = models.IntegerField(default=0, verbose_name="VERMILLION CARD")
    amazon_card = models.IntegerField(default=0, verbose_name="Amazonカード")
    olive_card = models.IntegerField(default=0, verbose_name="Olive")
    savings = models.IntegerField(default=0, verbose_name="定期預金")
    loan = models.IntegerField(default=0, verbose_name="マネーアシスト返済")
    loan_borrowing = models.IntegerField(default=0, verbose_name="マネーアシスト借入")
    other = models.IntegerField(default=7700, verbose_name="ジム")

    # クレカ項目の繰上げ返済フラグ（チェックすると請求金額を引かない）
    exclude_view_card = models.BooleanField(default=False, verbose_name="VIEWカード繰上げ返済")
    exclude_view_card_bonus = models.BooleanField(default=False, verbose_name="VIEWボーナス払い繰上げ返済")
    exclude_rakuten_card = models.BooleanField(default=False, verbose_name="楽天カード繰上げ返済")
    exclude_paypay_card = models.BooleanField(default=False, verbose_name="PayPayカード繰上げ返済")
    exclude_vermillion_card = models.BooleanField(default=False, verbose_name="VERMILLION繰上げ返済")
    exclude_amazon_card = models.BooleanField(default=False, verbose_name="Amazonカード繰上げ返済")
    exclude_olive_card = models.BooleanField(default=False, verbose_name="Olive繰上げ返済")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="作成日時")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新日時")

    class Meta:
        verbose_name = "月次計画"
        verbose_name_plural = "月次計画"
        ordering = ['year_month']

    def __str__(self):
        return f"{self.year_month}"

    def get_item(self, field_name):
        """
        項目の金額を取得（items JSONFieldから、フォールバックとして既存フィールドから）
        """
        # まずitemsから取得
        if field_name in self.items:
            return self.items[field_name]
        # フォールバック: 既存フィールドから取得
        return getattr(self, field_name, 0)

    def set_item(self, field_name, value):
        """
        項目の金額を設定（items JSONFieldと既存フィールドの両方に設定）
        """
        # itemsに設定
        if not isinstance(self.items, dict):
            self.items = {}
        self.items[field_name] = value
        # 既存フィールドにも設定（後方互換性のため）
        if hasattr(self, field_name):
            setattr(self, field_name, value)

    def get_exclusion(self, field_name):
        """繰上げ返済フラグを取得"""
        # まずexclusionsから取得
        if field_name in self.exclusions:
            return self.exclusions[field_name]
        # フォールバック: 既存フィールドから取得
        exclude_field = f'exclude_{field_name}'
        return getattr(self, exclude_field, False)

    def set_exclusion(self, field_name, value):
        """繰上げ返済フラグを設定"""
        # exclusionsに設定
        if not isinstance(self.exclusions, dict):
            self.exclusions = {}
        self.exclusions[field_name] = value
        # 既存フィールドにも設定（後方互換性のため）
        exclude_field = f'exclude_{field_name}'
        if hasattr(self, exclude_field):
            setattr(self, exclude_field, value)

    def get_total_income(self):
        """月次総収入を計算"""
        return self.get_item('salary') + self.get_item('bonus')

    def get_total_expenses(self):
        """月次総支出を計算（除外フラグがチェックされたクレカ項目は含まない）"""
        total = 0
        # MonthlyPlanDefaultから有効な項目を取得
        from .models import MonthlyPlanDefault
        default_items = MonthlyPlanDefault.objects.filter(is_active=True)

        for default_item in default_items:
            # フィールド名を取得
            from budget_app.views import get_field_mapping
            field_mapping = get_field_mapping()
            field_name = field_mapping.get(default_item.title)

            if field_name and default_item.payment_type == 'withdrawal':
                # 引落項目の場合
                amount = self.get_item(field_name)

                # クレカ項目の場合、繰上げ返済フラグをチェック
                if field_name in ['view_card', 'view_card_bonus', 'rakuten_card', 'paypay_card',
                                  'vermillion_card', 'amazon_card', 'olive_card']:
                    if not self.get_exclusion(field_name):
                        total += amount
                else:
                    total += amount

        return total
    
    def get_total_borrowing(self):
        """月次総借入を計算"""
        return self.get_item('loan_borrowing')

    def get_net_income(self):
        """月次収支を計算"""
        return self.get_total_income() - self.get_total_expenses()


class CreditEstimate(models.Model):
    """クレカ請求額の見積り（未来・現時点）"""

    CARD_TYPES = [
        ('view', 'VIEWカード'),
        ('rakuten', '楽天カード'),
        ('paypay', 'PayPayカード'),
        ('vermillion', 'VERMILLION CARD'),
        ('amazon', 'Amazonカード'),
        ('olive', 'Olive'),
    ]

    year_month = models.CharField(max_length=7, verbose_name="利用月（YYYY-MM）")
    billing_month = models.CharField(max_length=7, verbose_name="引き落とし月（YYYY-MM）", null=True, blank=True)
    card_type = models.CharField(max_length=10, choices=CARD_TYPES, verbose_name="カード種別")
    description = models.CharField(max_length=100, blank=True, verbose_name="メモ")
    amount = models.IntegerField(verbose_name="見積額（円）")
    due_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="請求日",
        help_text="請求日をカレンダーから選択"
    )
    purchase_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="購入日",
        help_text="ボーナス払いの場合、購入日を入力"
    )
    is_split_payment = models.BooleanField(
        default=False,
        verbose_name="分割2回払い"
    )
    is_bonus_payment = models.BooleanField(
        default=False,
        verbose_name="ボーナス払い"
    )
    split_payment_part = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="分割払い回数",
        help_text="分割払いの場合、1 or 2"
    )
    split_payment_group = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="分割払いグループID",
        help_text="同じ分割払いのペアを識別するID"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="作成日時")

    class Meta:
        verbose_name = "クレカ見積り"
        verbose_name_plural = "クレカ見積り"
        ordering = ['year_month', 'card_type', '-created_at']

    def __str__(self):
        card_label = dict(self.CARD_TYPES).get(self.card_type, self.card_type)
        return f"{self.year_month} {card_label}: ¥{self.amount:,}"


class TransactionEvent(models.Model):
    """支払いイベント（計算結果）"""
    EVENT_TYPES = [
        ('salary', '給与'),
        ('bonus', 'ボーナス'),
        ('food', '食費'),
        ('rent', '家賃'),
        ('lake', 'レイク返済'),
        ('view_card', 'VIEWカード'),
        ('rakuten_card', '楽天カード'),
        ('paypay_card', 'PayPayカード'),
        ('vermillion_card', 'VERMILLION CARD'),
        ('amazon_card', 'Amazonカード'),
        ('savings', '定期預金'),
        ('loan', 'マネーアシスト返済'),
        ('other', 'ジム'),
    ]

    date = models.DateField(verbose_name="日付")
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, verbose_name="種類")
    event_name = models.CharField(max_length=100, verbose_name="イベント名")
    amount = models.IntegerField(verbose_name="金額")  # 正=収入、負=支出
    balance_after = models.IntegerField(verbose_name="取引後残高")
    month = models.ForeignKey(
        MonthlyPlan,
        on_delete=models.CASCADE,
        related_name='transactions',
        verbose_name="関連月"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="作成日時")

    class Meta:
        verbose_name = "取引イベント"
        verbose_name_plural = "取引イベント"
        ordering = ['date', 'id']

    def __str__(self):
        return f"{self.date} - {self.event_name}: ¥{self.amount:,}"


class SimulationConfig(models.Model):
    """シミュレーション設定"""
    initial_balance = models.IntegerField(
        default=0,
        verbose_name="初期残高",
        help_text="シミュレーション開始時の口座残高"
    )
    start_date = models.DateField(verbose_name="開始日")
    simulation_months = models.IntegerField(
        default=12,
        validators=[MinValueValidator(1)],
        verbose_name="シミュレーション期間（月）"
    )
    default_salary = models.IntegerField(
        default=271919,
        verbose_name="デフォルト給与（円）",
        help_text="月次計画作成時のデフォルト給与額"
    )
    default_food = models.IntegerField(
        default=0,
        verbose_name="デフォルト食費（円）",
        help_text="月次計画作成時のデフォルト食費"
    )
    default_view_card = models.IntegerField(
        default=50000,
        verbose_name="VIEWカードデフォルト利用額（円）",
        help_text="クレカ見積もりに毎月デフォルトで計上されるVIEWカードの金額"
    )
    savings_enabled = models.BooleanField(
        default=False,
        verbose_name="定期預金を有効化",
        help_text="定期預金機能のオン/オフ"
    )
    savings_amount = models.IntegerField(
        default=50000,
        verbose_name="定期預金額（円）",
        help_text="毎月の定期預金額"
    )
    savings_start_month = models.CharField(
        max_length=7,
        blank=True,
        null=True,
        verbose_name="定期預金開始月（YYYY-MM）",
        help_text="定期預金を開始する年月"
    )
    is_active = models.BooleanField(default=True, verbose_name="有効")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="作成日時")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新日時")

    class Meta:
        verbose_name = "シミュレーション設定"
        verbose_name_plural = "シミュレーション設定"
        ordering = ['-created_at']

    def __str__(self):
        return f"設定: {self.start_date} から {self.simulation_months}ヶ月"


class CreditDefault(models.Model):
    """サブスク・固定費などの定期デフォルト（カード紐付けあり）"""

    CARD_TYPES = CreditEstimate.CARD_TYPES

    key = models.CharField(max_length=50, unique=True, verbose_name="キー")
    label = models.CharField(max_length=100, verbose_name="項目名")
    card_type = models.CharField(max_length=10, choices=CARD_TYPES, verbose_name="カード種別")
    amount = models.IntegerField(default=0, verbose_name="金額（円）")
    is_active = models.BooleanField(default=True, verbose_name="有効")
    apply_odd_months_only = models.BooleanField(default=False, verbose_name="奇数月のみ適用")

    class Meta:
        verbose_name = "定期デフォルト"
        verbose_name_plural = "定期デフォルト"
        ordering = ['key']

    def __str__(self):
        return f"{self.label}: ¥{self.amount:,}"


class DefaultChargeOverride(models.Model):
    """定期デフォルトの特定の月の金額上書き"""
    default = models.ForeignKey(CreditDefault, on_delete=models.CASCADE, related_name='overrides')
    year_month = models.CharField('対象年月', max_length=7, help_text='YYYY-MM形式')
    amount = models.PositiveIntegerField('上書き金額')
    card_type = models.CharField(
        'カード種別',
        max_length=20,
        choices=CreditEstimate.CARD_TYPES,
        null=True,
        blank=True,
        help_text='この月だけカード種別を変更する場合に指定'
    )
    is_split_payment = models.BooleanField(
        default=False,
        verbose_name='2回払い',
        help_text='この月だけ2回払いにする場合にチェック'
    )

    class Meta:
        verbose_name = '定期デフォルトの上書き'
        verbose_name_plural = '定期デフォルトの上書き'
        unique_together = ('default', 'year_month') # 同じ月の同じ項目は一つだけ

    def __str__(self):
        return f"{self.year_month} - {self.default.label}: {self.amount}"


class MonthlyPlanDefault(models.Model):
    """月次計画のデフォルト項目"""

    PAYMENT_TYPE_CHOICES = [
        ('deposit', '振込'),
        ('withdrawal', '引き落とし'),
    ]

    title = models.CharField(max_length=100, verbose_name="項目名")
    amount = models.IntegerField(default=0, verbose_name="デフォルト金額（円）")
    payment_type = models.CharField(
        max_length=20,
        choices=PAYMENT_TYPE_CHOICES,
        default='withdrawal',
        verbose_name="種別",
        help_text="振込または引き落とし"
    )
    withdrawal_day = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="引き落とし日/振込日",
        help_text="1-31の数値。引き落とし日または振込日を設定"
    )
    is_withdrawal_end_of_month = models.BooleanField(
        default=False,
        verbose_name="引き落とし日/振込日を月末にする",
        help_text="チェックすると引き落とし日/振込日が月末になります"
    )
    consider_holidays = models.BooleanField(
        default=False,
        verbose_name="休日を考慮",
        help_text="振込:休日なら直前の金曜、引落:休日なら翌営業日"
    )
    closing_day = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="締め日",
        help_text="クレジットカードの場合のみ設定。1-31の数値"
    )
    is_end_of_month = models.BooleanField(
        default=False,
        verbose_name="締め日を月末にする",
        help_text="チェックすると締め日が月末になります"
    )
    is_active = models.BooleanField(default=True, verbose_name="有効")
    order = models.IntegerField(default=0, verbose_name="表示順")

    class Meta:
        verbose_name = "月次計画デフォルト項目"
        verbose_name_plural = "月次計画デフォルト項目"
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.title}: ¥{self.amount:,}"
