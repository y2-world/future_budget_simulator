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
def get_item(mapping, key):
    """辞書からキーで値を取り出す（テンプレート用）"""
    try:
        return mapping.get(key)
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
    """控除率を計算（控除額 / (総支給額 - 交通費) * 100）"""
    try:
        gross_minus_transport = plan.gross_salary - plan.transportation
        if gross_minus_transport > 0:
            rate = (plan.deductions / gross_minus_transport) * 100
            return f"{rate:.1f}"
        return "0.0"
    except (AttributeError, ZeroDivisionError, TypeError):
        return "0.0"


@register.filter
def gross_minus_transport(plan):
    """総支給額-交通費を計算"""
    try:
        return plan.gross_salary - plan.transportation
    except (AttributeError, TypeError):
        return 0

