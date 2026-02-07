"""
Queue-based MengLa full crawl: crawl_jobs (parent) + crawl_subtasks (children).
Used for historical full crawls; worker consumes pending subtasks periodically.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument

from ..infra.database import mongo_db
from .domain import VALID_ACTIONS
from ..utils.period import period_keys_in_range

# Collection names
CRAWL_JOBS = "crawl_jobs"
CRAWL_SUBTASKS = "crawl_subtasks"

# Job status
JOB_PENDING = "PENDING"
JOB_RUNNING = "RUNNING"
JOB_COMPLETED = "COMPLETED"
JOB_FAILED = "FAILED"
JOB_CANCELLED = "CANCELLED"

# Subtask status
SUB_PENDING = "PENDING"
SUB_RUNNING = "RUNNING"
SUB_SUCCESS = "SUCCESS"
SUB_FAILED = "FAILED"

DEFAULT_ACTIONS = ["high", "hot", "chance", "industryViewV2", "industryTrendRange"]
DEFAULT_GRANULARITIES = ["day", "month", "quarter", "year"]


async def create_crawl_job(
    start_date: str,
    end_date: str,
    granularities: Optional[List[str]] = None,
    actions: Optional[List[str]] = None,
    cat_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Any]:
    """
    Create a crawl_job (status=PENDING) and insert all subtasks.
    Returns job _id or None if mongo_db is not available.
    """
    if mongo_db is None:
        return None

    granules = granularities or DEFAULT_GRANULARITIES
    acts = actions or DEFAULT_ACTIONS
    acts = [a for a in acts if a in VALID_ACTIONS]
    config = {
        "start_date": start_date,
        "end_date": end_date,
        "granularities": granules,
        "actions": acts,
        "catId": (cat_id or "").strip(),
        "extra": extra or {},
    }

    now = datetime.utcnow()
    job_doc = {
        "type": "mengla_full_crawl",
        "status": JOB_PENDING,
        "config": config,
        "stats": {"total_subtasks": 0, "completed": 0, "failed": 0},
        "created_at": now,
        "updated_at": now,
    }
    result = await mongo_db[CRAWL_JOBS].insert_one(job_doc)
    job_id = result.inserted_id

    total = 0
    for action in acts:
        for gran in granules:
            try:
                keys = period_keys_in_range(gran, start_date, end_date)
            except Exception:
                continue
            for period_key in keys:
                sub_doc = {
                    "job_id": job_id,
                    "action": action,
                    "granularity": gran,
                    "period_key": period_key,
                    "status": SUB_PENDING,
                    "attempts": 0,
                    "created_at": now,
                    "updated_at": now,
                }
                await mongo_db[CRAWL_SUBTASKS].insert_one(sub_doc)
                total += 1

    await mongo_db[CRAWL_JOBS].update_one(
        {"_id": job_id},
        {"$set": {"stats.total_subtasks": total, "updated_at": datetime.utcnow()}},
    )
    return job_id


async def get_next_job() -> Optional[Dict[str, Any]]:
    """Find one RUNNING or PENDING job (oldest first)."""
    if mongo_db is None:
        return None
    job = await mongo_db[CRAWL_JOBS].find_one(
        {"status": {"$in": [JOB_RUNNING, JOB_PENDING]}},
        sort=[("created_at", 1)],
    )
    return job


async def get_pending_subtasks(job_id: Any, limit: int = 1) -> List[Dict[str, Any]]:
    """Return up to `limit` PENDING subtasks for the job, oldest first."""
    if mongo_db is None:
        return []
    cursor = mongo_db[CRAWL_SUBTASKS].find(
        {"job_id": job_id, "status": SUB_PENDING},
    ).sort("created_at", 1)
    return await cursor.to_list(length=limit)


async def claim_next_subtask(job_id: Any) -> Optional[Dict[str, Any]]:
    """
    原子 claim：使用 find_one_and_update 将一个 PENDING subtask
    原子地标记为 RUNNING 并返回，避免并发消费者重复领取。
    """
    if mongo_db is None:
        return None
    now = datetime.utcnow()
    doc = await mongo_db[CRAWL_SUBTASKS].find_one_and_update(
        {"job_id": job_id, "status": SUB_PENDING},
        {
            "$set": {"status": SUB_RUNNING, "started_at": now, "updated_at": now},
            "$inc": {"attempts": 1},
        },
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER,
    )
    return doc


async def claim_subtasks(job_id: Any, limit: int = 1) -> List[Dict[str, Any]]:
    """原子 claim 多个 subtask（逐条 find_one_and_update）。"""
    claimed = []
    for _ in range(limit):
        doc = await claim_next_subtask(job_id)
        if doc is None:
            break
        claimed.append(doc)
    return claimed


async def set_job_running(job_id: Any) -> None:
    if mongo_db is None:
        return
    await mongo_db[CRAWL_JOBS].update_one(
        {"_id": job_id},
        {"$set": {"status": JOB_RUNNING, "updated_at": datetime.utcnow()}},
    )


async def set_subtask_running(subtask_id: Any) -> None:
    if mongo_db is None:
        return
    now = datetime.utcnow()
    await mongo_db[CRAWL_SUBTASKS].update_one(
        {"_id": subtask_id},
        {
            "$set": {"status": SUB_RUNNING, "started_at": now, "updated_at": now},
            "$inc": {"attempts": 1},
        },
    )


async def set_subtask_success(subtask_id: Any) -> None:
    if mongo_db is None:
        return
    now = datetime.utcnow()
    await mongo_db[CRAWL_SUBTASKS].update_one(
        {"_id": subtask_id},
        {"$set": {"status": SUB_SUCCESS, "finished_at": now, "updated_at": now}},
    )


async def set_subtask_failed(subtask_id: Any, error_message: str = "") -> None:
    if mongo_db is None:
        return
    now = datetime.utcnow()
    await mongo_db[CRAWL_SUBTASKS].update_one(
        {"_id": subtask_id},
        {
            "$set": {
                "status": SUB_FAILED,
                "finished_at": now,
                "last_error": error_message[:2000] if error_message else "",
                "updated_at": now,
            }
        },
    )


async def inc_job_stats(job_id: Any, completed_delta: int = 0, failed_delta: int = 0) -> None:
    if mongo_db is None:
        return
    if not completed_delta and not failed_delta:
        return
    await mongo_db[CRAWL_JOBS].update_one(
        {"_id": job_id},
        {
            "$set": {"updated_at": datetime.utcnow()},
            "$inc": {
                "stats.completed": completed_delta,
                "stats.failed": failed_delta,
            },
        },
    )


async def finish_job_if_done(job_id: Any) -> None:
    """
    If no subtasks are PENDING or RUNNING, set job to COMPLETED or FAILED.
    """
    if mongo_db is None:
        return
    pending = await mongo_db[CRAWL_SUBTASKS].count_documents(
        {"job_id": job_id, "status": {"$in": [SUB_PENDING, SUB_RUNNING]}},
    )
    if pending > 0:
        return
    failed = await mongo_db[CRAWL_SUBTASKS].count_documents(
        {"job_id": job_id, "status": SUB_FAILED},
    )
    new_status = JOB_FAILED if failed > 0 else JOB_COMPLETED
    await mongo_db[CRAWL_JOBS].update_one(
        {"_id": job_id},
        {"$set": {"status": new_status, "updated_at": datetime.utcnow()}},
    )
