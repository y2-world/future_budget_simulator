from django.db import migrations, models


def setup_standard_card(apps, schema_editor):
    MonthlyPlanDefault = apps.get_model('budget_app', 'MonthlyPlanDefault')
    CreditEstimate = apps.get_model('budget_app', 'CreditEstimate')

    # item_6: VIEWカード → VIEWカード ビックカメラ、linked_bonus_payment_type='bic_camera'
    item_6 = MonthlyPlanDefault.objects.filter(key='item_6').first()
    if item_6:
        item_6.title = 'VIEWカード ビックカメラ'
        item_6.linked_bonus_payment_type = 'bic_camera'
        item_6.save()

    # item_7: ボーナス払いビックカメラのタイトル更新
    MonthlyPlanDefault.objects.filter(key='item_7', is_bonus_payment=True).update(
        title='VIEWカード ボーナス払い【ビックカメラ】',
    )

    # スタンダードボーナス払いのタイトル更新
    MonthlyPlanDefault.objects.filter(
        is_bonus_payment=True, bonus_payment_type='standard'
    ).update(title='VIEWカード ボーナス払い【スタンダード】')

    # VIEWカード スタンダード（通常払い）を新規作成
    if item_6 and not MonthlyPlanDefault.objects.filter(
        is_bonus_payment=False, linked_bonus_payment_type='standard'
    ).exists():
        new_card = MonthlyPlanDefault.objects.create(
            title='VIEWカード スタンダード',
            key='temp_view_standard',
            amount=0,
            payment_type=item_6.payment_type,
            withdrawal_day=item_6.withdrawal_day,
            is_withdrawal_end_of_month=item_6.is_withdrawal_end_of_month,
            consider_holidays=item_6.consider_holidays,
            closing_day=item_6.closing_day,
            is_end_of_month=item_6.is_end_of_month,
            is_active=True,
            order=7,
            is_bonus_payment=False,
            linked_bonus_payment_type='standard',
        )
        new_key = f'item_{new_card.pk}'
        MonthlyPlanDefault.objects.filter(pk=new_card.pk).update(
            key=new_key,
            card_id=new_key,
        )
        # 既存のスタンダードボーナス払いCreditEstimateのcard_typeを更新
        CreditEstimate.objects.filter(
            is_bonus_payment=True,
            bonus_payment_type='standard',
            card_type='item_6',
        ).update(card_type=new_key)


def reverse_setup(apps, schema_editor):
    MonthlyPlanDefault = apps.get_model('budget_app', 'MonthlyPlanDefault')
    CreditEstimate = apps.get_model('budget_app', 'CreditEstimate')

    # スタンダードカードを削除する前にCreditEstimateをitem_6に戻す
    std_card = MonthlyPlanDefault.objects.filter(
        is_bonus_payment=False, linked_bonus_payment_type='standard'
    ).first()
    if std_card:
        CreditEstimate.objects.filter(card_type=std_card.key).update(card_type='item_6')
        std_card.delete()

    MonthlyPlanDefault.objects.filter(key='item_6').update(
        title='VIEWカード',
        linked_bonus_payment_type='',
    )
    MonthlyPlanDefault.objects.filter(key='item_7', is_bonus_payment=True).update(
        title='VIEWカード【ビックカメラボーナス払い】',
    )
    MonthlyPlanDefault.objects.filter(
        is_bonus_payment=True, bonus_payment_type='standard'
    ).update(title='VIEWカード【スタンダードボーナス払い】')


class Migration(migrations.Migration):

    dependencies = [
        ('budget_app', '0073_add_bonus_type_to_monthly_plan_default'),
    ]

    operations = [
        migrations.AddField(
            model_name='monthlyplandefault',
            name='linked_bonus_payment_type',
            field=models.CharField(
                blank=True,
                choices=[('bic_camera', 'ビックカメラ'), ('standard', 'スタンダード')],
                default='',
                help_text='このカードでボーナス払いを選択した際に使用するボーナス払い種別（通常払いカードのみ設定）',
                max_length=20,
                verbose_name='連携ボーナス払い種別',
            ),
        ),
        migrations.RunPython(setup_standard_card, reverse_setup),
    ]
