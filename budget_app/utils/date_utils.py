"""日付ユーティリティ"""


def parse_year_month(year_month: str) -> tuple[int, int]:
    """'YYYY-MM' 形式の文字列を (year, month) タプルに変換"""
    year, month = map(int, year_month.split('-'))
    return year, month
