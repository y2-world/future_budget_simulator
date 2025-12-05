#!/usr/bin/env python
"""
ボーナス払いの修正スクリプト
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'future_budget_simulator.settings')
django.setup()

from budget_app.models import CreditEstimate
from budget_app.forms import get_bonus_due_date_from_purchase
from datetime import date

def fix_invalid_bonus_payments():
    """対象外期間のボーナス払いを修正"""

    # すべてのボーナス払いを確認
    bonus_payments = CreditEstimate.objects.filter(is_bonus_payment=True).order_by('-created_at')

    print(f'=== ボーナス払い一覧 (最新10件) ===')
    fixed_count = 0
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
                print(f'   ⚠️ 対象外期間です! 修正します...')

                # 12/5の場合は12/6に変更
                if month == 12 and day <= 5:
                    new_purchase_date = date(bp.purchase_date.year, 12, 6)
                    bp.purchase_date = new_purchase_date
                    bp.year_month = new_purchase_date.strftime('%Y-%m')

                    # 支払日を再計算
                    new_due_date = get_bonus_due_date_from_purchase(new_purchase_date)
                    if new_due_date:
                        bp.due_date = new_due_date
                        bp.billing_month = new_due_date.strftime('%Y-%m')
                        bp.save()
                        fixed_count += 1
                        print(f'   ✅ 修正完了: 購入日 {new_purchase_date}, 支払日 {new_due_date}')
                    else:
                        print(f'   ❌ エラー: 支払日が計算できませんでした')
                else:
                    print(f'   ℹ️ 自動修正できません（手動で修正してください）')
        print()

    print(f'\n合計: {bonus_payments.count()}件のボーナス払い')
    print(f'修正: {fixed_count}件')

if __name__ == '__main__':
    fix_invalid_bonus_payments()
