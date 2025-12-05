# Generated manually

from django.db import migrations


def fix_bonus_payment_purchase_date(apps, schema_editor):
    """
    purchase_dateがNullのボーナス払いを修正
    due_dateを購入日として扱い、実際の支払日を再計算
    """
    CreditEstimate = apps.get_model('budget_app', 'CreditEstimate')

    # purchase_dateがNullのボーナス払いを取得
    broken_bonus_payments = CreditEstimate.objects.filter(
        is_bonus_payment=True,
        purchase_date__isnull=True
    )

    for estimate in broken_bonus_payments:
        if estimate.due_date:
            # 現在のdue_dateを購入日として扱う
            estimate.purchase_date = estimate.due_date
            estimate.year_month = estimate.due_date.strftime('%Y-%m')

            # 実際の支払日を計算
            # ボーナス払いは夏（8月）または冬（1月）
            purchase_month = estimate.due_date.month
            purchase_year = estimate.due_date.year

            # 1-6月の購入 → 同年8月支払い
            # 7-12月の購入 → 翌年1月支払い
            if purchase_month <= 6:
                payment_month = 8
                payment_year = purchase_year
            else:
                payment_month = 1
                payment_year = purchase_year + 1

            # 支払日は4日（VIEWカードの引き落とし日）
            from datetime import date
            estimate.due_date = date(payment_year, payment_month, 4)
            estimate.billing_month = f"{payment_year}-{payment_month:02d}"

            estimate.save()
            print(f"Fixed bonus payment {estimate.id}: {estimate.description}")


def reverse_fix(apps, schema_editor):
    """ロールバック（何もしない）"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('budget_app', '0036_fix_bonus_payment_billing_month'),
    ]

    operations = [
        migrations.RunPython(fix_bonus_payment_purchase_date, reverse_fix),
    ]
