# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('budget_app', '0031_creditestimate_purchase_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='creditestimate',
            name='billing_month',
            field=models.CharField(blank=True, max_length=7, null=True, verbose_name='引き落とし月（YYYY-MM）'),
        ),
        migrations.AlterField(
            model_name='creditestimate',
            name='year_month',
            field=models.CharField(max_length=7, verbose_name='利用月（YYYY-MM）'),
        ),
    ]
