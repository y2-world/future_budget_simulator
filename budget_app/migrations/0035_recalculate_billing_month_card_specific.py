# Generated manually

from django.db import migrations
from datetime import datetime


def calculate_billing_month(usage_month, card_type, split_part=None):
    """利用月から引き落とし月を計算（カード別）"""
    usage_date = datetime.strptime(usage_month, '%Y-%m')

    # カードごとの基本引き落とし期間
    if card_type in ['view', 'vermillion']:
        # 翌々月払い
        months_offset = 2
    else:
        # 翌月払い（楽天、PayPay、Amazon、Olive）
        months_offset = 1

    # 分割2回目の場合はさらに+1ヶ月
    if split_part == 2:
        months_offset += 1

    # 月を加算
    new_month = usage_date.month + months_offset
    new_year = usage_date.year
    while new_month > 12:
        new_month -= 12
        new_year += 1

    return f"{new_year}-{new_month:02d}"


def recalculate_billing_month(apps, schema_editor):
    """既存データのbilling_monthをカード別ロジックで再計算"""
    CreditEstimate = apps.get_model('budget_app', 'CreditEstimate')

    for estimate in CreditEstimate.objects.all():
        estimate.billing_month = calculate_billing_month(
            estimate.year_month,
            estimate.card_type,
            split_part=estimate.split_payment_part
        )
        estimate.save()


def reverse_recalculate(apps, schema_editor):
    """ロールバック（何もしない）"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('budget_app', '0034_fix_split_payment_year_month'),
    ]

    operations = [
        migrations.RunPython(recalculate_billing_month, reverse_recalculate),
    ]
