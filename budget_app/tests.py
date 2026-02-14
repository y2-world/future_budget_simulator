from django.test import TestCase, Client
from django.urls import reverse
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch
from .models import (
    SimulationConfig,
    MonthlyPlan,
    CreditEstimate,
    CreditDefault,
    DefaultChargeOverride,
    MonthlyPlanDefault,
)
from .views import (
    get_card_plan,
    calculate_closing_date,
    calculate_billing_month,
    calculate_billing_month_for_purchase,
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


class CreditCardLogicTests(TestCase):
    """クレジットカード処理の詳細テスト"""

    def setUp(self):
        """テスト用のカード設定を作成"""
        # 5日締め翌々月27日払いカード（楽天カード想定）
        self.rakuten_card = MonthlyPlanDefault(
            title='楽天カード',
            card_id='rakuten',
            is_active=True,
            closing_day=5,
            is_end_of_month=False,
            withdrawal_day=27,
            order=1
        )
        self.rakuten_card.save()
        MonthlyPlanDefault.objects.filter(pk=self.rakuten_card.pk).update(key='rakuten')
        self.rakuten_card.refresh_from_db()

        # 月末締め翌月10日払いカード（三井住友カード想定）
        self.smbc_card = MonthlyPlanDefault(
            title='三井住友カード',
            card_id='smbc',
            is_active=True,
            closing_day=None,
            is_end_of_month=True,
            withdrawal_day=10,
            order=2
        )
        self.smbc_card.save()
        MonthlyPlanDefault.objects.filter(pk=self.smbc_card.pk).update(key='smbc')
        self.smbc_card.refresh_from_db()

        # 15日締め翌月10日払いカード（VIEWカード想定）
        self.view_card = MonthlyPlanDefault(
            title='VIEWカード',
            card_id='view',
            is_active=True,
            closing_day=15,
            is_end_of_month=False,
            withdrawal_day=4,
            order=3
        )
        self.view_card.save()
        MonthlyPlanDefault.objects.filter(pk=self.view_card.pk).update(key='view')
        self.view_card.refresh_from_db()

    def test_closing_date_calculation_various_cards(self):
        """様々なカードの締め日計算テスト"""
        # 楽天カード（5日締め）: 2025-01 → 2025-02-05
        closing = calculate_closing_date('2025-01', 'rakuten')
        self.assertEqual(closing, date(2025, 2, 5))

        # 三井住友カード（月末締め）: 2025-01 → 2025-01-31
        closing = calculate_closing_date('2025-01', 'smbc')
        self.assertEqual(closing, date(2025, 1, 31))

        # VIEWカード（15日締め）: 2025-01 → 2025-02-15
        closing = calculate_closing_date('2025-01', 'view')
        self.assertEqual(closing, date(2025, 2, 15))

        # 2月の月末締め: 2025-02 → 2025-02-28
        closing = calculate_closing_date('2025-02', 'smbc')
        self.assertEqual(closing, date(2025, 2, 28))

    def test_billing_month_calculation_various_cards(self):
        """様々なカードの引き落とし月計算テスト"""
        # 楽天カード（指定日締め）: 利用月+2ヶ月
        billing = calculate_billing_month('2025-01', 'rakuten')
        self.assertEqual(billing, '2025-03')

        billing = calculate_billing_month('2025-11', 'rakuten')
        self.assertEqual(billing, '2026-01')  # 年をまたぐケース

        # 三井住友カード（月末締め）: 利用月+1ヶ月
        billing = calculate_billing_month('2025-01', 'smbc')
        self.assertEqual(billing, '2025-02')

        billing = calculate_billing_month('2025-12', 'smbc')
        self.assertEqual(billing, '2026-01')  # 年をまたぐケース

        # VIEWカード（15日締め）: 利用月+2ヶ月
        billing = calculate_billing_month('2025-01', 'view')
        self.assertEqual(billing, '2025-03')

    def test_split_payment_billing_month(self):
        """分割払いの引き落とし月計算テスト"""
        # 楽天カード 2回払い
        # 1回目: 2025-01 → 2025-03
        billing_1st = calculate_billing_month('2025-01', 'rakuten', split_part=1)
        self.assertEqual(billing_1st, '2025-03')

        # 2回目: 2025-01 → 2025-04
        billing_2nd = calculate_billing_month('2025-01', 'rakuten', split_part=2)
        self.assertEqual(billing_2nd, '2025-04')

        # 年をまたぐケース
        billing_1st = calculate_billing_month('2025-11', 'rakuten', split_part=1)
        self.assertEqual(billing_1st, '2026-01')

        billing_2nd = calculate_billing_month('2025-11', 'rakuten', split_part=2)
        self.assertEqual(billing_2nd, '2026-02')

    def test_year_boundary_cases(self):
        """年またぎのエッジケーステスト"""
        # 12月の処理
        closing = calculate_closing_date('2025-12', 'rakuten')
        self.assertEqual(closing, date(2026, 1, 5))

        billing = calculate_billing_month('2025-12', 'rakuten')
        self.assertEqual(billing, '2026-02')

        # 11月から年をまたぐケース
        billing = calculate_billing_month('2025-11', 'rakuten')
        self.assertEqual(billing, '2026-01')

    def test_credit_estimate_creation(self):
        """クレジット見積もりの作成テスト"""
        estimate = CreditEstimate.objects.create(
            card_type='rakuten',
            description='テスト購入',
            amount=10000,
            billing_month='2025-03',
            is_split_payment=False,
            is_bonus_payment=False
        )
        self.assertEqual(estimate.card_type, 'rakuten')
        self.assertEqual(estimate.amount, 10000)
        self.assertFalse(estimate.is_split_payment)
        self.assertFalse(estimate.is_bonus_payment)

    def test_split_payment_estimate(self):
        """分割払い見積もりのテスト"""
        # 2回払いの見積もり（1回目）
        estimate1 = CreditEstimate.objects.create(
            card_type='rakuten',
            description='高額商品',
            amount=20000,  # 1回あたりの金額
            billing_month='2025-03',
            is_split_payment=True,
            split_payment_part=1,
            split_payment_group='test_group_1'
        )
        self.assertTrue(estimate1.is_split_payment)
        self.assertEqual(estimate1.split_payment_part, 1)
        self.assertEqual(estimate1.split_payment_group, 'test_group_1')

        # 2回払いの見積もり（2回目）
        estimate2 = CreditEstimate.objects.create(
            card_type='rakuten',
            description='高額商品',
            amount=20000,
            billing_month='2025-04',
            is_split_payment=True,
            split_payment_part=2,
            split_payment_group='test_group_1'
        )
        self.assertEqual(estimate2.split_payment_part, 2)
        self.assertEqual(estimate2.split_payment_group, 'test_group_1')

    def test_bonus_payment_estimate(self):
        """ボーナス払い見積もりのテスト"""
        estimate = CreditEstimate.objects.create(
            card_type='rakuten',
            description='ボーナス一括',
            amount=50000,
            billing_month='2025-07',  # 夏のボーナス月
            is_bonus_payment=True
        )
        self.assertTrue(estimate.is_bonus_payment)

    def test_usd_payment_estimate(self):
        """ドル建て決済のテスト"""
        estimate = CreditEstimate.objects.create(
            card_type='rakuten',
            description='海外通販',
            amount=15000,  # 円換算後
            billing_month='2025-03',
            is_usd=True,
            usd_amount=Decimal('100.00')
        )
        self.assertTrue(estimate.is_usd)
        self.assertEqual(estimate.usd_amount, Decimal('100.00'))
        # 円換算された金額も保存される
        self.assertEqual(estimate.amount, 15000)


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


class BillingMonthForPurchaseTests(TestCase):
    """purchase_dateベースのbilling_month計算テスト（カード変更対応）"""

    def setUp(self):
        """テスト用カード設定"""
        # VIEWカード: 5日締め、翌々月4日払い
        self.view_card = MonthlyPlanDefault(
            title='VIEWカード',
            card_id='view_card',
            is_active=True,
            closing_day=5,
            is_end_of_month=False,
            withdrawal_day=4,
            order=1
        )
        self.view_card.save()
        MonthlyPlanDefault.objects.filter(pk=self.view_card.pk).update(key='view_card')
        self.view_card.refresh_from_db()

        # 楽天カード: 月末締め、翌月27日払い
        self.rakuten_card = MonthlyPlanDefault(
            title='楽天カード',
            card_id='rakuten_card',
            is_active=True,
            closing_day=None,
            is_end_of_month=True,
            withdrawal_day=27,
            order=2
        )
        self.rakuten_card.save()
        MonthlyPlanDefault.objects.filter(pk=self.rakuten_card.pk).update(key='rakuten_card')
        self.rakuten_card.refresh_from_db()

        # VERMILLIONカード: 10日締め、翌月10日払い
        self.vermillion_card = MonthlyPlanDefault(
            title='VERMILLION CARD',
            card_id='vermillion_card',
            is_active=True,
            closing_day=10,
            is_end_of_month=False,
            withdrawal_day=10,
            order=3
        )
        self.vermillion_card.save()
        MonthlyPlanDefault.objects.filter(pk=self.vermillion_card.pk).update(key='vermillion_card')
        self.vermillion_card.refresh_from_db()

        # PayPayカード: 月末締め、翌月27日払い
        self.paypay_card = MonthlyPlanDefault(
            title='PayPayカード',
            card_id='paypay_card',
            is_active=True,
            closing_day=None,
            is_end_of_month=True,
            withdrawal_day=27,
            order=4
        )
        self.paypay_card.save()
        MonthlyPlanDefault.objects.filter(pk=self.paypay_card.pk).update(key='paypay_card')
        self.paypay_card.refresh_from_db()

    # ========================================
    # VIEWカード（5日締め）の基本テスト
    # ========================================
    def test_view_card_payment_day_before_closing(self):
        """VIEW(5日締め): 利用日4日 ≤ 締め日5日 → 翌月払い"""
        # 1/4利用 → 1/5締めに入る → 2月払い
        self.assertEqual(
            calculate_billing_month_for_purchase(4, '2026-01', 'view_card'),
            '2026-02'
        )
        # 3/4利用 → 3/5締めに入る → 4月払い
        self.assertEqual(
            calculate_billing_month_for_purchase(4, '2026-03', 'view_card'),
            '2026-04'
        )

    def test_view_card_payment_day_on_closing(self):
        """VIEW(5日締め): 利用日5日 = 締め日5日 → 翌月払い"""
        # 1/5利用 → 1/5締めに入る → 2月払い
        self.assertEqual(
            calculate_billing_month_for_purchase(5, '2026-01', 'view_card'),
            '2026-02'
        )

    def test_view_card_payment_day_after_closing(self):
        """VIEW(5日締め): 利用日10日 > 締め日5日 → 翌々月払い"""
        # 1/10利用 → 2/5締めに入る → 3月払い
        self.assertEqual(
            calculate_billing_month_for_purchase(10, '2026-01', 'view_card'),
            '2026-03'
        )
        # 1/24利用 → 2/5締めに入る → 3月払い
        self.assertEqual(
            calculate_billing_month_for_purchase(24, '2026-01', 'view_card'),
            '2026-03'
        )

    # ========================================
    # 楽天カード（月末締め）の基本テスト
    # ========================================
    def test_rakuten_card_any_payment_day(self):
        """楽天(月末締め): どの利用日でも当月末締め → 翌月払い"""
        # 1/4利用 → 1/31締め → 2月払い
        self.assertEqual(
            calculate_billing_month_for_purchase(4, '2026-01', 'rakuten_card'),
            '2026-02'
        )
        # 1/15利用 → 1/31締め → 2月払い
        self.assertEqual(
            calculate_billing_month_for_purchase(15, '2026-01', 'rakuten_card'),
            '2026-02'
        )
        # 1/28利用 → 1/31締め → 2月払い
        self.assertEqual(
            calculate_billing_month_for_purchase(28, '2026-01', 'rakuten_card'),
            '2026-02'
        )

    # ========================================
    # VERMILLIONカード（10日締め）の基本テスト
    # ========================================
    def test_vermillion_card_before_closing(self):
        """VERMILLION(10日締め): 利用日4日 ≤ 10日 → 翌月払い"""
        self.assertEqual(
            calculate_billing_month_for_purchase(4, '2026-01', 'vermillion_card'),
            '2026-02'
        )

    def test_vermillion_card_on_closing(self):
        """VERMILLION(10日締め): 利用日10日 = 10日 → 翌月払い"""
        self.assertEqual(
            calculate_billing_month_for_purchase(10, '2026-01', 'vermillion_card'),
            '2026-02'
        )

    def test_vermillion_card_after_closing(self):
        """VERMILLION(10日締め): 利用日15日 > 10日 → 翌々月払い"""
        self.assertEqual(
            calculate_billing_month_for_purchase(15, '2026-01', 'vermillion_card'),
            '2026-03'
        )

    # ========================================
    # カード変更時のテスト（メイン修正対象）
    # ========================================
    def test_card_change_view_to_rakuten_payment_day_4(self):
        """VIEW→楽天 (payment_day=4): 3/4利用 → 楽天3月末締め → 4月払い"""
        # VIEWのまま: 3/4利用 → 3/5締め → 4月払い(4/4)
        self.assertEqual(
            calculate_billing_month_for_purchase(4, '2026-03', 'view_card'),
            '2026-04'
        )
        # 楽天に変更: 3/4利用 → 3/31締め → 4月払い(4/27)
        self.assertEqual(
            calculate_billing_month_for_purchase(4, '2026-03', 'rakuten_card'),
            '2026-04'
        )

    def test_card_change_view_to_rakuten_payment_day_24(self):
        """VIEW→楽天 (payment_day=24): 支払月が変わるケース"""
        # VIEWのまま: 1/24利用 → 24>5 → 翌々月 → 3月払い(3/4)
        self.assertEqual(
            calculate_billing_month_for_purchase(24, '2026-01', 'view_card'),
            '2026-03'
        )
        # 楽天に変更: 1/24利用 → 1/31締め → 2月払い(2/27)
        self.assertEqual(
            calculate_billing_month_for_purchase(24, '2026-01', 'rakuten_card'),
            '2026-02'
        )

    def test_card_change_rakuten_to_view_payment_day_4(self):
        """楽天→VIEW (payment_day=4)"""
        # 楽天: 3/4利用 → 3月末締め → 4月払い
        self.assertEqual(
            calculate_billing_month_for_purchase(4, '2026-03', 'rakuten_card'),
            '2026-04'
        )
        # VIEWに変更: 3/4利用 → 3/5締め → 4月払い
        self.assertEqual(
            calculate_billing_month_for_purchase(4, '2026-03', 'view_card'),
            '2026-04'
        )

    def test_card_change_rakuten_to_view_payment_day_10(self):
        """楽天→VIEW (payment_day=10): 支払月が変わるケース"""
        # 楽天: 3/10利用 → 3月末締め → 4月払い
        self.assertEqual(
            calculate_billing_month_for_purchase(10, '2026-03', 'rakuten_card'),
            '2026-04'
        )
        # VIEWに変更: 3/10利用 → 10>5 → 翌々月 → 5月払い
        self.assertEqual(
            calculate_billing_month_for_purchase(10, '2026-03', 'view_card'),
            '2026-05'
        )

    def test_card_change_view_to_vermillion_payment_day_4(self):
        """VIEW→VERMILLION (payment_day=4): 両方締め日前 → 同じ月"""
        # VIEW: 1/4 ≤ 5 → 2月
        self.assertEqual(
            calculate_billing_month_for_purchase(4, '2026-01', 'view_card'),
            '2026-02'
        )
        # VERMILLION: 1/4 ≤ 10 → 2月
        self.assertEqual(
            calculate_billing_month_for_purchase(4, '2026-01', 'vermillion_card'),
            '2026-02'
        )

    def test_card_change_view_to_vermillion_payment_day_7(self):
        """VIEW→VERMILLION (payment_day=7): VIEWは翌々月、VERMILLIONは翌月"""
        # VIEW: 1/7 > 5 → 3月
        self.assertEqual(
            calculate_billing_month_for_purchase(7, '2026-01', 'view_card'),
            '2026-03'
        )
        # VERMILLION: 1/7 ≤ 10 → 2月
        self.assertEqual(
            calculate_billing_month_for_purchase(7, '2026-01', 'vermillion_card'),
            '2026-02'
        )

    # ========================================
    # 年またぎテスト
    # ========================================
    def test_year_boundary_view_card(self):
        """VIEW(5日締め) 年またぎ: 11月・12月利用"""
        # 11/10利用 → 10>5 → 翌々月 → 1月(翌年)
        self.assertEqual(
            calculate_billing_month_for_purchase(10, '2025-11', 'view_card'),
            '2026-01'
        )
        # 12/4利用 → 4≤5 → 翌月 → 1月(翌年)
        self.assertEqual(
            calculate_billing_month_for_purchase(4, '2025-12', 'view_card'),
            '2026-01'
        )
        # 12/10利用 → 10>5 → 翌々月 → 2月(翌年)
        self.assertEqual(
            calculate_billing_month_for_purchase(10, '2025-12', 'view_card'),
            '2026-02'
        )

    def test_year_boundary_rakuten_card(self):
        """楽天(月末締め) 年またぎ: 12月利用 → 1月払い"""
        self.assertEqual(
            calculate_billing_month_for_purchase(15, '2025-12', 'rakuten_card'),
            '2026-01'
        )

    # ========================================
    # 2月（短い月）のエッジケース
    # ========================================
    def test_february_payment_day_29(self):
        """2月にpayment_day=29の場合、28日にクランプ"""
        # 2026年は平年なので2/28が最大
        # VIEW: 28>5 → 翌々月 → 4月
        self.assertEqual(
            calculate_billing_month_for_purchase(29, '2026-02', 'view_card'),
            '2026-04'
        )
        # 楽天: 月末締め → 3月
        self.assertEqual(
            calculate_billing_month_for_purchase(29, '2026-02', 'rakuten_card'),
            '2026-03'
        )

    def test_february_leap_year(self):
        """うるう年の2月: payment_day=29 → 29日のまま"""
        # 2028年はうるう年
        # VIEW: 29>5 → 翌々月 → 4月
        self.assertEqual(
            calculate_billing_month_for_purchase(29, '2028-02', 'view_card'),
            '2028-04'
        )

    def test_payment_day_31_in_short_month(self):
        """payment_day=31の場合、30日の月でクランプ"""
        # 4月(30日まで): payment_day=31 → 30日
        # VIEW: 30>5 → 翌々月 → 6月
        self.assertEqual(
            calculate_billing_month_for_purchase(31, '2026-04', 'view_card'),
            '2026-06'
        )


class DefaultChargeUpdateScopeTests(TestCase):
    """定期デフォルト変更時の適用範囲テスト（利用日ベース）"""

    def setUp(self):
        """テスト用カードと定期デフォルトを作成"""
        self.view_card = MonthlyPlanDefault(
            title='VIEWカード',
            card_id='view_card',
            is_active=True,
            closing_day=5,
            is_end_of_month=False,
            withdrawal_day=4,
            order=1
        )
        self.view_card.save()
        MonthlyPlanDefault.objects.filter(pk=self.view_card.pk).update(key='view_card')

        self.rakuten_card = MonthlyPlanDefault(
            title='楽天カード',
            card_id='rakuten_card',
            is_active=True,
            closing_day=None,
            is_end_of_month=True,
            withdrawal_day=27,
            order=2
        )
        self.rakuten_card.save()
        MonthlyPlanDefault.objects.filter(pk=self.rakuten_card.pk).update(key='rakuten_card')

        # 定期デフォルト: Heroku (payment_day=4, VIEW)
        self.heroku = CreditDefault.objects.create(
            key='heroku_test',
            label='Heroku',
            card_type='view_card',
            amount=1728,
            payment_day=4,
            is_active=True,
        )

        # 各月のoverideを作成
        for ym in ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05']:
            DefaultChargeOverride.objects.create(
                default=self.heroku,
                year_month=ym,
                amount=1728,
                card_type='view_card',
            )

    @patch('budget_app.views.timezone')
    def test_update_only_future_purchase_dates(self, mock_timezone):
        """カード変更は利用日が今日より後のoverrideのみ更新"""
        from django.utils import timezone as real_tz
        import datetime

        # 今日を2026-02-14に固定
        mock_now = real_tz.now()
        mock_timezone.now.return_value = datetime.datetime(2026, 2, 14, 12, 0, 0,
                                                            tzinfo=datetime.timezone.utc)

        client = Client()
        # payment_day=4なので:
        # 2026-01: 1/4 → 過去 → 変更しない
        # 2026-02: 2/4 → 過去 → 変更しない
        # 2026-03: 3/4 → 未来 → 変更する
        # 2026-04: 4/4 → 未来 → 変更する
        # 2026-05: 5/4 → 未来 → 変更する

        response = client.post(
            reverse('budget_app:credit_defaults'),
            {
                'action': 'update',
                'id': self.heroku.pk,
                'label': 'Heroku',
                'card_type': 'rakuten_card',
                'amount': '1728',
                'payment_day': '4',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        self.assertEqual(response.status_code, 200)

        # 過去の利用月は変更されていないことを確認
        ov_01 = DefaultChargeOverride.objects.get(default=self.heroku, year_month='2026-01')
        self.assertEqual(ov_01.card_type, 'view_card', '1/4は過去なので変更しない')

        ov_02 = DefaultChargeOverride.objects.get(default=self.heroku, year_month='2026-02')
        self.assertEqual(ov_02.card_type, 'view_card', '2/4は過去なので変更しない')

        # 未来の利用月は変更されていることを確認
        ov_03 = DefaultChargeOverride.objects.get(default=self.heroku, year_month='2026-03')
        self.assertEqual(ov_03.card_type, 'rakuten_card', '3/4は未来なので変更する')

        ov_04 = DefaultChargeOverride.objects.get(default=self.heroku, year_month='2026-04')
        self.assertEqual(ov_04.card_type, 'rakuten_card', '4/4は未来なので変更する')

        ov_05 = DefaultChargeOverride.objects.get(default=self.heroku, year_month='2026-05')
        self.assertEqual(ov_05.card_type, 'rakuten_card', '5/4は未来なので変更する')

    @patch('budget_app.views.timezone')
    def test_manual_override_not_overwritten(self, mock_timezone):
        """手動で金額変更済みのoverrideは上書きしない"""
        import datetime

        mock_timezone.now.return_value = datetime.datetime(2026, 2, 14, 12, 0, 0,
                                                            tzinfo=datetime.timezone.utc)

        # 2026-04のoverrideを手動で金額変更
        ov_04 = DefaultChargeOverride.objects.get(default=self.heroku, year_month='2026-04')
        ov_04.amount = 999
        ov_04.save()

        client = Client()
        response = client.post(
            reverse('budget_app:credit_defaults'),
            {
                'action': 'update',
                'id': self.heroku.pk,
                'label': 'Heroku',
                'card_type': 'view_card',
                'amount': '2000',  # 1728→2000に変更
                'payment_day': '4',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        self.assertEqual(response.status_code, 200)

        # 手動変更済みの2026-04は金額が変わらない（元の金額1728と異なるため）
        ov_04.refresh_from_db()
        self.assertEqual(ov_04.amount, 999, '手動変更済みは上書きしない')

        # 2026-03は元の金額1728のまま → 2000に更新される
        ov_03 = DefaultChargeOverride.objects.get(default=self.heroku, year_month='2026-03')
        self.assertEqual(ov_03.amount, 2000, '未変更のoverrideは更新する')

    @patch('budget_app.views.timezone')
    def test_payment_day_24_update_scope(self, mock_timezone):
        """payment_day=24の場合: 2/24は未来(2/14基準)なので更新対象"""
        import datetime

        mock_timezone.now.return_value = datetime.datetime(2026, 2, 14, 12, 0, 0,
                                                            tzinfo=datetime.timezone.utc)

        # NTTっぽい定期デフォルト (payment_day=24)
        ntt = CreditDefault.objects.create(
            key='ntt_test',
            label='NTT',
            card_type='view_card',
            amount=5170,
            payment_day=24,
            is_active=True,
        )
        for ym in ['2026-01', '2026-02', '2026-03']:
            DefaultChargeOverride.objects.create(
                default=ntt, year_month=ym, amount=5170, card_type='view_card',
            )

        client = Client()
        response = client.post(
            reverse('budget_app:credit_defaults'),
            {
                'action': 'update',
                'id': ntt.pk,
                'label': 'NTT',
                'card_type': 'rakuten_card',
                'amount': '5170',
                'payment_day': '24',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        self.assertEqual(response.status_code, 200)

        # 1/24は過去 → 変更しない
        ov_01 = DefaultChargeOverride.objects.get(default=ntt, year_month='2026-01')
        self.assertEqual(ov_01.card_type, 'view_card')

        # 2/24は未来（今日は2/14）→ 変更する
        ov_02 = DefaultChargeOverride.objects.get(default=ntt, year_month='2026-02')
        self.assertEqual(ov_02.card_type, 'rakuten_card')

        # 3/24は未来 → 変更する
        ov_03 = DefaultChargeOverride.objects.get(default=ntt, year_month='2026-03')
        self.assertEqual(ov_03.card_type, 'rakuten_card')


class CardChangeBillingSimulationTests(TestCase):
    """カード変更時のbilling_month計算の統合テスト（実際のデータフロー）"""

    def setUp(self):
        """実際のカード設定に近いテストデータ"""
        # VIEW: 5日締め、4日払い
        self.view_card = MonthlyPlanDefault(
            title='VIEWカード', card_id='view_card', is_active=True,
            closing_day=5, is_end_of_month=False, withdrawal_day=4, order=1
        )
        self.view_card.save()
        MonthlyPlanDefault.objects.filter(pk=self.view_card.pk).update(key='view_card')

        # 楽天: 月末締め、27日払い
        self.rakuten_card = MonthlyPlanDefault(
            title='楽天カード', card_id='rakuten_card', is_active=True,
            closing_day=None, is_end_of_month=True, withdrawal_day=27, order=2
        )
        self.rakuten_card.save()
        MonthlyPlanDefault.objects.filter(pk=self.rakuten_card.pk).update(key='rakuten_card')

    def test_heroku_view_to_rakuten_full_simulation(self):
        """Heroku(payment_day=4)をVIEW→楽天に変更した場合のフルシミュレーション

        期待動作:
        - 利用月2026-01(VIEW): 1/4 ≤ 5日 → 2月払い(2/4) [変更前のまま]
        - 利用月2026-02(VIEW): 2/4 ≤ 5日 → 3月払い(3/4) [変更前のまま]
        - 利用月2026-03(楽天): 3/4 → 月末締め → 4月払い(4/27)
        - 利用月2026-04(楽天): 4/4 → 月末締め → 5月払い(5/27)
        """
        test_cases = [
            # (payment_day, year_month, card_type, expected_billing)
            (4, '2026-01', 'view_card', '2026-02'),     # 変更前
            (4, '2026-02', 'view_card', '2026-03'),     # 変更前
            (4, '2026-03', 'rakuten_card', '2026-04'),  # 変更後
            (4, '2026-04', 'rakuten_card', '2026-05'),  # 変更後
            (4, '2026-05', 'rakuten_card', '2026-06'),  # 変更後
        ]

        billing_months = []
        for payment_day, ym, card, expected in test_cases:
            result = calculate_billing_month_for_purchase(payment_day, ym, card)
            self.assertEqual(result, expected,
                f'payment_day={payment_day} ym={ym} card={card}: '
                f'expected={expected} got={result}')
            billing_months.append(result)

        # 重複チェック: 同じbilling_monthに2つ入らない
        self.assertEqual(len(billing_months), len(set(billing_months)),
            f'billing_monthに重複あり: {billing_months}')

    def test_ntt_view_to_rakuten_full_simulation(self):
        """NTT(payment_day=24)をVIEW→楽天に変更した場合

        期待動作:
        - 利用月2026-01(VIEW): 1/24 > 5日 → 3月払い(3/4) [変更前]
        - 利用月2026-02(VIEW): 2/24 > 5日 → 4月払い(4/4) [変更前]
        - 利用月2026-03(楽天): 3/24 → 月末締め → 4月払い(4/27) [変更後]
        ※ 4月に2つ（VIEW 4/4とrakuten 4/27）が入るのは正常（別カード）
        """
        test_cases = [
            (24, '2026-01', 'view_card', '2026-03'),
            (24, '2026-02', 'view_card', '2026-04'),
            (24, '2026-03', 'rakuten_card', '2026-04'),  # 4月に2つ目
            (24, '2026-04', 'rakuten_card', '2026-05'),
        ]

        for payment_day, ym, card, expected in test_cases:
            result = calculate_billing_month_for_purchase(payment_day, ym, card)
            self.assertEqual(result, expected,
                f'payment_day={payment_day} ym={ym} card={card}: '
                f'expected={expected} got={result}')

    def test_claude_view_to_rakuten_full_simulation(self):
        """Claude(payment_day=28)をVIEW→楽天に変更

        期待動作:
        - VIEW: 28 > 5 → 翌々月
        - 楽天: 月末締め → 翌月
        """
        test_cases = [
            (28, '2026-01', 'view_card', '2026-03'),
            (28, '2026-02', 'view_card', '2026-04'),
            (28, '2026-03', 'rakuten_card', '2026-04'),
            (28, '2026-04', 'rakuten_card', '2026-05'),
        ]

        for payment_day, ym, card, expected in test_cases:
            result = calculate_billing_month_for_purchase(payment_day, ym, card)
            self.assertEqual(result, expected,
                f'payment_day={payment_day} ym={ym} card={card}: '
                f'expected={expected} got={result}')
