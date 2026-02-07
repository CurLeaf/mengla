"""
MengLa 定时任务调度器

- run_period_collect(granularity): 统一采集入口（day/month/quarter/year）
- run_backfill_check(): 补数检查
- run_crawl_queue_once(): 队列消费者
- run_mengla_granular_jobs(): 全量多颗粒度补齐
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .infra import database
from .utils.period import make_period_keys, period_to_date_range
from .core.domain import query_mengla
from .core.queue import (
    get_next_job,
    claim_subtasks,
    set_job_running,
    set_subtask_success,
    set_subtask_failed,
    inc_job_stats,
    finish_job_if_done,
)
from .utils.category import get_top_level_cat_ids
from .utils.config import SCHEDULER_CONFIG, CRON_JOBS, CONCURRENT_CONFIG, get_collect_interval
from .infra.resilience import retry_async, RetryError
from .core.sync_task_log import (
    create_sync_task_log,
    update_sync_task_progress,
    finish_sync_task_log,
    is_cancelled,
    _unmark_cancelled,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_CANCELLED,
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
    使用统一的 run_period_collect 替代 4 个独立采集函数。
    """
    scheduler = AsyncIOScheduler(timezone=SCHEDULER_CONFIG["timezone"])

    # Daily collect: 04:00
    scheduler.add_job(
        run_period_collect,
        "cron",
        hour=4, minute=0,
        args=["day"],
        id="daily_collect",
        name="Daily Collect",
    )

    # Monthly collect: 3rd day 05:00
    scheduler.add_job(
        run_period_collect,
        "cron",
        day=3, hour=5, minute=0,
        args=["month"],
        id="monthly_collect",
        name="Monthly Collect",
    )

    # Quarterly collect: 10th day after quarter end 06:00
    scheduler.add_job(
        run_period_collect,
        "cron",
        month="1,4,7,10", day=10, hour=6, minute=0,
        args=["quarter"],
        id="quarterly_collect",
        name="Quarterly Collect",
    )

    # Yearly collect: Jan 20 07:00
    scheduler.add_job(
        run_period_collect,
        "cron",
        month=1, day=20, hour=7, minute=0,
        args=["year"],
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
# 统一采集入口（替代原来的 4 个独立函数）
# ==============================================================================
async def run_period_collect(
    granularity: str,
    target_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    统一采集入口，granularity = day | month | quarter | year。
    根据颗粒度自动计算目标日期和 period_key，遍历所有类目进行采集。
    失败后延迟重试一次。
    """
    # 计算目标日期
    target = target_date or _compute_target_date(granularity)
    periods = make_period_keys(target)
    top_cat_ids = _get_top_cat_ids_safe()

    stats = {"total": 0, "success": 0, "failed": 0}
    period_key = periods[granularity]
    interval = get_collect_interval()

    logger.info("Starting %s collect for period_key=%s", granularity, period_key)

    # 1) 非趋势接口
    for cat_id in top_cat_ids:
        for action in NON_TREND_ACTIONS:
            stats["total"] += 1
            success = await _collect_with_retry(
                action=action,
                cat_id=cat_id,
                date_type=granularity,
                timest=period_key,
                granularity=granularity,
            )
            if success:
                stats["success"] += 1
            else:
                stats["failed"] += 1
            await asyncio.sleep(random.uniform(interval * 0.5, interval * 1.5))

    # 2) 趋势接口：按年范围补齐
    year_str = str(target.year)
    start_year, end_year = period_to_date_range("year", year_str)
    date_type_map = {"day": "DAY", "month": "MONTH", "quarter": "QUARTERLY_FOR_YEAR", "year": "YEAR"}
    trend_date_type = date_type_map.get(granularity, "DAY")

    for cat_id in top_cat_ids:
        stats["total"] += 1
        success = await _collect_with_retry(
            action=TREND_ACTION,
            cat_id=cat_id,
            date_type=trend_date_type,
            timest="",
            star_range=start_year,
            end_range=end_year,
            granularity=granularity,
        )
        if success:
            stats["success"] += 1
        else:
            stats["failed"] += 1
        await asyncio.sleep(random.uniform(interval * 0.5, interval * 1.5))

    logger.info("%s collect completed: %s", granularity.capitalize(), stats)
    return stats


def _compute_target_date(granularity: str) -> datetime:
    """根据颗粒度计算默认的采集目标日期"""
    today = datetime.now()
    if granularity == "day":
        return today - timedelta(days=1)
    elif granularity == "month":
        first_of_this_month = today.replace(day=1)
        return first_of_this_month - timedelta(days=1)
    elif granularity == "quarter":
        current_quarter = (today.month - 1) // 3 + 1
        if current_quarter == 1:
            return datetime(today.year - 1, 10, 1)
        else:
            prev_quarter_month = (current_quarter - 2) * 3 + 1
            return datetime(today.year, prev_quarter_month, 1)
    elif granularity == "year":
        return datetime(today.year - 1, 1, 1)
    else:
        return today - timedelta(days=1)


async def _collect_with_retry(
    *,
    action: str,
    cat_id: str,
    date_type: str,
    timest: str = "",
    star_range: str = "",
    end_range: str = "",
    granularity: str = "day",
) -> bool:
    """
    执行一次采集，失败后延迟 5 秒重试一次。
    返回 True 表示最终成功。
    """
    try:
        await query_mengla(
            action=action,
            product_id="",
            catId=cat_id,
            dateType=date_type,
            timest=timest,
            starRange=star_range,
            endRange=end_range,
            extra=None,
        )
        return True
    except Exception as e:
        logger.warning(
            "Collect failed (will retry): action=%s cat_id=%s gran=%s error=%s",
            action, cat_id, granularity, e,
        )
        # 失败后延迟重试一次
        await asyncio.sleep(5)
        try:
            await query_mengla(
                action=action,
                product_id="",
                catId=cat_id,
                dateType=date_type,
                timest=timest,
                starRange=star_range,
                endRange=end_range,
                extra=None,
            )
            return True
        except Exception as e2:
            logger.error(
                "Retry also failed, skip: action=%s cat_id=%s gran=%s error=%s",
                action, cat_id, granularity, e2,
            )
            return False


# ==============================================================================
# 补数检查
# ==============================================================================
async def run_backfill_check() -> Dict[str, Any]:
    """检查最近数据是否有缺失，触发补采"""
    from .utils.config import COLLECTION_NAME

    if database.mongo_db is None:
        logger.warning("MongoDB not connected, skipping backfill check")
        return {"status": "skipped", "reason": "db_not_connected"}

    now = datetime.now()
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()
    interval = get_collect_interval()

    stats = {"checked": 0, "missing": 0, "backfilled": 0, "failed": 0}

    logger.info("Starting backfill check")

    collection = database.mongo_db[COLLECTION_NAME]

    for granularity in ["day", "month"]:
        period_key = periods[granularity]

        for cat_id in top_cat_ids:
            for action in NON_TREND_ACTIONS:
                stats["checked"] += 1

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
                        success = await _collect_with_retry(
                            action=action,
                            cat_id=cat_id,
                            date_type=granularity,
                            timest=period_key,
                            granularity=granularity,
                        )
                        if success:
                            stats["backfilled"] += 1
                        else:
                            stats["failed"] += 1
                        await asyncio.sleep(random.uniform(interval * 0.25, interval * 0.75))
                except Exception as e:
                    logger.warning("Backfill check error: %s", e)

    logger.info("Backfill check completed: %s", stats)
    return stats


# ==============================================================================
# 全量多颗粒度补齐
# ==============================================================================
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


async def run_mengla_granular_jobs(
    target_date: Optional[datetime] = None,
    force_refresh: bool = False,
    trigger: str = TRIGGER_SCHEDULED,
) -> None:
    """
    针对 MengLa 的 high / hot / chance / view / trend 五个接口，
    按日 / 月 / 季 / 年四种颗粒度进行补齐。
    """
    now = target_date or (datetime.now() - timedelta(days=1))
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()
    interval = get_collect_interval()

    non_trend_count = len(top_cat_ids) * 4 * 4
    trend_count = len(top_cat_ids) * 4
    total_tasks = non_trend_count + trend_count

    task_id = "mengla_granular_force" if force_refresh else "mengla_granular"
    task_name = "MengLa 强制全量采集" if force_refresh else "MengLa 日/月/季/年补齐"

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

    completed_count = 0
    failed_count = 0

    MAX_RETRIES = 5
    BASE_DELAY = 5.0
    MAX_DELAY = 120.0

    async def query_with_retry(**kwargs) -> bool:
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

    cancelled = False
    try:
        for cat_id in top_cat_ids:
            if is_cancelled(log_id):
                cancelled = True
                break
            for action in ["high", "hot", "chance", "industryViewV2"]:
                if is_cancelled(log_id):
                    cancelled = True
                    break
                for gran in ["day", "month", "quarter", "year"]:
                    if is_cancelled(log_id):
                        cancelled = True
                        break
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

                    await asyncio.sleep(random.uniform(interval * 1.5, interval * 4.5))
                if cancelled:
                    break
            if cancelled:
                break

        if not cancelled:
            year_str = str(now.year)
            start_year, end_year = period_to_date_range("year", year_str)

            for cat_id in top_cat_ids:
                if is_cancelled(log_id):
                    cancelled = True
                    break
                for gran in ["day", "month", "quarter", "year"]:
                    if is_cancelled(log_id):
                        cancelled = True
                        break
                    success = await query_with_retry(
                        action="industryTrendRange",
                        product_id="",
                        catId=cat_id,
                        dateType=gran.upper(),
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

                    await asyncio.sleep(random.uniform(interval * 1.5, interval * 4.5))
                if cancelled:
                    break

        if cancelled:
            logger.info(
                "Granular jobs cancelled: date=%s completed=%d failed=%d",
                now.date(), completed_count, failed_count,
            )
            _unmark_cancelled(log_id)
            return

        final_status = STATUS_FAILED if failed_count > 0 else STATUS_COMPLETED
        await finish_sync_task_log(log_id, status=final_status)

        logger.info(
            "Granular jobs completed: date=%s force_refresh=%s completed=%d failed=%d",
            now.date(), force_refresh, completed_count, failed_count
        )

    except Exception as e:
        _unmark_cancelled(log_id)
        await finish_sync_task_log(log_id, status=STATUS_FAILED, error_message=str(e))
        logger.error("Granular jobs failed with unexpected error: %s", e)
        raise


async def run_mengla_granular_jobs_manual() -> None:
    """手动触发补齐任务（使用缓存）"""
    await run_mengla_granular_jobs(force_refresh=False, trigger=TRIGGER_MANUAL)


async def run_mengla_granular_jobs_force() -> None:
    """强制刷新所有数据（跳过缓存）- 手动触发"""
    await run_mengla_granular_jobs(force_refresh=True, trigger=TRIGGER_MANUAL)


# ==============================================================================
# 队列消费者（使用原子 claim）
# ==============================================================================
async def run_crawl_queue_once(max_batch: int = 1) -> None:
    """
    Queue consumer: pick one RUNNING/PENDING crawl job, run up to max_batch
    pending subtasks (query_mengla), update status and job stats.
    使用 claim_subtasks 实现原子领取，防止并发消费者重复领取。
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

    # 原子 claim subtasks（替代原来的 get_pending_subtasks + set_subtask_running 两步操作）
    subtasks = await claim_subtasks(job_id, limit=max_batch)
    for sub in subtasks:
        sub_id = sub["_id"]
        action = sub.get("action", "")
        gran = sub.get("granularity", "day")
        period_key = sub.get("period_key", "")
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


# ==============================================================================
# 面板任务注册表
# ==============================================================================
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
        "description": "采集前一天的 day 颗粒度数据",
        "run": lambda: run_period_collect("day"),
    },
    "monthly_collect": {
        "name": "月度采集",
        "description": "采集上月的 month 颗粒度数据",
        "run": lambda: run_period_collect("month"),
    },
    "quarterly_collect": {
        "name": "季度采集",
        "description": "采集上季的 quarter 颗粒度数据",
        "run": lambda: run_period_collect("quarter"),
    },
    "yearly_collect": {
        "name": "年度采集",
        "description": "采集上年的 year 颗粒度数据",
        "run": lambda: run_period_collect("year"),
    },
    "backfill_check": {
        "name": "补数检查",
        "description": "检查最近数据是否有缺失，触发补采",
        "run": run_backfill_check,
    },
}
