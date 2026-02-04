import asyncio
import logging
import random
from datetime import datetime
from typing import Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .database import mongo_db
from .period_utils import make_period_keys, period_to_date_range
from .mengla_domain import query_mengla_domain
from .mengla_crawl_queue import (
    get_next_job,
    get_pending_subtasks,
    set_job_running,
    set_subtask_running,
    set_subtask_success,
    set_subtask_failed,
    inc_job_stats,
    finish_job_if_done,
)
from .category_utils import get_top_level_cat_ids

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
    """
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    
    # MengLa 每日任务：凌晨 2:10 执行，按日/月/季/年颗粒度对 5 个接口进行补齐
    scheduler.add_job(run_mengla_granular_jobs, "cron", hour=2, minute=10)
    
    # 队列消费：定期执行待处理的爬取子任务（历史全量补齐）
    # 每次仅执行少量子任务，由 APScheduler 控制队列轮询频率。
    # 这里将间隔设置为约 3~5 分钟（4 分钟基础 + 1 分钟抖动），
    # 保证各个子任务以队列形式错峰执行，避免频繁打爆托管任务。
    scheduler.add_job(
        run_crawl_queue_once,
        "interval",
        seconds=240,  # 4 分钟
        jitter=60,    # ±1 分钟抖动 => 约 3~5 分钟
    )
    
    return scheduler


MENG_LA_ACTIONS: Dict[str, List[str]] = {
    "high": ["day", "month", "quarter", "year"],
    "hot": ["day", "month", "quarter", "year"],
    "chance": ["day", "month", "quarter", "year"],
    "industryViewV2": ["day", "month", "quarter", "year"],
    "industryTrendRange": ["day", "month", "quarter", "year"],
}


async def run_mengla_jobs(target_date: Optional[datetime] = None) -> None:
    """
    每天凌晨针对 MengLa 的 high / view / trend 三个接口进行补齐：
    - 先计算当日对应的 day/month/quarter/year period_key
    - 对于每个 action+granularity，复用 query_mengla_domain 的查 Mongo + 调第三方逻辑
    """
    now = target_date or datetime.now()
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()

    for cat_id in top_cat_ids:
        for action, granularities in MENG_LA_ACTIONS.items():
            for gran in granularities:
                period_key = periods[gran]
                await query_mengla_domain(  # 返回 (data, source)，此处仅触发拉取与落库
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
    所有查询统一复用 query_mengla_domain（先 Mongo / 再 Redis / 后采集）。
    """
    now = target_date or datetime.now()
    periods = make_period_keys(now)
    top_cat_ids = _get_top_cat_ids_safe()

    # 1) 非趋势接口：high / hot / chance / industryViewV2
    for cat_id in top_cat_ids:
        for action in ["high", "hot", "chance", "industryViewV2"]:
            for gran in ["day", "month", "quarter", "year"]:
                period_key = periods[gran]
                await query_mengla_domain(
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
            await query_mengla_domain(
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
    pending subtasks (query_mengla_domain), update status and job stats.
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
                await query_mengla_domain(
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
                await query_mengla_domain(
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
}

