# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('budget_app', '0010_creditdefault'),
    ]

    operations = [
        # Add new fields
        migrations.AddField(
            model_name='monthlyplan',
            name='rakuten_card',
            field=models.IntegerField(default=0, verbose_name='楽天カード'),
        ),
        migrations.AddField(
            model_name='monthlyplan',
            name='paypay_card',
            field=models.IntegerField(default=0, verbose_name='PayPayカード'),
        ),
        # Remove old field
        migrations.RemoveField(
            model_name='monthlyplan',
            name='rakuten_paypay_card',
        ),
    ]
