from django.contrib import admin
from .models import (
    SimulationConfig,
    AccountBalance,
    MonthlyPlan,
    TransactionEvent,
    CreditEstimate,
    CreditDefault,
)


@admin.register(SimulationConfig)
class SimulationConfigAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'initial_balance', 'start_date',
        'simulation_months', 'is_active', 'created_at'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['id']
    ordering = ['-created_at']


@admin.register(AccountBalance)
class AccountBalanceAdmin(admin.ModelAdmin):
    list_display = ['date', 'balance', 'source', 'last_updated']
    list_filter = ['source', 'date']
    search_fields = ['date']
    ordering = ['-date']


@admin.register(MonthlyPlan)
class MonthlyPlanAdmin(admin.ModelAdmin):
    list_display = [
        'year_month',
        'get_total_income', 'get_total_expenses', 'get_net_income',
        'updated_at'
    ]
    list_filter = ['year_month']
    search_fields = ['year_month']
    ordering = ['year_month']

    fieldsets = (
        ('基本情報', {
            'fields': ('year_month',)
        }),
        ('給与明細', {
            'fields': ('gross_salary', 'deductions', 'transportation')
        }),
        ('ボーナス明細', {
            'fields': ('bonus_gross_salary', 'bonus_deductions')
        }),
        ('動的項目', {
            'fields': ('items', 'exclusions')
        }),
    )


@admin.register(TransactionEvent)
class TransactionEventAdmin(admin.ModelAdmin):
    list_display = [
        'date', 'event_name', 'amount',
        'balance_after', 'month', 'created_at'
    ]
    list_filter = ['event_type', 'date', 'month']
    search_fields = ['event_name', 'event_type']
    ordering = ['date', 'id']
    readonly_fields = ['created_at']


@admin.register(CreditEstimate)
class CreditEstimateAdmin(admin.ModelAdmin):
    list_display = ['year_month', 'card_type', 'description', 'amount', 'due_date', 'is_split_payment', 'is_bonus_payment', 'created_at']
    list_filter = ['card_type', 'year_month', 'is_split_payment', 'is_bonus_payment']
    search_fields = ['year_month', 'description']
    ordering = ['-year_month', '-created_at']


@admin.register(CreditDefault)
class CreditDefaultAdmin(admin.ModelAdmin):
    list_display = ['key', 'label', 'card_type', 'amount']
    list_filter = ['card_type']
    search_fields = ['key', 'label']
    ordering = ['key']
