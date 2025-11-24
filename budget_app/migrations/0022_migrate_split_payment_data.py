# Generated migration to migrate existing split payment data

from django.db import migrations
import uuid


def migrate_split_payment_data(apps, schema_editor):
    """既存の分割払いデータを新しいフィールド形式に移行

    descriptionに「(分割1回目)」「(分割2回目)」が含まれるデータを、
    新しいsplit_payment_part（1 or 2）フィールドに移行し、
    descriptionからは括弧書きを削除する
    """
    CreditEstimate = apps.get_model('budget_app', 'CreditEstimate')

    # descriptionに「(分割1回目)」または「(分割2回目)」が含まれるエントリーを取得
    all_estimates = CreditEstimate.objects.filter(
        description__icontains='(分割'
    ).order_by('year_month', 'card_type', 'created_at')

    # 分割ペアをグループ化
    processed = set()

    for est in all_estimates:
        if est.id in processed:
            continue

        # descriptionから括弧書きを除去
        clean_desc = est.description.replace(' (分割1回目)', '').replace(' (分割2回目)', '').strip()

        # 1回目か2回目かを判定
        if '(分割1回目)' in est.description:
            # これは1回目
            first_payment = est

            # 次月の年月を計算
            year, month = map(int, est.year_month.split('-'))
            next_month = month + 1
            next_year = year
            if next_month > 12:
                next_month = 1
                next_year += 1
            next_year_month = f"{next_year}-{next_month:02d}"

            # 2回目を検索
            second_candidates = CreditEstimate.objects.filter(
                year_month=next_year_month,
                card_type=est.card_type
            )
            second_payment = None
            for candidate in second_candidates:
                if clean_desc in candidate.description and '(分割2回目)' in candidate.description:
                    second_payment = candidate
                    break

            # グループIDを生成
            group_id = str(uuid.uuid4())

            # 1回目を更新
            first_payment.description = clean_desc
            first_payment.split_payment_part = 1
            first_payment.split_payment_group = group_id
            first_payment.is_split_payment = True
            first_payment.save()
            processed.add(first_payment.id)

            # 2回目を更新
            if second_payment:
                second_payment.description = clean_desc
                second_payment.split_payment_part = 2
                second_payment.split_payment_group = group_id
                second_payment.is_split_payment = True
                second_payment.save()
                processed.add(second_payment.id)

        elif '(分割2回目)' in est.description:
            # これは2回目（ペアの1回目が見つからなかった場合）
            # 単独で処理
            est.description = clean_desc
            est.split_payment_part = 2
            est.split_payment_group = str(uuid.uuid4())
            est.is_split_payment = True
            est.save()
            processed.add(est.id)


class Migration(migrations.Migration):

    dependencies = [
        ('budget_app', '0021_creditestimate_split_payment_group_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_split_payment_data, migrations.RunPython.noop),
    ]
