from datetime import datetime

from backend.utils.period import (
    parse_timest_to_datetime,
    make_period_keys,
    normalize_granularity,
    period_to_date_range,
    to_collect_api_date,
    to_dashed_date,
    format_for_collect_api,
    format_trend_range_for_api,
    timest_to_period_key,
    period_keys_in_range,
)


class TestParseTimestToDatetime:
    """timest 日期解析测试"""

    def test_day_yyyymmdd(self):
        result = parse_timest_to_datetime("day", "20250115")
        assert result == datetime(2025, 1, 15)

    def test_day_dashed(self):
        result = parse_timest_to_datetime("day", "2025-01-15")
        assert result == datetime(2025, 1, 15)

    def test_month_yyyymm(self):
        result = parse_timest_to_datetime("month", "202503")
        assert result == datetime(2025, 3, 1)

    def test_month_dashed(self):
        result = parse_timest_to_datetime("month", "2025-03")
        assert result == datetime(2025, 3, 1)

    def test_quarter_yyyyqn(self):
        result = parse_timest_to_datetime("quarter", "2025Q2")
        assert result == datetime(2025, 4, 1)

    def test_quarter_dashed(self):
        result = parse_timest_to_datetime("quarter", "2025-Q3")
        assert result == datetime(2025, 7, 1)

    def test_year(self):
        result = parse_timest_to_datetime("year", "2025")
        assert result == datetime(2025, 1, 1)

    def test_empty_string_returns_now(self):
        result = parse_timest_to_datetime("day", "")
        assert isinstance(result, datetime)


class TestMakePeriodKeys:
    """period_key 生成测试"""

    def test_returns_all_granularities(self):
        dt = datetime(2025, 7, 15)
        keys = make_period_keys(dt)
        assert keys["day"] == "20250715"
        assert keys["month"] == "202507"
        assert keys["quarter"] == "2025Q3"
        assert keys["year"] == "2025"

    def test_q1(self):
        dt = datetime(2025, 2, 1)
        keys = make_period_keys(dt)
        assert keys["quarter"] == "2025Q1"

    def test_q4(self):
        dt = datetime(2025, 12, 31)
        keys = make_period_keys(dt)
        assert keys["quarter"] == "2025Q4"


class TestNormalizeGranularity:
    """粒度归一化测试"""

    def test_day(self):
        assert normalize_granularity("day") == "day"

    def test_month(self):
        assert normalize_granularity("month") == "month"

    def test_quarter(self):
        assert normalize_granularity("quarter") == "quarter"

    def test_quarterly_prefix(self):
        assert normalize_granularity("quarterly_for_year") == "quarter"

    def test_year(self):
        assert normalize_granularity("year") == "year"

    def test_others(self):
        assert normalize_granularity("others") == "day"

    def test_none_defaults_to_day(self):
        assert normalize_granularity(None) == "day"

    def test_empty_defaults_to_day(self):
        assert normalize_granularity("") == "day"


class TestPeriodToDateRange:
    """周期日期范围计算测试"""

    def test_day_returns_same_date(self):
        start, end = period_to_date_range("day", "20250115")
        assert start == "2025-01-15"
        assert end == "2025-01-15"

    def test_month_returns_full_range(self):
        start, end = period_to_date_range("month", "202502")
        assert start == "2025-02-01"
        assert end == "2025-02-28"

    def test_month_leap_year(self):
        start, end = period_to_date_range("month", "202402")
        assert start == "2024-02-01"
        assert end == "2024-02-29"

    def test_quarter_q1(self):
        start, end = period_to_date_range("quarter", "2025Q1")
        assert start == "2025-01-01"
        assert end == "2025-03-31"

    def test_year_full_range(self):
        start, end = period_to_date_range("year", "2025")
        assert start == "2025-01-01"
        assert end == "2025-12-31"

    def test_start_before_end(self):
        """任何粒度的范围，start 都应 <= end"""
        for g, t in [("day", "20250601"), ("month", "202506"),
                      ("quarter", "2025Q2"), ("year", "2025")]:
            start, end = period_to_date_range(g, t)
            assert start <= end, f"Failed for {g}: {start} > {end}"


class TestToDashedDate:
    """日期格式转换测试"""

    def test_yyyymmdd_to_dashed(self):
        assert to_dashed_date("20250115") == "2025-01-15"

    def test_already_dashed(self):
        assert to_dashed_date("2025-01-15") == "2025-01-15"


class TestPeriodKeysInRange:
    """范围内 period_key 生成测试"""

    def test_day_range(self):
        keys = period_keys_in_range("day", "2025-01-01", "2025-01-03")
        assert keys == ["20250101", "20250102", "20250103"]

    def test_month_range(self):
        keys = period_keys_in_range("month", "2025-01-01", "2025-03-31")
        assert keys == ["202501", "202502", "202503"]

    def test_quarter_range(self):
        keys = period_keys_in_range("quarter", "2025-01-01", "2025-06-30")
        assert keys == ["2025Q1", "2025Q2"]

    def test_year_range(self):
        keys = period_keys_in_range("year", "2024-01-01", "2026-12-31")
        assert keys == ["2024", "2025", "2026"]
