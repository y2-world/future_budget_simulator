"""為替レート取得ユーティリティ"""
import requests
from decimal import Decimal
from datetime import datetime, timedelta
from django.core.cache import cache


def get_usd_to_jpy_rate():
    """
    USD→JPYの為替レートを取得

    無料のExchangeRate-API (https://www.exchangerate-api.com/)を使用
    レートは1日1回更新されるため、1日キャッシュする

    Returns:
        Decimal: USD→JPYのレート
    """
    cache_key = 'usd_jpy_rate'
    cached_rate = cache.get(cache_key)

    if cached_rate:
        return Decimal(str(cached_rate))

    try:
        # ExchangeRate-APIの無料エンドポイント
        url = 'https://api.exchangerate-api.com/v4/latest/USD'
        response = requests.get(url, timeout=5)
        response.raise_for_status()

        data = response.json()
        rate = data['rates']['JPY']

        # 1日キャッシュ (秒単位)
        cache.set(cache_key, rate, 86400)

        return Decimal(str(rate))
    except Exception as e:
        # API呼び出しが失敗した場合は、デフォルトレートを使用
        # エラーログを出力
        print(f"為替レート取得エラー: {e}")
        # デフォルトレート: 150円/ドル
        default_rate = Decimal('150.0')
        return default_rate


def convert_usd_to_jpy(usd_amount, exchange_rate=None):
    """
    ドルを円に変換

    Args:
        usd_amount: ドル金額 (Decimal or float or str)
        exchange_rate: 為替レート (指定しない場合は自動取得)

    Returns:
        int: 円金額（整数）
    """
    if usd_amount is None:
        return 0

    usd = Decimal(str(usd_amount))
    rate = exchange_rate if exchange_rate else get_usd_to_jpy_rate()

    # ドル * レート = 円
    jpy = usd * rate

    # 整数に丸める
    return int(round(jpy))


def format_usd_with_jpy(usd_amount, jpy_amount=None):
    """
    ドルと円を併記する形式でフォーマット

    Args:
        usd_amount: ドル金額
        jpy_amount: 円金額 (指定しない場合は自動変換)

    Returns:
        str: "$XX.XX (¥XX,XXX)" 形式の文字列
    """
    if usd_amount is None:
        return ""

    usd = Decimal(str(usd_amount))

    if jpy_amount is None:
        jpy_amount = convert_usd_to_jpy(usd)

    # ドル部分: 小数点2桁
    # 円部分: カンマ区切り
    return f"${usd:.2f} (¥{jpy_amount:,})"
