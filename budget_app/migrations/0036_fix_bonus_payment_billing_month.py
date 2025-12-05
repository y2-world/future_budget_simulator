# Generated manually

from django.db import migrations


def fix_bonus_payment_billing_month(apps, schema_editor):
    """ボーナス払いのbilling_monthをdue_dateから設定"""
    CreditEstimate = apps.get_model('budget_app', 'CreditEstimate')

    for estimate in CreditEstimate.objects.filter(is_bonus_payment=True):
        # ボーナス払いの場合、billing_monthはdue_date（支払日）の月
        if estimate.due_date:
            estimate.billing_month = estimate.due_date.strftime('%Y-%m')
            estimate.save()


def reverse_fix(apps, schema_editor):
    """ロールバック（何もしない）"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('budget_app', '0035_recalculate_billing_month_card_specific'),
    ]

    operations = [
        migrations.RunPython(fix_bonus_payment_billing_month, reverse_fix),
    ]
