from __future__ import annotations

import calendar
import re
from datetime import datetime
from typing import Dict


def parse_timest_to_datetime(granularity: str, timest: str) -> datetime:
    """
    将前端传入的 timest 解析为 datetime。
    支持格式：day=YYYYMMDD 或 yyyy-MM-dd；month=YYYYMM 或 yyyy-MM；
    quarter=YYYYQn 或 yyyy-Qn；year=YYYY 或 yyyy。
    """
    raw = (timest or "").strip()
    if not raw:
        return datetime.utcnow()

    g = (granularity or "day").lower()

    # day: YYYYMMDD (8 digits) or yyyy-MM-dd
    if g == "day":
        if len(raw) == 8 and raw.isdigit():
            return datetime.strptime(raw, "%Y%m%d")
        if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
            return datetime.strptime(raw, "%Y-%m-%d")

    # month: YYYYMM (6 digits) or yyyy-MM
    if g == "month":
        if len(raw) == 6 and raw.isdigit():
            return datetime.strptime(raw, "%Y%m")
        if re.match(r"^\d{4}-\d{2}$", raw):
            return datetime.strptime(raw + "-01", "%Y-%m-%d")

    # quarter: YYYYQn or yyyy-Qn
    if g == "quarter":
        m = re.match(r"^(\d{4})[Qq](\d)$", raw)
        if m:
            y, q = int(m.group(1)), int(m.group(2))
            month = (q - 1) * 3 + 1
            return datetime(y, month, 1)
        m = re.match(r"^(\d{4})-Q(\d)$", raw, re.IGNORECASE)
        if m:
            y, q = int(m.group(1)), int(m.group(2))
            month = (q - 1) * 3 + 1
            return datetime(y, month, 1)

    # year: YYYY (4 digits)
    if g == "year":
        if len(raw) == 4 and raw.isdigit():
            return datetime(int(raw), 1, 1)

    # fallback: try YYYYMMDD
    if len(raw) == 8 and raw.isdigit():
        return datetime.strptime(raw, "%Y%m%d")
    return datetime.utcnow()


def make_period_keys(dt: datetime) -> Dict[str, str]:
  """
  根据日期生成各粒度的 period_key：
  - day: YYYYMMDD
  - month: YYYYMM
  - quarter: YYYYQn
  - year: YYYY
  """
  quarter = (dt.month - 1) // 3 + 1
  return {
      "day": dt.strftime("%Y%m%d"),
      "month": dt.strftime("%Y%m"),
      "quarter": f"{dt.year}Q{quarter}",
      "year": dt.strftime("%Y"),
  }


def normalize_granularity(date_type: str | None) -> str:
  """
  将前端传入的 dateType 归一为 day/month/quarter/year 四种之一，默认 day。
  """
  key = (date_type or "").lower().strip()
  # quarter / quarterly_for_year / QUARTER 等统一映射为 quarter 粒度
  if key.startswith("quarter"):
      return "quarter"
  # 前端已经保证只会传 day / month / quarter / year / others（大小写不限）
  if key in ("day",):
      return "day"
  if key in ("month",):
      return "month"
  if key in ("year",):
      return "year"
  if key in ("others",):
      # “其他” 粒度按日来统计
      return "day"
  # 兜底：认为是按日
  return "day"


def to_collect_api_date(granularity: str, timest: str) -> tuple[str, str]:
  """
  采集服务/扩展只支持 dateType=day，将 month/quarter/year 转为 day + 该周期首日 YYYYMMDD。
  用于请求外部采集 API 时统一传 dateType=day、timest=YYYYMMDD。
  """
  g = (granularity or "day").lower()
  if g == "day":
    raw = (timest or "").strip()
    if len(raw) == 8 and raw.isdigit():
      return ("day", raw)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
      return ("day", raw.replace("-", ""))
    # 其他 day 格式兜底
    dt = parse_timest_to_datetime("day", timest)
    return ("day", dt.strftime("%Y%m%d"))
  dt = parse_timest_to_datetime(g, timest)
  return ("day", dt.strftime("%Y%m%d"))


def to_dashed_date(value: str) -> str:
  """
  将 YYYYMMDD 或 yyyy-MM-dd 转为 yyyy-MM-dd，采集 API 要求日期带连字符。
  """
  raw = (value or "").strip()
  if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
    return raw
  if len(raw) == 8 and raw.isdigit():
    return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
  return raw


def format_for_collect_api(granularity: str, value: str) -> str:
  """
  按粒度将 timest 格式化为采集 API 要求的格式：
  - day   -> yyyy-MM-dd
  - month -> yyyy-MM
  - quarter -> yyyy-Qn
  - year  -> yyyy
  """
  g = (granularity or "day").lower()
  dt = parse_timest_to_datetime(g, value or "")
  if g == "day":
    return dt.strftime("%Y-%m-%d")
  if g == "month":
    return dt.strftime("%Y-%m")
  if g == "quarter":
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{q}"
  if g == "year":
    return dt.strftime("%Y")
  return dt.strftime("%Y-%m-%d")


def format_trend_range_for_api(
  granularity: str, raw_start: str, raw_end: str
) -> tuple[str, str]:
  """
  将行业趋势范围的任意合法输入按粒度转为采集 API 要求的 (starRange, endRange)。
  支持：前端 yyyy-MM / yyyy-Qn / yyyy，或 scheduler/fill 的 yyyy-MM-dd、period_key 如 202501/2025Q1。
  输出：day=yyyy-MM-dd；month=yyyy-MM；quarter=yyyy-Qn；year=yyyy。
  """
  g = (granularity or "day").lower()
  raw_start = (raw_start or "").strip()
  raw_end = (raw_end or "").strip() or raw_start

  def normalize(raw: str) -> str:
    if not raw:
      return ""
    if g == "day":
      return to_dashed_date(raw)
    if g == "month":
      if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw[:7]
      return format_for_collect_api("month", raw)
    if g == "quarter":
      if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        dt = parse_timest_to_datetime("day", raw)
        q = (dt.month - 1) // 3 + 1
        return f"{dt.year}-Q{q}"
      return format_for_collect_api("quarter", raw)
    if g == "year":
      if re.match(r"^\d{4}-\d{2}-\d{2}$", raw) or (
        len(raw) >= 4 and raw[:4].isdigit()
      ):
        return raw[:4]
      return format_for_collect_api("year", raw)
    return to_dashed_date(raw)

  return (normalize(raw_start), normalize(raw_end))


def period_to_date_range(granularity: str, timest: str) -> tuple[str, str]:
  """
  根据粒度与 timest 计算该周期的真实起止日期（yyyy-MM-dd），
  用于请求中的 starRange、endRange，采集 API 需要真实日期区间。
  - day: 当天
  - month: 当月 1 日 ~ 当月最后一日
  - quarter: 当季首日 ~ 当季末日
  - year: 当年 1 月 1 日 ~ 12 月 31 日
  """
  g = (granularity or "day").lower()
  dt = parse_timest_to_datetime(g, timest or "")
  if g == "day":
    s = dt.strftime("%Y-%m-%d")
    return (s, s)
  if g == "month":
    start = dt.replace(day=1)
    _, last_day = calendar.monthrange(dt.year, dt.month)
    end = dt.replace(day=last_day)
    return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
  if g == "quarter":
    q = (dt.month - 1) // 3 + 1
    start_month = (q - 1) * 3 + 1
    start = dt.replace(month=start_month, day=1)
    end_month = start_month + 2
    _, last_day = calendar.monthrange(dt.year, end_month)
    end = dt.replace(month=end_month, day=last_day)
    return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
  if g == "year":
    start = dt.replace(month=1, day=1)
    end = dt.replace(month=12, day=31)
    return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
  s = dt.strftime("%Y-%m-%d")
  return (s, s)


def timest_to_period_key(granularity: str, timest: str) -> str:
  """将单个时间点 timest（如 20250115 或 2025-01-15）转为该粒度下的 period_key。"""
  dt = parse_timest_to_datetime((granularity or "day").lower(), timest or "")
  return make_period_keys(dt).get((granularity or "day").lower(), make_period_keys(dt)["day"])


def period_keys_in_range(granularity: str, start_date: str, end_date: str) -> list[str]:
  """
  根据粒度与起止日期（yyyy-MM-dd）生成该范围内的所有 period_key 列表。
  - day: 2025-01-01..2025-01-31 -> [20250101, ..., 20250131]
  - month: 同区间 -> [202501]
  - quarter: 同区间 -> [2025Q1]
  - year: 同区间 -> [2025]
  """
  from datetime import timedelta

  g = (granularity or "day").lower()
  # 解析为日期
  def parse_d(s: str) -> datetime:
    raw = (s or "").strip()[:10]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
      return datetime.strptime(raw, "%Y-%m-%d")
    if len(raw) == 8 and raw.isdigit():
      return datetime.strptime(raw, "%Y%m%d")
    return datetime.utcnow()

  start_d = parse_d(start_date)
  end_d = parse_d(end_date)
  if start_d > end_d:
    start_d, end_d = end_d, start_d

  keys: list[str] = []
  if g == "day":
    d = start_d
    while d <= end_d:
      keys.append(d.strftime("%Y%m%d"))
      d += timedelta(days=1)
    return keys
  if g == "month":
    y, m = start_d.year, start_d.month
    ey, em = end_d.year, end_d.month
    while (y, m) <= (ey, em):
      keys.append(datetime(y, m, 1).strftime("%Y%m"))
      if m == 12:
        y, m = y + 1, 1
      else:
        m += 1
    return keys
  if g == "quarter":
    y, q = start_d.year, (start_d.month - 1) // 3 + 1
    ey, eq = end_d.year, (end_d.month - 1) // 3 + 1
    while (y, q) <= (ey, eq):
      keys.append(f"{y}Q{q}")
      if q == 4:
        y, q = y + 1, 1
      else:
        q += 1
    return keys
  if g == "year":
    y = start_d.year
    while y <= end_d.year:
      keys.append(str(y))
      y += 1
    return keys
  # 默认按天
  d = start_d
  while d <= end_d:
    keys.append(d.strftime("%Y%m%d"))
    d += timedelta(days=1)
  return keys

