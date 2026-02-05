import asyncio
import logging
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .infra.database import mongo_db
from .utils.period import make_period_keys, period_to_date_range
from .core.domain import query_mengla
from .core.queue import (
    get_next_job,
    get_pending_subtasks,
    set_job_running,
    set_subtask_running,
    set_subtask_success,
    set_subtask_failed,
    inc_job_stats,
    finish_job_if_done,
)
from .utils.category import get_top_level_cat_ids
from .utils.config import SCHEDULER_CONFIG, CRON_JOBS, CONCURRENT_CONFIG

logger = logging.getLogger("mengla-scheduler")


def _get_top_cat_ids_safe() -> List[str]:
    """Try to load all top-level catIds; fallback to [''] if unavailable."""
    try:
        cat_ids = get_top_level_cat_ids()
        if cat_ids:
            return cat_ids
        logger.warning("category_utils returned empty top-level cat list, falling back to default catId=''")
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to load top-level categories: %s", exc)
    return [""]


def init_scheduler() -> AsyncIOScheduler:
    """
    初始化 APScheduler，注册 MengLa 相关定时任务。
    使用配置中心的设置。
    """
    scheduler = AsyncIOScheduler(timezone=SCHEDULER_CONFIG["timezone"])
    
    # 每日主采集：02:00 执行，day 颗粒度
    scheduler.add_job(
        run_daily_collect,
        "cron",
        hour=2, minute=0,
        id="daily_collect",
        name="每日主采集",
    )
    
    # 月度采集：每月1日 01:00 执行，month 颗粒度
    scheduler.add_job(
        run_monthly_collect,
        "cron",
        day=1, hour=1, minute=0,
        id="monthly_collect",
        name="月度采集",
    )
    
    # 季度采集：季初 02:00 执行，quarter 颗粒度
    scheduler.add_job(
        run_quarterly_collect,
        "cron",
        month="1,4,7,10", day=1, hour=2, minute=0,
        id="quarterly_collect",
        name="季度采集",
    )
    
    # 年度采集：年初 03:00 执行，year 颗粒度
    scheduler.add_job(
        run_yearly_collect,
        "cron",
        month=1, day=1, hour=3, minute=0,
        id="yearly_collect",
        name="年度采集",
    )
    
    # 补数检查：每4小时检查缺失数据
    scheduler.add_job(
        run_backfill_check,
        "cron",
        hour="*/4", minute=0,
        id="backfill_check",
        name="补数检查",
    )
    
    # 队列消费：定期执行待处理的爬取子任务（历史全量补齐）
    scheduler.add_job(
        run_crawl_queue_once,
        "interval",
        seconds=240,  # 4 分钟
        jitter=60,    # ±1 分钟抖动 => 约 3~5 分钟
        id="crawl_queue",
        name="队列消费",
    )
    
    logger.info("Scheduler initialized with %d jobs", len(scheduler.get_jobs()))
    return scheduler


MENG_LA_ACTIONS: Dict[str, List[str]] = {
    "high": ["day", "month", "quarter", "year"],
    "hot": ["day", "month", "quarter", "year"],
    "chance": ["day", "month", "quarter", "year"],
    "industryViewV2": ["day", "month", "quarter", "year"],
    "industryTrendRange": ["day", "month", "quarter", "year"],
}

# 非趋势接口列表
NON_TREND_ACTIONS = ["high", "hot", "chance", "industryViewV2"]
# 趋势接口
TREND_ACTION = "industryTrendRange"


# ==============================================================================
# 新增定时任务函数
# ==============================================================================
async def run_daily_collect(target_date: Optional[datetime] = None) -> Dict[str, Any]:
    """
    每日主采集：采集当天的 day 颗粒度数据
    """
    now = target_date or datetime.now()
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()
    
    stats = {"total": 0, "success": 0, "failed": 0}
    period_key = periods["day"]
    
    logger.info("Starting daily collect for period_key=%s", period_key)
    
    for cat_id in top_cat_ids:
        for action in NON_TREND_ACTIONS:
            stats["total"] += 1
            try:
                await query_mengla(
                    action=action,
                    product_id="",
                    catId=cat_id,
                    dateType="day",
                    timest=period_key,
                    starRange="",
                    endRange="",
                    extra=None,
                )
                stats["success"] += 1
            except Exception as e:
                stats["failed"] += 1
                logger.warning("Daily collect failed: action=%s cat_id=%s error=%s", action, cat_id, e)
            await asyncio.sleep(random.uniform(1, 3))
    
    # 趋势接口：按年范围补齐 day 颗粒度
    year_str = str(now.year)
    start_year, end_year = period_to_date_range("year", year_str)
    
    for cat_id in top_cat_ids:
        stats["total"] += 1
        try:
            await query_mengla(
                action=TREND_ACTION,
                product_id="",
                catId=cat_id,
                dateType="DAY",
                timest="",
                starRange=start_year,
                endRange=end_year,
                extra=None,
            )
            stats["success"] += 1
        except Exception as e:
            stats["failed"] += 1
            logger.warning("Daily trend collect failed: cat_id=%s error=%s", cat_id, e)
        await asyncio.sleep(random.uniform(1, 3))
    
    logger.info("Daily collect completed: %s", stats)
    return stats


async def run_monthly_collect(target_date: Optional[datetime] = None) -> Dict[str, Any]:
    """
    月度采集：采集当月的 month 颗粒度数据
    """
    now = target_date or datetime.now()
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()
    
    stats = {"total": 0, "success": 0, "failed": 0}
    period_key = periods["month"]
    
    logger.info("Starting monthly collect for period_key=%s", period_key)
    
    for cat_id in top_cat_ids:
        for action in NON_TREND_ACTIONS:
            stats["total"] += 1
            try:
                await query_mengla(
                    action=action,
                    product_id="",
                    catId=cat_id,
                    dateType="month",
                    timest=period_key,
                    starRange="",
                    endRange="",
                    extra=None,
                )
                stats["success"] += 1
            except Exception as e:
                stats["failed"] += 1
                logger.warning("Monthly collect failed: action=%s cat_id=%s error=%s", action, cat_id, e)
            await asyncio.sleep(random.uniform(1, 3))
    
    # 趋势接口：按年范围补齐 month 颗粒度
    year_str = str(now.year)
    start_year, end_year = period_to_date_range("year", year_str)
    
    for cat_id in top_cat_ids:
        stats["total"] += 1
        try:
            await query_mengla(
                action=TREND_ACTION,
                product_id="",
                catId=cat_id,
                dateType="MONTH",
                timest="",
                starRange=start_year,
                endRange=end_year,
                extra=None,
            )
            stats["success"] += 1
        except Exception as e:
            stats["failed"] += 1
            logger.warning("Monthly trend collect failed: cat_id=%s error=%s", cat_id, e)
        await asyncio.sleep(random.uniform(1, 3))
    
    logger.info("Monthly collect completed: %s", stats)
    return stats


async def run_quarterly_collect(target_date: Optional[datetime] = None) -> Dict[str, Any]:
    """
    季度采集：采集当季的 quarter 颗粒度数据
    """
    now = target_date or datetime.now()
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()
    
    stats = {"total": 0, "success": 0, "failed": 0}
    period_key = periods["quarter"]
    
    logger.info("Starting quarterly collect for period_key=%s", period_key)
    
    for cat_id in top_cat_ids:
        for action in NON_TREND_ACTIONS:
            stats["total"] += 1
            try:
                await query_mengla(
                    action=action,
                    product_id="",
                    catId=cat_id,
                    dateType="quarter",
                    timest=period_key,
                    starRange="",
                    endRange="",
                    extra=None,
                )
                stats["success"] += 1
            except Exception as e:
                stats["failed"] += 1
                logger.warning("Quarterly collect failed: action=%s cat_id=%s error=%s", action, cat_id, e)
            await asyncio.sleep(random.uniform(1, 3))
    
    # 趋势接口：按年范围补齐 quarter 颗粒度
    year_str = str(now.year)
    start_year, end_year = period_to_date_range("year", year_str)
    
    for cat_id in top_cat_ids:
        stats["total"] += 1
        try:
            await query_mengla(
                action=TREND_ACTION,
                product_id="",
                catId=cat_id,
                dateType="QUARTERLY_FOR_YEAR",
                timest="",
                starRange=start_year,
                endRange=end_year,
                extra=None,
            )
            stats["success"] += 1
        except Exception as e:
            stats["failed"] += 1
            logger.warning("Quarterly trend collect failed: cat_id=%s error=%s", cat_id, e)
        await asyncio.sleep(random.uniform(1, 3))
    
    logger.info("Quarterly collect completed: %s", stats)
    return stats


async def run_yearly_collect(target_date: Optional[datetime] = None) -> Dict[str, Any]:
    """
    年度采集：采集当年的 year 颗粒度数据
    """
    now = target_date or datetime.now()
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()
    
    stats = {"total": 0, "success": 0, "failed": 0}
    period_key = periods["year"]
    
    logger.info("Starting yearly collect for period_key=%s", period_key)
    
    for cat_id in top_cat_ids:
        for action in NON_TREND_ACTIONS:
            stats["total"] += 1
            try:
                await query_mengla(
                    action=action,
                    product_id="",
                    catId=cat_id,
                    dateType="year",
                    timest=period_key,
                    starRange="",
                    endRange="",
                    extra=None,
                )
                stats["success"] += 1
            except Exception as e:
                stats["failed"] += 1
                logger.warning("Yearly collect failed: action=%s cat_id=%s error=%s", action, cat_id, e)
            await asyncio.sleep(random.uniform(1, 3))
    
    # 趋势接口：按年范围补齐 year 颗粒度
    year_str = str(now.year)
    start_year, end_year = period_to_date_range("year", year_str)
    
    for cat_id in top_cat_ids:
        stats["total"] += 1
        try:
            await query_mengla(
                action=TREND_ACTION,
                product_id="",
                catId=cat_id,
                dateType="YEAR",
                timest="",
                starRange=start_year,
                endRange=end_year,
                extra=None,
            )
            stats["success"] += 1
        except Exception as e:
            stats["failed"] += 1
            logger.warning("Yearly trend collect failed: cat_id=%s error=%s", cat_id, e)
        await asyncio.sleep(random.uniform(1, 3))
    
    logger.info("Yearly collect completed: %s", stats)
    return stats


async def run_backfill_check() -> Dict[str, Any]:
    """
    补数检查：检查最近数据是否有缺失，触发补采
    """
    from .infra.database import mongo_db, MENGLA_DATA_COLLECTION
    from .utils.config import COLLECTION_NAME
    
    if mongo_db is None:
        logger.warning("MongoDB not connected, skipping backfill check")
        return {"status": "skipped", "reason": "db_not_connected"}
    
    now = datetime.now()
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()
    
    stats = {"checked": 0, "missing": 0, "backfilled": 0, "failed": 0}
    
    logger.info("Starting backfill check")
    
    collection = mongo_db[COLLECTION_NAME]
    
    # 检查最近的 day 和 month 数据
    for granularity in ["day", "month"]:
        period_key = periods[granularity]
        
        for cat_id in top_cat_ids:
            for action in NON_TREND_ACTIONS:
                stats["checked"] += 1
                
                # 检查数据是否存在
                query = {
                    "action": action,
                    "cat_id": cat_id or "",
                    "granularity": granularity,
                    "period_key": period_key,
                }
                
                try:
                    doc = await collection.find_one(query)
                    if doc is None:
                        stats["missing"] += 1
                        # 触发补采
                        try:
                            await query_mengla(
                                action=action,
                                product_id="",
                                catId=cat_id,
                                dateType=granularity,
                                timest=period_key,
                                starRange="",
                                endRange="",
                                extra=None,
                            )
                            stats["backfilled"] += 1
                        except Exception as e:
                            stats["failed"] += 1
                            logger.warning("Backfill failed: %s error=%s", query, e)
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                except Exception as e:
                    logger.warning("Backfill check error: %s", e)
    
    logger.info("Backfill check completed: %s", stats)
    return stats


async def run_mengla_jobs(target_date: Optional[datetime] = None) -> None:
    """
    每天凌晨针对 MengLa 的 high / view / trend 三个接口进行补齐：
    - 先计算当日对应的 day/month/quarter/year period_key
    - 对于每个 action+granularity，复用 query_mengla 的查 Mongo + 调第三方逻辑
    """
    now = target_date or datetime.now()
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()

    for cat_id in top_cat_ids:
        for action, granularities in MENG_LA_ACTIONS.items():
            for gran in granularities:
                period_key = periods[gran]
                await query_mengla(  # 返回 (data, source)，此处仅触发拉取与落库
                    action=action,
                    product_id="",
                    catId=cat_id,
                    dateType=gran,
                    timest=period_key,
                    starRange="",
                    endRange="",
                    extra=None,
                )


async def run_mengla_granular_jobs(target_date: Optional[datetime] = None) -> None:
    """
    每天凌晨针对 MengLa 的 high / hot / chance / view / trend 五个接口，
    按日 / 月 / 季 / 年四种颗粒度进行补齐：
    - 非趋势接口：按当天对应的 day/month/quarter/year period_key 各触发一次查询。
    - 趋势接口：对近一年的 day/month/quarter/year 范围各触发一次查询。
    所有查询统一复用 query_mengla（先 Mongo / 再 Redis / 后采集）。
    """
    now = target_date or datetime.now()
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()

    # 1) 非趋势接口：high / hot / chance / industryViewV2
    for cat_id in top_cat_ids:
        for action in ["high", "hot", "chance", "industryViewV2"]:
            for gran in ["day", "month", "quarter", "year"]:
                period_key = periods[gran]
                await query_mengla(
                    action=action,
                    product_id="",
                    catId=cat_id,
                    dateType=gran,
                    timest=period_key,
                    starRange="",
                    endRange="",
                    extra=None,
                )
                await asyncio.sleep(random.uniform(3, 9))

    # 2) 趋势接口：industryTrendRange，按年范围分别补齐 day/month/quarter/year 颗粒度
    year_str = str(now.year)
    start_year, end_year = period_to_date_range("year", year_str)  # yyyy-01-01, yyyy-12-31

    for cat_id in top_cat_ids:
        for gran in ["day", "month", "quarter", "year"]:
            await query_mengla(
                action="industryTrendRange",
                product_id="",
                catId=cat_id,
                dateType=gran.upper(),  # DAY / MONTH / QUARTER / YEAR
                timest="",
                starRange=start_year,
                endRange=end_year,
                extra=None,
            )
            await asyncio.sleep(random.uniform(3, 9))


async def run_crawl_queue_once(max_batch: int = 1) -> None:
    """
    Queue consumer: pick one RUNNING/PENDING crawl job, run up to max_batch
    pending subtasks (query_mengla), update status and job stats.
    """
    if mongo_db is None:
        return
    job = await get_next_job()
    if not job:
        return
    job_id = job["_id"]
    if job["status"] == "PENDING":
        await set_job_running(job_id)
    config = job.get("config") or {}
    cat_id = config.get("catId", "") or ""
    extra = config.get("extra") or {}

    subtasks = await get_pending_subtasks(job_id, limit=max_batch)
    for sub in subtasks:
        sub_id = sub["_id"]
        action = sub.get("action", "")
        gran = sub.get("granularity", "day")
        period_key = sub.get("period_key", "")
        await set_subtask_running(sub_id)
        try:
            if action == "industryTrendRange":
                start_range, end_range = period_to_date_range(gran, period_key)
                await query_mengla(
                    action=action,
                    product_id="",
                    catId=cat_id,
                    dateType=gran.upper(),
                    timest="",
                    starRange=start_range,
                    endRange=end_range,
                    extra=extra,
                )
            else:
                await query_mengla(
                    action=action,
                    product_id="",
                    catId=cat_id,
                    dateType=gran,
                    timest=period_key,
                    starRange="",
                    endRange="",
                    extra=extra,
                )
            await set_subtask_success(sub_id)
            await inc_job_stats(job_id, completed_delta=1, failed_delta=0)
        except Exception as exc:  # noqa: BLE001
            await set_subtask_failed(sub_id, str(exc))
            await inc_job_stats(job_id, completed_delta=0, failed_delta=1)

    await finish_job_if_done(job_id)


# 行业智能面板相关任务：供 GET /panel/tasks 与 POST /panel/tasks/{task_id}/run 使用
PANEL_TASKS: Dict[str, dict] = {
    "mengla_granular": {
        "name": "MengLa 日/月/季/年补齐",
        "description": "对 high/hot/chance/industryViewV2/industryTrendRange 按当日颗粒度补齐",
        "run": run_mengla_granular_jobs,
    },
    "mengla_single_day": {
        "name": "MengLa 单日补齐",
        "description": "同上，仅针对当日 period_key 各接口触发一次",
        "run": run_mengla_jobs,
    },
    "daily_collect": {
        "name": "每日主采集",
        "description": "采集当天的 day 颗粒度数据",
        "run": run_daily_collect,
    },
    "monthly_collect": {
        "name": "月度采集",
        "description": "采集当月的 month 颗粒度数据",
        "run": run_monthly_collect,
    },
    "quarterly_collect": {
        "name": "季度采集",
        "description": "采集当季的 quarter 颗粒度数据",
        "run": run_quarterly_collect,
    },
    "yearly_collect": {
        "name": "年度采集",
        "description": "采集当年的 year 颗粒度数据",
        "run": run_yearly_collect,
    },
    "backfill_check": {
        "name": "补数检查",
        "description": "检查最近数据是否有缺失，触发补采",
        "run": run_backfill_check,
    },
}

