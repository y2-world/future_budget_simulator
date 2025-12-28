from django import template
from django.contrib.humanize.templatetags.humanize import intcomma

register = template.Library()


@register.filter
def format_year_month(value):
    """Convert 'YYYY-MM' into 'YYYY年M月'."""
    if not value:
        return ''
    try:
        year_str, month_str = str(value).split('-', 1)
        year = int(year_str)
        month = int(month_str.split(':')[0])  # guard against potential suffixes
    except (ValueError, AttributeError):
        return value
    return f'{year}年{month}月'


@register.filter
def yen(value):
    """Format integer currency with comma separators and leading yen symbol."""
    if value in ('', None):
        amount = 0
    else:
        try:
            amount = int(value)
        except (TypeError, ValueError):
            return value
    return f'¥{intcomma(amount)}'


@register.filter
def get_item(obj, key):
    """MonthlyPlanオブジェクトまたは辞書からキーで値を取り出す（テンプレート用）"""
    try:
        # MonthlyPlanオブジェクトの場合はget_item()メソッドを呼ぶ
        if hasattr(obj, 'get_item') and callable(obj.get_item):
            return obj.get_item(key)
        # 辞書の場合はget()を使う
        elif hasattr(obj, 'get'):
            return obj.get(key)
        return None
    except Exception:
        return None


@register.filter
def attr(obj, name):
    """オブジェクトの属性を取得（テンプレート用）"""
    try:
        return getattr(obj, name)
    except Exception:
        return None


@register.filter
def deduction_rate(plan):
    """控除率を計算（(給与控除額 + ボーナス控除額) / (総支給額 - 交通費) * 100）"""
    try:
        # 給与とボーナスの総支給額を合計
        total_gross = plan.gross_salary + (plan.bonus_gross_salary or 0)
        gross_minus_transport = total_gross - plan.transportation

        # 給与とボーナスの控除額を合計
        total_deductions = plan.deductions + (plan.bonus_deductions or 0)

        if gross_minus_transport > 0:
            rate = (total_deductions / gross_minus_transport) * 100
            return f"{rate:.1f}"
        return "0.0"
    except (AttributeError, ZeroDivisionError, TypeError):
        return "0.0"


@register.filter
def gross_minus_transport(plan):
    """総支給額-交通費を計算（給与 + ボーナス）"""
    try:
        # 給与とボーナスの総支給額を合計
        total_gross = plan.gross_salary + (plan.bonus_gross_salary or 0)
        return total_gross - plan.transportation
    except (AttributeError, TypeError):
        return 0


@register.filter
def subtract(value, arg):
    """2つの数値の差を計算"""
    try:
        return int(value) - int(arg)
    except (TypeError, ValueError):
        return 0


@register.filter
def filter_by_year(plans, year):
    """指定された年の月次計画をフィルタリング"""
    try:
        year_str = str(year)
        return [plan for plan in plans if plan.year_month.startswith(year_str)]
    except (AttributeError, TypeError):
        return []


@register.filter
def call(obj, method_name):
    """オブジェクトのメソッドを引数付きで呼び出す（テンプレート用）"""
    try:
        method = getattr(obj, method_name)
        if callable(method):
            return method()
        return method
    except Exception:
        return None

