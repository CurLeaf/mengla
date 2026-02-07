import asyncio
import logging
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .infra import database
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
from .infra.resilience import retry_async, RetryError
from .core.sync_task_log import (
    create_sync_task_log,
    update_sync_task_progress,
    finish_sync_task_log,
    STATUS_COMPLETED,
    STATUS_FAILED,
    TRIGGER_MANUAL,
    TRIGGER_SCHEDULED,
)

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
    
    # Daily collect: 04:00, collect previous day data
    scheduler.add_job(
        run_daily_collect,
        "cron",
        hour=4, minute=0,
        id="daily_collect",
        name="Daily Collect",
    )
    
    # Monthly collect: 3rd day 05:00, collect previous month data
    scheduler.add_job(
        run_monthly_collect,
        "cron",
        day=3, hour=5, minute=0,
        id="monthly_collect",
        name="Monthly Collect",
    )
    
    # Quarterly collect: 10th day after quarter end 06:00
    # Q1->Apr 10, Q2->Jul 10, Q3->Oct 10, Q4->Jan 10
    scheduler.add_job(
        run_quarterly_collect,
        "cron",
        month="1,4,7,10", day=10, hour=6, minute=0,
        id="quarterly_collect",
        name="Quarterly Collect",
    )
    
    # Yearly collect: Jan 20 07:00, collect previous year data
    scheduler.add_job(
        run_yearly_collect,
        "cron",
        month=1, day=20, hour=7, minute=0,
        id="yearly_collect",
        name="Yearly Collect",
    )
    
    # Backfill check: every 4 hours
    scheduler.add_job(
        run_backfill_check,
        "cron",
        hour="*/4", minute=0,
        id="backfill_check",
        name="Backfill Check",
    )
    
    # Queue consumer: process pending crawl subtasks
    scheduler.add_job(
        run_crawl_queue_once,
        "interval",
        seconds=240,  # 4 min
        jitter=60,    # +/-1 min jitter => ~3-5 min
        id="crawl_queue",
        name="Queue Consumer",
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
    每日主采集：采集前一天的 day 颗粒度数据
    """
    from datetime import timedelta
    # 默认采集前一天的数据
    target = target_date or (datetime.now() - timedelta(days=1))
    periods = make_period_keys(target)
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
    year_str = str(target.year)
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
    月度采集：采集上一月的 month 颗粒度数据
    """
    from datetime import timedelta
    # 默认采集上一月的数据（回退到上月任意一天）
    today = datetime.now()
    first_of_this_month = today.replace(day=1)
    target = target_date or (first_of_this_month - timedelta(days=1))
    periods = make_period_keys(target)
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
    year_str = str(target.year)
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
    季度采集：采集上一季度的 quarter 颗粒度数据
    """
    # 默认采集上一季度的数据
    today = datetime.now()
    # 计算当前季度，然后回退到上一季度
    current_quarter = (today.month - 1) // 3 + 1
    if current_quarter == 1:
        # 当前Q1，上一季度是去年Q4
        target = target_date or datetime(today.year - 1, 10, 1)
    else:
        # 上一季度的首月
        prev_quarter_month = (current_quarter - 2) * 3 + 1
        target = target_date or datetime(today.year, prev_quarter_month, 1)
    periods = make_period_keys(target)
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
    year_str = str(target.year)
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
    年度采集：采集上一年的 year 颗粒度数据
    """
    # 默认采集上一年的数据
    today = datetime.now()
    target = target_date or datetime(today.year - 1, 1, 1)
    periods = make_period_keys(target)
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
    year_str = str(target.year)
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
    from .infra.database import MENGLA_DATA_COLLECTION
    from .utils.config import COLLECTION_NAME
    
    if database.mongo_db is None:
        logger.warning("MongoDB not connected, skipping backfill check")
        return {"status": "skipped", "reason": "db_not_connected"}
    
    now = datetime.now()
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()
    
    stats = {"checked": 0, "missing": 0, "backfilled": 0, "failed": 0}
    
    logger.info("Starting backfill check")
    
    collection = database.mongo_db[COLLECTION_NAME]
    
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


async def run_mengla_granular_jobs(
    target_date: Optional[datetime] = None,
    force_refresh: bool = False,
    trigger: str = TRIGGER_SCHEDULED,
) -> None:
    """
    每天凌晨针对 MengLa 的 high / hot / chance / view / trend 五个接口，
    按日 / 月 / 季 / 年四种颗粒度进行补齐：
    - 非趋势接口：按昨天对应的 day/month/quarter/year period_key 各触发一次查询。
    - 趋势接口：对近一年的 day/month/quarter/year 范围各触发一次查询。
    所有查询统一复用 query_mengla（先 Mongo / 再 Redis / 后采集）。
    
    Args:
        target_date: 目标日期，默认昨天
        force_refresh: 是否强制刷新（跳过缓存）
        trigger: 触发方式 ("manual" 或 "scheduled")
    """
    from datetime import timedelta
    # 默认采集昨天的数据（外部数据源基于 T-1）
    now = target_date or (datetime.now() - timedelta(days=1))
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()
    
    # 计算总任务数
    # 非趋势接口：4 个接口 × 4 颗粒度 × N 类目
    # 趋势接口：1 个接口 × 4 颗粒度 × N 类目
    non_trend_count = len(top_cat_ids) * 4 * 4  # 4 actions × 4 granularities
    trend_count = len(top_cat_ids) * 4  # 1 action × 4 granularities
    total_tasks = non_trend_count + trend_count
    
    # 确定任务名称和 ID
    task_id = "mengla_granular_force" if force_refresh else "mengla_granular"
    task_name = "MengLa 强制全量采集" if force_refresh else "MengLa 日/月/季/年补齐"
    
    # 创建同步任务日志
    log_id = await create_sync_task_log(
        task_id=task_id,
        task_name=task_name,
        total=total_tasks,
        trigger=trigger,
    )
    
    logger.info(
        "Starting granular jobs: task_id=%s total=%d force_refresh=%s log_id=%s",
        task_id, total_tasks, force_refresh, log_id
    )
    
    # 统计
    completed_count = 0
    failed_count = 0
    
    # 退避重试配置
    MAX_RETRIES = 5
    BASE_DELAY = 5.0   # 基础延迟 5 秒
    MAX_DELAY = 120.0  # 最大延迟 2 分钟
    
    async def query_with_retry(**kwargs) -> bool:
        """带退避重试的查询，返回是否成功"""
        action = kwargs.get("action", "")
        cat_id = kwargs.get("catId", "")
        gran = kwargs.get("dateType", "")
        
        def on_retry(attempt: int, exc: Exception):
            logger.warning(
                "Granular job retry %d/%d: action=%s cat_id=%s gran=%s error=%s",
                attempt, MAX_RETRIES, action, cat_id, gran, exc
            )
        
        try:
            await retry_async(
                query_mengla,
                max_attempts=MAX_RETRIES,
                base_delay=BASE_DELAY,
                max_delay=MAX_DELAY,
                jitter=True,
                on_retry=on_retry,
                **kwargs,
            )
            return True
        except RetryError as e:
            logger.error(
                "Granular job failed after %d retries: action=%s cat_id=%s gran=%s last_error=%s",
                e.attempts, action, cat_id, gran, e.last_exception
            )
            return False
        except Exception as e:
            logger.error(
                "Granular job unexpected error: action=%s cat_id=%s gran=%s error=%s",
                action, cat_id, gran, e
            )
            return False

    try:
        # 1) 非趋势接口：high / hot / chance / industryViewV2
        for cat_id in top_cat_ids:
            for action in ["high", "hot", "chance", "industryViewV2"]:
                for gran in ["day", "month", "quarter", "year"]:
                    period_key = periods[gran]
                    success = await query_with_retry(
                        action=action,
                        product_id="",
                        catId=cat_id,
                        dateType=gran,
                        timest=period_key,
                        starRange="",
                        endRange="",
                        extra=None,
                        use_cache=not force_refresh,
                    )
                    
                    if success:
                        completed_count += 1
                        await update_sync_task_progress(log_id, completed_delta=1)
                    else:
                        failed_count += 1
                        await update_sync_task_progress(log_id, failed_delta=1)
                    
                    await asyncio.sleep(random.uniform(3, 9))

        # 2) 趋势接口：industryTrendRange，按年范围分别补齐 day/month/quarter/year 颗粒度
        year_str = str(now.year)
        start_year, end_year = period_to_date_range("year", year_str)  # yyyy-01-01, yyyy-12-31

        for cat_id in top_cat_ids:
            for gran in ["day", "month", "quarter", "year"]:
                success = await query_with_retry(
                    action="industryTrendRange",
                    product_id="",
                    catId=cat_id,
                    dateType=gran.upper(),  # DAY / MONTH / QUARTER / YEAR
                    timest="",
                    starRange=start_year,
                    endRange=end_year,
                    extra=None,
                    use_cache=not force_refresh,
                )
                
                if success:
                    completed_count += 1
                    await update_sync_task_progress(log_id, completed_delta=1)
                else:
                    failed_count += 1
                    await update_sync_task_progress(log_id, failed_delta=1)
                
                await asyncio.sleep(random.uniform(3, 9))
        
        # 标记任务完成
        final_status = STATUS_FAILED if failed_count > 0 else STATUS_COMPLETED
        await finish_sync_task_log(log_id, status=final_status)
        
        logger.info(
            "Granular jobs completed: date=%s force_refresh=%s completed=%d failed=%d",
            now.date(), force_refresh, completed_count, failed_count
        )
        
    except Exception as e:
        # 发生未预期的异常，标记任务失败
        await finish_sync_task_log(log_id, status=STATUS_FAILED, error_message=str(e))
        logger.error("Granular jobs failed with unexpected error: %s", e)
        raise


async def run_mengla_granular_jobs_manual() -> None:
    """手动触发补齐任务（使用缓存）"""
    await run_mengla_granular_jobs(force_refresh=False, trigger=TRIGGER_MANUAL)


async def run_mengla_granular_jobs_force() -> None:
    """强制刷新所有数据（跳过缓存）- 手动触发"""
    await run_mengla_granular_jobs(force_refresh=True, trigger=TRIGGER_MANUAL)


async def run_crawl_queue_once(max_batch: int = 1) -> None:
    """
    Queue consumer: pick one RUNNING/PENDING crawl job, run up to max_batch
    pending subtasks (query_mengla), update status and job stats.
    """
    if database.mongo_db is None:
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
        "description": "对 high/hot/chance/industryViewV2/industryTrendRange 按当日颗粒度补齐（有缓存时跳过）",
        "run": run_mengla_granular_jobs_manual,
    },
    "mengla_granular_force": {
        "name": "MengLa 强制全量采集",
        "description": "强制刷新所有接口数据（跳过缓存，直接从数据源采集）",
        "run": run_mengla_granular_jobs_force,
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

