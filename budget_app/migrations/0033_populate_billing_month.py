# Generated manually

from django.db import migrations
from datetime import datetime


def calculate_billing_month(usage_month, split_part=None):
    """利用月から引き落とし月を計算"""
    usage_date = datetime.strptime(usage_month, '%Y-%m')

    # 基本: 翌々月（2ヶ月後）
    months_offset = 2

    # 分割2回目の場合はさらに+1ヶ月
    if split_part == 2:
        months_offset = 3

    # 月を加算
    new_month = usage_date.month + months_offset
    new_year = usage_date.year
    while new_month > 12:
        new_month -= 12
        new_year += 1

    return f"{new_year}-{new_month:02d}"


def populate_billing_month(apps, schema_editor):
    """既存データのbilling_monthを計算して設定"""
    CreditEstimate = apps.get_model('budget_app', 'CreditEstimate')

    for estimate in CreditEstimate.objects.all():
        estimate.billing_month = calculate_billing_month(
            estimate.year_month,
            split_part=estimate.split_payment_part
        )
        estimate.save()


def reverse_populate_billing_month(apps, schema_editor):
    """ロールバック時にbilling_monthをクリア"""
    CreditEstimate = apps.get_model('budget_app', 'CreditEstimate')
    CreditEstimate.objects.all().update(billing_month=None)


class Migration(migrations.Migration):

    dependencies = [
        ('budget_app', '0032_creditestimate_billing_month'),
    ]

    operations = [
        migrations.RunPython(populate_billing_month, reverse_populate_billing_month),
    ]
