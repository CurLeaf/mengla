from __future__ import annotations

from .database import mongo_db


async def ensure_mengla_indexes() -> None:
    """
    为 MengLa 集合创建唯一索引：
    所有集合统一按颗粒度 (granularity, period_key, params_hash)，
    行业趋势（mengla_trend_reports）按各天/各月等颗粒存储，不再按时间范围。
    """
    if mongo_db is None:
        return

    single_period_spec = [("granularity", 1), ("period_key", 1), ("params_hash", 1)]

    for name in [
        "mengla_high_reports",
        "mengla_hot_reports",
        "mengla_chance_reports",
        "mengla_view_reports",
        "mengla_trend_reports",
    ]:
        coll = mongo_db[name]
        await coll.create_index(
            single_period_spec, unique=True, name="uniq_period_params"
        )

