# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('budget_app', '0030_defaultchargeoverride_is_split_payment'),
    ]

    operations = [
        migrations.AddField(
            model_name='creditestimate',
            name='purchase_date',
            field=models.DateField(blank=True, help_text='ボーナス払いの場合、購入日を入力', null=True, verbose_name='購入日'),
        ),
    ]
