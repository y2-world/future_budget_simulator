# Generated manually on 2026-01-09

from django.db import migrations


def fix_card_settings(apps, schema_editor):
    """
    VIEWカードとVERMILLIONカードの設定を修正

    VIEWカード (item_6):
    - offset_months: 2 → 1 (5日締め、翌月払い)
    例: 1/1利用 → 1/5締め → 2月払い

    VERMILLIONカード (item_10):
    - closing_day: 5 → 10 (10日締め)
    - offset_months: 2 → 1 (翌月払い)
    例: 1/9利用 → 1/10締め → 2月払い
    """
    MonthlyPlanDefault = apps.get_model('budget_app', 'MonthlyPlanDefault')

    # VIEWカードの設定を修正
    view_card = MonthlyPlanDefault.objects.filter(key='item_6').first()
    if view_card:
        view_card.offset_months = 1
        view_card.save()
        print(f"Updated VIEW card: offset_months=1")

    # VERMILLIONカードの設定を修正
    vermillion_card = MonthlyPlanDefault.objects.filter(key='item_10').first()
    if vermillion_card:
        vermillion_card.closing_day = 10
        vermillion_card.offset_months = 1
        vermillion_card.save()
        print(f"Updated VERMILLION card: closing_day=10, offset_months=1")


def reverse_card_settings(apps, schema_editor):
    """設定を元に戻す"""
    MonthlyPlanDefault = apps.get_model('budget_app', 'MonthlyPlanDefault')

    # VIEWカードの設定を元に戻す
    view_card = MonthlyPlanDefault.objects.filter(key='item_6').first()
    if view_card:
        view_card.offset_months = 2
        view_card.save()

    # VERMILLIONカードの設定を元に戻す
    vermillion_card = MonthlyPlanDefault.objects.filter(key='item_10').first()
    if vermillion_card:
        vermillion_card.closing_day = 5
        vermillion_card.offset_months = 2
        vermillion_card.save()


class Migration(migrations.Migration):

    dependencies = [
        ('budget_app', '0064_fix_vermillion_card_settings'),
    ]

    operations = [
        migrations.RunPython(fix_card_settings, reverse_card_settings),
    ]
