#!/usr/bin/env python
"""
ボーナス払いの修正スクリプト
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'future_budget_simulator.settings')
django.setup()

from budget_app.models import CreditEstimate
from datetime import date

def fix_invalid_bonus_payments():
    """対象外期間のボーナス払いを修正"""

    # すべてのボーナス払いを確認
    bonus_payments = CreditEstimate.objects.filter(is_bonus_payment=True).order_by('-created_at')

    print(f'=== ボーナス払い一覧 (最新10件) ===')
    for i, bp in enumerate(bonus_payments[:10]):
        print(f'{i+1}. ID: {bp.pk}')
        print(f'   内容: {bp.description}')
        print(f'   購入日: {bp.purchase_date}')
        print(f'   支払日: {bp.due_date}')
        print(f'   year_month: {bp.year_month}')
        print(f'   billing_month: {bp.billing_month}')

        # 対象外期間をチェック
        if bp.purchase_date:
            month = bp.purchase_date.month
            day = bp.purchase_date.day

            invalid = False
            if month == 6 and day >= 6:
                invalid = True
            elif month == 7 and day <= 5:
                invalid = True
            elif month == 11 and day >= 6:
                invalid = True
            elif month == 12 and day <= 5:
                invalid = True

            if invalid:
                print(f'   ⚠️ 対象外期間です!')
        print()

    print(f'\n合計: {bonus_payments.count()}件のボーナス払い')

if __name__ == '__main__':
    fix_invalid_bonus_payments()
