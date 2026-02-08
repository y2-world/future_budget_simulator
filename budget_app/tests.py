from django.test import TestCase, Client
from django.urls import reverse
from decimal import Decimal
from datetime import date, timedelta
from .models import (
    SimulationConfig,
    MonthlyPlan,
    CreditEstimate,
    MonthlyPlanDefault,
)
from .views import (
    get_card_plan,
    calculate_closing_date,
    calculate_billing_month,
    is_odd_month,
    get_active_defaults_ordered,
    get_active_card_defaults,
    get_card_by_key,
    get_cards_by_closing_day,
)


class HelperFunctionTests(TestCase):
    """ヘルパー関数のテスト"""

    def setUp(self):
        """テスト用のデータを作成"""
        # カード設定を作成
        self.card1 = MonthlyPlanDefault(
            title='楽天カード',
            card_id='card_1',
            is_active=True,
            closing_day=5,
            is_end_of_month=False,
            withdrawal_day=27,
            order=1
        )
        self.card1.save()
        # save()後にkeyを手動設定
        MonthlyPlanDefault.objects.filter(pk=self.card1.pk).update(key='card_1')
        self.card1.refresh_from_db()

        self.card2 = MonthlyPlanDefault(
            title='三井住友カード',
            card_id='card_2',
            is_active=True,
            closing_day=None,
            is_end_of_month=True,
            withdrawal_day=10,
            order=2
        )
        self.card2.save()
        MonthlyPlanDefault.objects.filter(pk=self.card2.pk).update(key='card_2')
        self.card2.refresh_from_db()

        self.inactive_card = MonthlyPlanDefault(
            title='無効なカード',
            card_id='card_3',
            is_active=False,
            closing_day=15,
            order=3
        )
        self.inactive_card.save()
        MonthlyPlanDefault.objects.filter(pk=self.inactive_card.pk).update(key='card_3')
        self.inactive_card.refresh_from_db()

    def test_get_card_plan(self):
        """get_card_plan関数のテスト"""
        # 有効なカードを取得
        card = get_card_plan('card_1')
        self.assertIsNotNone(card)
        self.assertEqual(card.title, '楽天カード')

        # 無効なカードは取得されない
        card = get_card_plan('card_3')
        self.assertIsNone(card)

    def test_calculate_closing_date(self):
        """calculate_closing_date関数のテスト"""
        # 指定日締め（5日締め）: year_month+1の5日
        closing = calculate_closing_date('2025-01', 'card_1')
        self.assertEqual(closing, date(2025, 2, 5))

        # 月末締め: year_monthの月末
        closing = calculate_closing_date('2025-02', 'card_2')
        self.assertEqual(closing, date(2025, 2, 28))

    def test_calculate_billing_month(self):
        """calculate_billing_month関数のテスト"""
        # 指定日締め（is_end_of_month=False）: +2ヶ月
        billing = calculate_billing_month('2025-01', 'card_1')
        self.assertEqual(billing, '2025-03')

        # 月末締め（is_end_of_month=True）: +1ヶ月
        billing = calculate_billing_month('2025-01', 'card_2')
        self.assertEqual(billing, '2025-02')

    def test_is_odd_month(self):
        """is_odd_month関数のテスト"""
        self.assertTrue(is_odd_month('2025-01'))
        self.assertFalse(is_odd_month('2025-02'))
        self.assertTrue(is_odd_month('2025-03'))

    def test_get_active_defaults_ordered(self):
        """get_active_defaults_ordered関数のテスト"""
        defaults = get_active_defaults_ordered()
        self.assertEqual(defaults.count(), 2)

    def test_get_active_card_defaults(self):
        """get_active_card_defaults関数のテスト"""
        cards = get_active_card_defaults()
        self.assertEqual(cards.count(), 2)

    def test_get_card_by_key(self):
        """get_card_by_key関数のテスト"""
        card = get_card_by_key('card_1')
        self.assertIsNotNone(card)
        self.assertEqual(card.title, '楽天カード')

    def test_get_cards_by_closing_day(self):
        """get_cards_by_closing_day関数のテスト"""
        cards = get_cards_by_closing_day(5)
        self.assertEqual(cards.count(), 1)


class MonthlyPlanModelTests(TestCase):
    """MonthlyPlanモデルのテスト"""

    def setUp(self):
        """テスト用のデータを作成"""
        self.plan = MonthlyPlan.objects.create(
            year_month='2025-01',
            gross_salary=300000,
            deductions=60000,
            transportation=10000,
            items={
                'rent': 80000,
                'utilities': 15000,
                'food': 30000,
            }
        )

    def test_get_item(self):
        """get_itemメソッドのテスト"""
        self.assertEqual(self.plan.get_item('rent'), 80000)
        self.assertEqual(self.plan.get_item('utilities'), 15000)
        self.assertEqual(self.plan.get_item('nonexistent'), 0)

    def test_get_total_income(self):
        """get_total_incomeメソッドのテスト"""
        # get_total_income()はMonthlyPlanDefaultのpayment_type='deposit'項目を探す
        # テストデータにはそのような項目がないため0が返る（正常）
        total = self.plan.get_total_income()
        self.assertEqual(total, 0)

    def test_str(self):
        """__str__メソッドのテスト"""
        self.assertEqual(str(self.plan), '2025-01')


class CreditEstimateModelTests(TestCase):
    """CreditEstimateモデルのテスト"""

    def setUp(self):
        """テスト用のデータを作成"""
        self.card = MonthlyPlanDefault(
            title='テストカード',
            card_id='test_card',
            is_active=True,
            order=1
        )
        self.card.save()
        MonthlyPlanDefault.objects.filter(pk=self.card.pk).update(key='test_card')

    def test_create_credit_estimate(self):
        """CreditEstimateの作成テスト"""
        estimate = CreditEstimate.objects.create(
            card_type='test_card',
            description='テスト購入',
            amount=10000,
            billing_month='2025-02'
        )
        self.assertEqual(estimate.description, 'テスト購入')
        self.assertEqual(estimate.amount, 10000)


class MonthlyPlanDefaultModelTests(TestCase):
    """MonthlyPlanDefaultモデルのテスト"""

    def test_create_default_item(self):
        """デフォルト項目の作成テスト"""
        item = MonthlyPlanDefault(
            title='家賃',
            amount=80000,
            is_active=True,
            order=1
        )
        item.save()
        self.assertEqual(item.title, '家賃')
        self.assertEqual(item.amount, 80000)

    def test_is_credit_card(self):
        """is_credit_cardメソッドのテスト"""
        # is_credit_card()はclosing_dayまたはis_end_of_monthが設定されているかで判定
        card = MonthlyPlanDefault(
            title='楽天カード',
            card_id='card_1',
            is_active=True,
            closing_day=5,  # これが設定されているのでTrue
            order=1
        )
        card.save()
        self.assertTrue(card.is_credit_card())

        item = MonthlyPlanDefault(
            title='家賃',
            is_active=True,
            order=2
            # closing_dayもis_end_of_monthも設定されていないのでFalse
        )
        item.save()
        self.assertFalse(item.is_credit_card())


class ViewTests(TestCase):
    """ビューのテスト"""

    def setUp(self):
        """テスト用のクライアントとデータを作成"""
        self.client = Client()
        self.config = SimulationConfig.objects.create(
            initial_balance=1000000,
            is_active=True,
            start_date=date.today(),
            simulation_months=12
        )
        self.plan = MonthlyPlan.objects.create(
            year_month='2025-02',
            gross_salary=300000,
            deductions=60000,
            transportation=10000
        )

    def test_plan_list_view(self):
        """月次計画一覧ビューのテスト"""
        response = self.client.get(reverse('budget_app:plan_list'))
        self.assertEqual(response.status_code, 200)

    def test_config_view_get(self):
        """設定ビュー（GET）のテスト"""
        response = self.client.get(reverse('budget_app:config'))
        self.assertEqual(response.status_code, 200)

    def test_plan_data_view(self):
        """月次計画データビューのテスト"""
        response = self.client.get(reverse('budget_app:plan_data', args=[self.plan.pk]))
        self.assertEqual(response.status_code, 200)
