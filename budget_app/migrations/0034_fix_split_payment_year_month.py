# Generated manually

from django.db import migrations


def fix_split_payment_year_month(apps, schema_editor):
    """既存の分割払いデータの利用月を統一"""
    CreditEstimate = apps.get_model('budget_app', 'CreditEstimate')

    # 分割払いグループごとに処理
    split_groups = CreditEstimate.objects.filter(
        is_split_payment=True,
        split_payment_group__isnull=False
    ).values_list('split_payment_group', flat=True).distinct()

    for group_id in split_groups:
        # グループ内のエントリーを取得
        entries = CreditEstimate.objects.filter(
            split_payment_group=group_id
        ).order_by('split_payment_part')

        if entries.count() == 2:
            first = entries[0]
            second = entries[1]

            # 2回目の利用月を1回目と同じにする
            if first.year_month != second.year_month:
                second.year_month = first.year_month
                second.save()


def reverse_fix(apps, schema_editor):
    """ロールバック（何もしない）"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('budget_app', '0033_populate_billing_month'),
    ]

    operations = [
        migrations.RunPython(fix_split_payment_year_month, reverse_fix),
    ]
