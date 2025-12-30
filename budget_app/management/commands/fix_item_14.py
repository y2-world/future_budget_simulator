from django.core.management.base import BaseCommand
from budget_app.models import MonthlyPlanDefault


class Command(BaseCommand):
    help = 'Fix item_14 depends_on_key configuration'

    def handle(self, *args, **options):
        try:
            item_14 = MonthlyPlanDefault.objects.get(key='item_14')
            self.stdout.write(f'Current configuration:')
            self.stdout.write(f'  Title: {item_14.title}')
            self.stdout.write(f'  depends_on_key: {item_14.depends_on_key}')
            self.stdout.write(f'  offset_months: {item_14.offset_months}')

            item_14.depends_on_key = None
            item_14.save()

            self.stdout.write(self.style.SUCCESS(
                f'Successfully updated item_14: depends_on_key = {item_14.depends_on_key}'
            ))
        except MonthlyPlanDefault.DoesNotExist:
            self.stdout.write(self.style.ERROR('item_14 not found'))
