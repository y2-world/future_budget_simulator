from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Salary(models.Model):
    """給与明細"""
    year_month = models.CharField(max_length=7, unique=True, verbose_name="年月")  # YYYY-MM

    # 給与明細
    gross_salary = models.IntegerField(default=0, verbose_name="総支給額")
    deductions = models.IntegerField(default=0, verbose_name="控除額")
    transportation = models.IntegerField(default=0, verbose_name="交通費")

    # ボーナス明細（ボーナスがある月のみ入力）
    has_bonus = models.BooleanField(default=False, verbose_name="ボーナスあり")
    bonus_gross_salary = models.IntegerField(default=0, verbose_name="ボーナス総支給額")
    bonus_deductions = models.IntegerField(default=0, verbose_name="ボーナス控除額")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="作成日時")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新日時")

    class Meta:
        verbose_name = "給与明細"
        verbose_name_plural = "給与明細"
        ordering = ['year_month']

    def __str__(self):
        return f"{self.year_month}"

    def get_net_salary(self):
        """手取り給与を計算（差引支給額 = 総支給額 - 控除額）"""
        return self.gross_salary - self.deductions

    def get_net_bonus(self):
        """手取りボーナスを計算"""
        if self.has_bonus:
            return self.bonus_gross_salary - self.bonus_deductions
        return 0


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

    # 臨時収入・支出（JSONフィールド）
    temporary_items = models.JSONField(
        default=list,
        verbose_name="臨時項目",
        help_text="臨時収入・支出のリスト 例: [{'name': '旅行', 'amount': -50000, 'date': 15, 'type': 'expense'}]"
    )

    # 給与明細の詳細（itemsとは別に管理）
    gross_salary = models.IntegerField(default=0, verbose_name="総支給額")
    deductions = models.IntegerField(default=0, verbose_name="控除額")
    transportation = models.IntegerField(default=0, verbose_name="交通費")

    # ボーナス明細の詳細（itemsとは別に管理）
    bonus_gross_salary = models.IntegerField(default=0, verbose_name="ボーナス総支給額")
    bonus_deductions = models.IntegerField(default=0, verbose_name="ボーナス控除額")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="作成日時")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新日時")

    class Meta:
        verbose_name = "月次計画"
        verbose_name_plural = "月次計画"
        ordering = ['year_month']

    def __str__(self):
        return f"{self.year_month}"

    def save(self, *args, **kwargs):
        """
        保存時に自動処理を実行
        """
        super().save(*args, **kwargs)

    def get_item(self, field_name):
        """
        項目の金額を取得（items JSONFieldから）
        """
        if not isinstance(self.items, dict):
            return 0
        return self.items.get(field_name, 0)

    def set_item(self, field_name, value):
        """
        項目の金額を設定（items JSONFieldに設定）
        """
        if not isinstance(self.items, dict):
            self.items = {}
        self.items[field_name] = value

    def get_exclusion(self, field_name):
        """繰上げ返済フラグを取得"""
        if not isinstance(self.exclusions, dict):
            return False
        return self.exclusions.get(field_name, False)

    def set_exclusion(self, field_name, value):
        """繰上げ返済フラグを設定"""
        if not isinstance(self.exclusions, dict):
            self.exclusions = {}
        self.exclusions[field_name] = value

    def get_total_income(self):
        """月次総収入を計算（臨時収入を含む）"""
        total = 0
        # MonthlyPlanDefaultから入金項目を取得
        from .models import MonthlyPlanDefault
        deposit_items = MonthlyPlanDefault.objects.filter(payment_type='deposit')

        for deposit_item in deposit_items:
            # この月に表示すべき項目かチェック
            if not deposit_item.should_display_for_month(self.year_month):
                continue

            field_name = deposit_item.key
            if field_name:
                total += self.get_item(field_name)

        # 臨時収入を加算
        total += self.get_temporary_income()

        return total

    def get_total_expenses(self):
        """月次総支出を計算（除外フラグがチェックされたクレカ項目は含まない、臨時支出を含む）"""
        total = 0
        # MonthlyPlanDefaultから項目を取得
        from .models import MonthlyPlanDefault
        default_items = MonthlyPlanDefault.objects.filter(payment_type='withdrawal')

        for default_item in default_items:
            # この月に表示すべき項目かチェック
            if not default_item.should_display_for_month(self.year_month):
                continue

            # keyをフィールド名として使用
            field_name = default_item.key
            if not field_name:
                continue

            # 引落項目の場合
            amount = self.get_item(field_name)

            # クレカ項目の場合、繰上げ返済フラグをチェック
            if default_item.is_credit_card():
                if not self.get_exclusion(field_name):
                    total += amount
            else:
                total += amount

        # 臨時支出を加算
        total += self.get_temporary_expenses()

        return total
    

    def get_net_income(self):
        """月次収支を計算"""
        return self.get_total_income() - self.get_total_expenses()

    def get_temporary_items(self):
        """臨時項目のリストを取得"""
        if not isinstance(self.temporary_items, list):
            return []
        return self.temporary_items

    def get_temporary_income(self):
        """臨時収入の合計を取得"""
        total = 0
        for item in self.get_temporary_items():
            amount = item.get('amount', 0)
            if amount > 0:
                total += amount
        return total

    def get_temporary_expenses(self):
        """臨時支出の合計を取得"""
        total = 0
        for item in self.get_temporary_items():
            amount = item.get('amount', 0)
            if amount < 0:
                total += abs(amount)
        return total

    def add_temporary_item(self, name, amount, date, item_type='expense'):
        """臨時項目を追加"""
        if not isinstance(self.temporary_items, list):
            self.temporary_items = []
        self.temporary_items.append({
            'name': name,
            'amount': amount,
            'date': date,
            'type': item_type
        })

    def remove_temporary_item(self, index):
        """臨時項目を削除"""
        if isinstance(self.temporary_items, list) and 0 <= index < len(self.temporary_items):
            self.temporary_items.pop(index)


class CreditEstimate(models.Model):
    """クレカ請求額の見積り（未来・現時点）"""

    # デフォルトのカード種別（後方互換性のため）
    CARD_TYPES = [
        ('view', 'VIEWカード'),
        ('rakuten', '楽天カード'),
        ('paypay', 'PayPayカード'),
        ('vermillion', 'VERMILLION CARD'),
        ('amazon', 'Amazonカード'),
        ('olive', 'Olive'),
    ]

    @classmethod
    def get_card_choices(cls):
        """MonthlyPlanDefaultから動的にカード選択肢を生成"""
        from budget_app.models import MonthlyPlanDefault

        # MonthlyPlanDefaultからカードkeyと名称を取得
        card_choices = []

        for item in MonthlyPlanDefault.objects.filter(
            is_active=True,
            card_id__isnull=False
        ).exclude(card_id='').exclude(is_bonus_payment=True).order_by('order'):
            card_choices.append((item.key, item.title))  # card_idではなくkeyを使用

        # DBにデータがない場合はデフォルトを返す（後方互換性）
        return card_choices if card_choices else cls.CARD_TYPES

    year_month = models.CharField(max_length=7, verbose_name="利用月（YYYY-MM）")
    billing_month = models.CharField(max_length=7, verbose_name="引き落とし月（YYYY-MM）", null=True, blank=True)
    card_type = models.CharField(max_length=50, verbose_name="カード")
    description = models.CharField(max_length=100, blank=True, verbose_name="メモ")
    amount = models.IntegerField(verbose_name="見積額（円）")
    is_usd = models.BooleanField(default=False, verbose_name="ドル入力")
    usd_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="金額（ドル）")
    due_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="請求日",
        help_text="請求日をカレンダーから選択"
    )
    purchase_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="利用日",
        help_text="ボーナス払いの場合、利用日を入力"
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

    def get_card_type_display(self):
        """カード種別の表示名を取得（MonthlyPlanDefaultから）"""
        if self.card_type:
            card_item = MonthlyPlanDefault.objects.filter(card_id=self.card_type).first()
            if card_item:
                return card_item.title
        # フォールバック：MonthlyPlanDefaultに見つからない場合は、レガシーCARD_TYPESから取得
        return dict(self.CARD_TYPES).get(self.card_type, self.card_type)


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
    card_type = models.CharField(max_length=50, verbose_name="カード種別")  # choicesはフォームで動的に設定
    amount = models.IntegerField(default=0, verbose_name="金額（円）")
    is_usd = models.BooleanField(default=False, verbose_name="ドル入力")
    usd_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="金額（ドル）")
    is_active = models.BooleanField(default=True, verbose_name="有効")
    apply_odd_months_only = models.BooleanField(default=False, verbose_name="奇数月のみ適用")
    payment_day = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        verbose_name="毎月の利用日",
        help_text="1-31の数値。毎月この日に自動生成されます（例: Netflix = 1日）"
    )

    class Meta:
        verbose_name = "定期デフォルト"
        verbose_name_plural = "定期デフォルト"
        ordering = ['key']

    def __str__(self):
        return f"{self.label}: ¥{self.amount:,}"

    def get_card_type_display(self):
        """カード種別の表示名を取得"""
        if self.card_type:
            # MonthlyPlanDefaultからカード名を取得
            card_item = MonthlyPlanDefault.objects.filter(key=self.card_type).first()
            if card_item:
                return card_item.title
        # デフォルトのchoicesから取得を試みる
        return dict(self.CARD_TYPES).get(self.card_type, self.card_type)


class DefaultChargeOverride(models.Model):
    """定期デフォルトの特定の月の金額上書き"""
    default = models.ForeignKey(CreditDefault, on_delete=models.CASCADE, related_name='overrides')
    year_month = models.CharField('対象年月', max_length=7, help_text='YYYY-MM形式')
    amount = models.PositiveIntegerField('上書き金額')
    is_usd = models.BooleanField(default=False, verbose_name="ドル入力")
    usd_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="金額（ドル）")
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
    purchase_date_override = models.DateField(
        '利用日上書き',
        null=True,
        blank=True,
        help_text='この月だけ利用日を変更する場合に指定'
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
    key = models.CharField(
        max_length=100,
        unique=True,
        default='',
        blank=True,
        verbose_name="フィールド名",
        help_text="項目の一意識別子（自動生成）"
    )
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
        verbose_name="引落日 / 振込日",
        help_text="1-31の数値。引落日または振込日を設定"
    )
    is_withdrawal_end_of_month = models.BooleanField(
        default=False,
        verbose_name="引落日 / 振込日を月末にする",
        help_text="チェックすると引落日 / 振込日が月末になります"
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

    # 条件付き表示フィールド
    depends_on_key = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="依存する項目のkey",
        help_text="この項目が表示される条件として、指定されたkeyの項目に値がある必要がある"
    )
    offset_months = models.IntegerField(
        default=0,
        verbose_name="表示月オフセット",
        help_text="depends_on_keyで指定された項目から何ヶ月後に表示するか（例：1=翌月、0=同月）"
    )
    card_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        verbose_name="カードID",
        help_text="クレジットカード項目の一意識別子（自動生成: card_1, card_2, ...）"
    )
    is_bonus_payment = models.BooleanField(
        default=False,
        verbose_name="ボーナス払い",
        help_text="ボーナス払い用の項目かどうか"
    )

    class Meta:
        verbose_name = "月次計画デフォルト項目"
        verbose_name_plural = "月次計画デフォルト項目"
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.title}: ¥{self.amount:,}"

    def is_credit_card(self):
        """クレジットカード項目かどうかを判定（締め日が設定されている項目）"""
        return self.closing_day is not None or self.is_end_of_month

    def should_display_for_month(self, year_month):
        """指定された年月にこの項目を表示すべきかを判定"""
        # 依存関係がない場合は、is_activeに従う
        if not self.depends_on_key:
            return self.is_active

        # is_activeがFalseの場合は常に非表示
        if not self.is_active:
            return False

        # 依存関係がある場合、前月のデータをチェック
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

        current_date = datetime.strptime(year_month, '%Y-%m')
        # offset_monthsの逆計算（例：offset_months=1なら、1ヶ月前をチェック）
        check_date = current_date - relativedelta(months=self.offset_months)
        check_year_month = check_date.strftime('%Y-%m')

        # check_year_monthの MonthlyPlanで depends_on_keyに値があるかチェック
        try:
            from .models import MonthlyPlan
            plan = MonthlyPlan.objects.get(year_month=check_year_month)
            value = plan.get_item(self.depends_on_key)
            return value > 0
        except MonthlyPlan.DoesNotExist:
            return False

    def save(self, *args, **kwargs):
        """保存時にkeyとcard_idをIDベースで設定"""
        # 新規作成の場合、まず保存してIDを取得
        is_new = not self.pk
        if is_new:
            # keyを一時的に空にして保存（後でIDベースに更新）
            self.key = f'temp_{id(self)}'  # 一時的なユニークキー
            super().save(*args, **kwargs)
            # IDが確定したので、IDベースのkeyに更新
            self.key = f'item_{self.pk}'

            # クレジットカード項目の場合、card_idも自動生成
            updates = {'key': self.key}
            if self.is_credit_card() and not self.card_id:
                updates['card_id'] = f'card_{self.pk}'

            # update()を使ってsave()の無限ループを回避
            type(self).objects.filter(pk=self.pk).update(**updates)
        else:
            # 既存レコードの場合
            if not self.key or not self.key.startswith('item_'):
                # keyが空、または古い形式の場合、IDベースに更新
                self.key = f'item_{self.pk}'

            # クレジットカード項目でcard_idが未設定の場合、自動生成
            if self.is_credit_card() and not self.card_id:
                self.card_id = f'card_{self.pk}'

            super().save(*args, **kwargs)

