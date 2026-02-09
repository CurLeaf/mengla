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
from typing import Any, Dict, List, Optional, Union

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
from .utils.config import SCHEDULER_CONFIG, CRON_JOBS, CONCURRENT_CONFIG, get_collect_interval, parse_cron_expr
from .infra.resilience import retry_async, RetryError
from .core.sync_task_log import (
    create_sync_task_log,
    update_sync_task_progress,
    finish_sync_task_log,
    get_running_task_by_task_id,
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

    # 从 CRON_JOBS 配置注册定时采集任务（支持环境变量覆盖 cron 表达式）
    _cron_job_defs = [
        ("daily_collect",     run_period_collect,  ["day"],     "Daily Collect"),
        ("monthly_collect",   run_period_collect,  ["month"],   "Monthly Collect"),
        ("quarterly_collect", run_period_collect,  ["quarter"], "Quarterly Collect"),
        ("yearly_collect",    run_period_collect,  ["year"],    "Yearly Collect"),
        ("backfill_check",    run_backfill_check,  [],          "Backfill Check"),
    ]

    for job_id, func, args, name in _cron_job_defs:
        cron_expr = CRON_JOBS[job_id]["cron"]
        cron_params = parse_cron_expr(cron_expr)
        scheduler.add_job(
            func,
            "cron",
            **cron_params,
            args=args or None,
            id=job_id,
            name=name,
        )
        logger.info("Registered cron job: %s (%s) cron=%s", job_id, name, cron_expr)

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
_GRANULARITY_TASK_NAMES: Dict[str, str] = {
    "day": "每日采集",
    "month": "月度采集",
    "quarter": "季度采集",
    "year": "年度采集",
}


async def run_period_collect(
    granularity: str,
    target_date: Optional[datetime] = None,
    trigger: str = TRIGGER_SCHEDULED,
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

    # 预计任务数：非趋势接口 (cats * 4) + 趋势接口 (cats * 1)
    total_tasks = len(top_cat_ids) * (len(NON_TREND_ACTIONS) + 1)
    task_id = f"{granularity}_collect"
    task_name = _GRANULARITY_TASK_NAMES.get(granularity, f"{granularity} 采集")

    # 重叠防护：原子检查并创建，防止并发启动同一任务
    # 先检查是否有同类型任务正在运行
    existing = await get_running_task_by_task_id(task_id)
    if existing:
        logger.warning("Task %s already running (log_id=%s), skip", task_id, existing["id"])
        return {"skipped": True, "reason": "already_running", "existing_log_id": existing["id"]}

    log_id = await create_sync_task_log(
        task_id=task_id,
        task_name=task_name,
        total=total_tasks,
        trigger=trigger,
    )

    # 二次检查：创建后再次确认没有并发启动的同类任务（双重防护）
    if database.mongo_db is not None and log_id:
        from bson import ObjectId
        count = await database.mongo_db["sync_task_logs"].count_documents({
            "task_id": task_id,
            "status": "RUNNING",
        })
        if count > 1:
            # 有并发竞争，取消当前创建的任务（让先创建的继续）
            logger.warning("Task %s concurrent start detected, cancelling duplicate log_id=%s", task_id, log_id)
            await finish_sync_task_log(log_id, STATUS_CANCELLED, error_message="并发启动冲突，自动取消")
            return {"skipped": True, "reason": "concurrent_conflict"}

    logger.info("Starting %s collect for period_key=%s log_id=%s", granularity, period_key, log_id)

    max_parallel = CONCURRENT_CONFIG.get("max_concurrent", 5)

    try:
        # 1) 非趋势接口 —— 同一 cat_id 的不同 action 并行
        for cat_id in top_cat_ids:
            if is_cancelled(log_id):
                break

            sem = asyncio.Semaphore(max_parallel)

            async def _do_collect(act: str, cid: str) -> bool:
                async with sem:
                    return await _collect_with_retry(
                        action=act,
                        cat_id=cid,
                        date_type=granularity,
                        timest=period_key,
                        granularity=granularity,
                    )

            tasks_batch = [_do_collect(action, cat_id) for action in NON_TREND_ACTIONS]
            stats["total"] += len(tasks_batch)
            results = await asyncio.gather(*tasks_batch, return_exceptions=True)

            for r in results:
                if isinstance(r, Exception):
                    stats["failed"] += 1
                    await update_sync_task_progress(log_id, failed_delta=1)
                elif r:
                    stats["success"] += 1
                    await update_sync_task_progress(log_id, completed_delta=1)
                else:
                    stats["failed"] += 1
                    await update_sync_task_progress(log_id, failed_delta=1)

            # 类目之间加间隔，避免上游限流
            await asyncio.sleep(random.uniform(interval * 0.5, interval * 1.5))

        if is_cancelled(log_id):
            _unmark_cancelled(log_id)
            logger.info("%s collect cancelled: %s", granularity.capitalize(), stats)
            return stats

        # 2) 趋势接口：按年范围补齐
        year_str = str(target.year)
        start_year, end_year = period_to_date_range("year", year_str)
        date_type_map = {"day": "DAY", "month": "MONTH", "quarter": "QUARTERLY_FOR_YEAR", "year": "YEAR"}
        trend_date_type = date_type_map.get(granularity, "DAY")

        for cat_id in top_cat_ids:
            if is_cancelled(log_id):
                break
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
                await update_sync_task_progress(log_id, completed_delta=1)
            else:
                stats["failed"] += 1
                await update_sync_task_progress(log_id, failed_delta=1)
            await asyncio.sleep(random.uniform(interval * 0.5, interval * 1.5))

        if is_cancelled(log_id):
            _unmark_cancelled(log_id)
            logger.info("%s collect cancelled: %s", granularity.capitalize(), stats)
            return stats

        final_status = STATUS_FAILED if stats["failed"] > 0 else STATUS_COMPLETED
        await finish_sync_task_log(log_id, status=final_status)

        logger.info("%s collect completed: %s", granularity.capitalize(), stats)
        return stats

    except (Exception, asyncio.CancelledError) as e:
        _unmark_cancelled(log_id)
        error_msg = "任务被中断（服务重启）" if isinstance(e, asyncio.CancelledError) else str(e)
        await finish_sync_task_log(log_id, status=STATUS_FAILED, error_message=error_msg)
        logger.error("%s collect failed: %s", granularity.capitalize(), e)
        raise


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
async def run_backfill_check(
    trigger: str = TRIGGER_SCHEDULED,
) -> Dict[str, Any]:
    """检查最近数据是否有缺失，触发补采"""
    from .utils.config import COLLECTION_NAME

    if database.mongo_db is None:
        logger.warning("MongoDB not connected, skipping backfill check")
        return {"status": "skipped", "reason": "db_not_connected"}

    now = datetime.now()
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()
    interval = get_collect_interval()

    # 检查总数: 2 granularities * cats * 4 actions
    total_checks = 2 * len(top_cat_ids) * len(NON_TREND_ACTIONS)

    # 重叠防护
    existing = await get_running_task_by_task_id("backfill_check")
    if existing:
        logger.warning("Task backfill_check already running (log_id=%s), skip", existing["id"])
        return {"skipped": True, "reason": "already_running", "existing_log_id": existing["id"]}

    log_id = await create_sync_task_log(
        task_id="backfill_check",
        task_name="补数检查",
        total=total_checks,
        trigger=trigger,
    )

    stats = {"checked": 0, "missing": 0, "backfilled": 0, "failed": 0}

    logger.info("Starting backfill check log_id=%s", log_id)

    collection = database.mongo_db[COLLECTION_NAME]

    try:
        for granularity in ["day", "month"]:
            period_key = periods[granularity]

            for cat_id in top_cat_ids:
                if is_cancelled(log_id):
                    break
                for action in NON_TREND_ACTIONS:
                    if is_cancelled(log_id):
                        break
                    stats["checked"] += 1

                    query = {
                        "action": action,
                        "cat_id": cat_id or "",
                        "granularity": granularity,
                        "period_key": period_key,
                    }

                    try:
                        doc = await collection.find_one(query)
                        need_backfill = False
                        if doc is None:
                            need_backfill = True
                            stats["missing"] += 1
                        elif doc.get("is_empty", False):
                            # 之前采集过但数据为空，重新尝试
                            need_backfill = True
                            stats["missing"] += 1

                        if need_backfill:
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

                    await update_sync_task_progress(log_id, completed_delta=1)
                if is_cancelled(log_id):
                    break
            if is_cancelled(log_id):
                break

        if is_cancelled(log_id):
            _unmark_cancelled(log_id)
            logger.info("Backfill check cancelled: %s", stats)
            return stats

        final_status = STATUS_FAILED if stats["failed"] > 0 else STATUS_COMPLETED
        await finish_sync_task_log(log_id, status=final_status)

        logger.info("Backfill check completed: %s", stats)
        return stats

    except (Exception, asyncio.CancelledError) as e:
        _unmark_cancelled(log_id)
        error_msg = "任务被中断（服务重启）" if isinstance(e, asyncio.CancelledError) else str(e)
        await finish_sync_task_log(log_id, status=STATUS_FAILED, error_message=error_msg)
        logger.error("Backfill check failed: %s", e)
        raise


# ==============================================================================
# 全量多颗粒度补齐
# ==============================================================================
async def run_mengla_jobs(
    target_date: Optional[datetime] = None,
    trigger: str = TRIGGER_MANUAL,
) -> None:
    """
    每天凌晨针对 MengLa 的 high / view / trend 三个接口进行补齐：
    - 先计算当日对应的 day/month/quarter/year period_key
    - 对于每个 action+granularity，复用 query_mengla 的查 Mongo + 调第三方逻辑
    """
    now = target_date or datetime.now()
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()

    # 总任务数: cats * 5 actions * 4 granularities
    total_tasks = len(top_cat_ids) * sum(len(g) for g in MENG_LA_ACTIONS.values())

    log_id = await create_sync_task_log(
        task_id="mengla_single_day",
        task_name="MengLa 单日补齐",
        total=total_tasks,
        trigger=trigger,
    )

    completed = 0
    failed = 0

    try:
        for cat_id in top_cat_ids:
            if is_cancelled(log_id):
                break
            for action, granularities in MENG_LA_ACTIONS.items():
                if is_cancelled(log_id):
                    break
                for gran in granularities:
                    if is_cancelled(log_id):
                        break
                    period_key = periods[gran]
                    try:
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
                        completed += 1
                        await update_sync_task_progress(log_id, completed_delta=1)
                    except Exception as e:
                        failed += 1
                        await update_sync_task_progress(log_id, failed_delta=1)
                        logger.warning("MengLa single day error: action=%s cat=%s gran=%s err=%s", action, cat_id, gran, e)

        if is_cancelled(log_id):
            _unmark_cancelled(log_id)
            logger.info("MengLa single day cancelled: completed=%d failed=%d", completed, failed)
            return

        final_status = STATUS_FAILED if failed > 0 else STATUS_COMPLETED
        await finish_sync_task_log(log_id, status=final_status)
        logger.info("MengLa single day completed: completed=%d failed=%d", completed, failed)

    except (Exception, asyncio.CancelledError) as e:
        _unmark_cancelled(log_id)
        error_msg = "任务被中断（服务重启）" if isinstance(e, asyncio.CancelledError) else str(e)
        await finish_sync_task_log(log_id, status=STATUS_FAILED, error_message=error_msg)
        logger.error("MengLa single day failed: %s", e)
        raise


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

    # 重叠防护
    existing = await get_running_task_by_task_id(task_id)
    if existing:
        logger.warning("Task %s already running (log_id=%s), skip", task_id, existing["id"])
        return

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

    except (Exception, asyncio.CancelledError) as e:
        _unmark_cancelled(log_id)
        error_msg = "任务被中断（服务重启）" if isinstance(e, asyncio.CancelledError) else str(e)
        await finish_sync_task_log(log_id, status=STATUS_FAILED, error_message=error_msg)
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
    # get_next_job 已原子认领 PENDING->RUNNING，无需再调用 set_job_running
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
        "run": lambda: run_mengla_jobs(trigger=TRIGGER_MANUAL),
    },
    "daily_collect": {
        "name": "每日主采集",
        "description": "采集前一天的 day 颗粒度数据",
        "run": lambda: run_period_collect("day", trigger=TRIGGER_MANUAL),
    },
    "monthly_collect": {
        "name": "月度采集",
        "description": "采集上月的 month 颗粒度数据",
        "run": lambda: run_period_collect("month", trigger=TRIGGER_MANUAL),
    },
    "quarterly_collect": {
        "name": "季度采集",
        "description": "采集上季的 quarter 颗粒度数据",
        "run": lambda: run_period_collect("quarter", trigger=TRIGGER_MANUAL),
    },
    "yearly_collect": {
        "name": "年度采集",
        "description": "采集上年的 year 颗粒度数据",
        "run": lambda: run_period_collect("year", trigger=TRIGGER_MANUAL),
    },
    "backfill_check": {
        "name": "补数检查",
        "description": "检查最近数据是否有缺失，触发补采",
        "run": lambda: run_backfill_check(trigger=TRIGGER_MANUAL),
    },
}
