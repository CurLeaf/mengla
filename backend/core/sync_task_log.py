"""
Sync Task Log: 记录同步任务的执行状态和进度。
用于在管理中心展示当天的采集任务列表。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from bson import ObjectId

from ..infra import database

logger = logging.getLogger("mengla-backend")

# Collection name
SYNC_TASK_LOGS = "sync_task_logs"

# Task status
STATUS_RUNNING = "RUNNING"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"
STATUS_CANCELLED = "CANCELLED"

# Trigger types
TRIGGER_MANUAL = "manual"
TRIGGER_SCHEDULED = "scheduled"

# ---------------------------------------------------------------------------
# 协作式取消机制
# 运行中的任务会在每次循环迭代时检查此集合，如果发现自己的 log_id 在其中，
# 则主动停止执行。
# ---------------------------------------------------------------------------
_cancelled_logs: Set[str] = set()


def is_cancelled(log_id: Optional[str]) -> bool:
    """检查指定的任务日志是否已被取消。"""
    if not log_id:
        return False
    return log_id in _cancelled_logs


def _mark_cancelled(log_id: str) -> None:
    """将 log_id 加入取消集合。"""
    _cancelled_logs.add(log_id)


def _unmark_cancelled(log_id: str) -> None:
    """将 log_id 从取消集合中移除（清理）。"""
    _cancelled_logs.discard(log_id)


async def create_sync_task_log(
    task_id: str,
    task_name: str,
    total: int,
    trigger: str = TRIGGER_MANUAL,
) -> Optional[str]:
    """
    创建同步任务日志记录。
    
    Args:
        task_id: 任务类型 ID (如 "mengla_granular_force")
        task_name: 任务显示名称
        total: 总子任务数量
        trigger: 触发方式 ("manual" 或 "scheduled")
    
    Returns:
        日志记录 ID (字符串) 或 None
    """
    if database.mongo_db is None:
        logger.warning("MongoDB not available, cannot create sync task log for task_id=%s", task_id)
        return None
    
    now = datetime.utcnow()
    doc = {
        "task_id": task_id,
        "task_name": task_name,
        "status": STATUS_RUNNING,
        "progress": {
            "total": total,
            "completed": 0,
            "failed": 0,
        },
        "started_at": now,
        "finished_at": None,
        "trigger": trigger,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }
    
    result = await database.mongo_db[SYNC_TASK_LOGS].insert_one(doc)
    return str(result.inserted_id)


async def update_sync_task_progress(
    log_id: str,
    completed_delta: int = 0,
    failed_delta: int = 0,
) -> None:
    """
    更新同步任务的进度。
    
    Args:
        log_id: 日志记录 ID
        completed_delta: 完成数增量
        failed_delta: 失败数增量
    """
    if database.mongo_db is None or not log_id:
        if database.mongo_db is None:
            logger.warning("MongoDB not available, cannot update sync task progress for log_id=%s", log_id)
        return
    
    try:
        oid = ObjectId(log_id)
    except Exception:
        logger.warning("Invalid ObjectId for sync task progress update: log_id=%s", log_id)
        return
    
    update: Dict[str, Any] = {"$set": {"updated_at": datetime.utcnow()}}
    
    if completed_delta or failed_delta:
        update["$inc"] = {}
        if completed_delta:
            update["$inc"]["progress.completed"] = completed_delta
        if failed_delta:
            update["$inc"]["progress.failed"] = failed_delta
    
    await database.mongo_db[SYNC_TASK_LOGS].update_one({"_id": oid}, update)


async def finish_sync_task_log(
    log_id: str,
    status: str = STATUS_COMPLETED,
    error_message: Optional[str] = None,
) -> None:
    """
    完成同步任务日志记录。
    
    Args:
        log_id: 日志记录 ID
        status: 最终状态 (COMPLETED 或 FAILED)
        error_message: 错误信息 (仅当 status=FAILED 时)
    """
    if database.mongo_db is None or not log_id:
        if database.mongo_db is None:
            logger.warning("MongoDB not available, cannot finish sync task log for log_id=%s", log_id)
        return
    
    try:
        oid = ObjectId(log_id)
    except Exception:
        logger.warning("Invalid ObjectId for sync task log finish: log_id=%s", log_id)
        return
    
    now = datetime.utcnow()
    update = {
        "$set": {
            "status": status,
            "finished_at": now,
            "updated_at": now,
        }
    }
    
    if error_message:
        update["$set"]["error_message"] = error_message[:2000]
    
    await database.mongo_db[SYNC_TASK_LOGS].update_one({"_id": oid}, update)


async def get_today_sync_tasks() -> List[Dict[str, Any]]:
    """
    获取当天的同步任务列表。
    
    Returns:
        任务列表，按创建时间倒序排列
    """
    if database.mongo_db is None:
        return []
    
    # 计算今天的开始时间 (UTC)
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    cursor = database.mongo_db[SYNC_TASK_LOGS].find(
        {"created_at": {"$gte": today_start}},
    ).sort("created_at", -1)
    
    tasks = await cursor.to_list(length=100)
    
    # 转换 ObjectId 为字符串
    result = []
    for task in tasks:
        task["id"] = str(task.pop("_id"))
        result.append(task)
    
    return result


async def get_sync_task_detail(log_id: str) -> Optional[Dict[str, Any]]:
    """
    获取单个同步任务的详情。
    
    Args:
        log_id: 日志记录 ID
    
    Returns:
        任务详情或 None
    """
    if database.mongo_db is None or not log_id:
        return None
    
    try:
        oid = ObjectId(log_id)
    except Exception:
        return None
    
    task = await database.mongo_db[SYNC_TASK_LOGS].find_one({"_id": oid})
    
    if task:
        task["id"] = str(task.pop("_id"))
        return task
    
    return None


async def get_running_task_by_task_id(task_id: str) -> Optional[Dict[str, Any]]:
    """
    获取指定任务类型的运行中任务。
    用于避免重复启动同一任务。
    
    Args:
        task_id: 任务类型 ID
    
    Returns:
        运行中的任务或 None
    """
    if database.mongo_db is None:
        return None
    
    task = await database.mongo_db[SYNC_TASK_LOGS].find_one({
        "task_id": task_id,
        "status": STATUS_RUNNING,
    })
    
    if task:
        task["id"] = str(task.pop("_id"))
        return task
    
    return None


# ---------------------------------------------------------------------------
# 取消任务
# ---------------------------------------------------------------------------
async def cancel_sync_task(log_id: str) -> Dict[str, Any]:
    """
    取消一个运行中的同步任务。
    
    1. 将 log_id 加入协作取消集合（运行中的任务会在下次迭代时自行停止）
    2. 在数据库中将状态标记为 CANCELLED
    
    Args:
        log_id: 日志记录 ID
    
    Returns:
        操作结果
    """
    if database.mongo_db is None:
        return {"success": False, "message": "数据库不可用"}

    try:
        oid = ObjectId(log_id)
    except Exception:
        return {"success": False, "message": f"无效的 log_id: {log_id}"}

    # 检查任务是否存在且正在运行
    task = await database.mongo_db[SYNC_TASK_LOGS].find_one({"_id": oid})
    if task is None:
        return {"success": False, "message": "任务不存在"}

    if task["status"] != STATUS_RUNNING:
        return {"success": False, "message": f"任务不在运行中（当前状态: {task['status']}）"}

    # 1. 通知协作取消机制
    _mark_cancelled(log_id)

    # 2. 更新数据库状态
    now = datetime.utcnow()
    await database.mongo_db[SYNC_TASK_LOGS].update_one(
        {"_id": oid},
        {"$set": {
            "status": STATUS_CANCELLED,
            "error_message": "用户手动取消",
            "finished_at": now,
            "updated_at": now,
        }},
    )

    logger.info("Sync task cancelled: log_id=%s task_id=%s", log_id, task.get("task_id"))
    return {"success": True, "message": "任务已取消"}


# ---------------------------------------------------------------------------
# 删除任务（可选：同时删除采集数据）
# ---------------------------------------------------------------------------
async def delete_sync_task(log_id: str, delete_data: bool = False) -> Dict[str, Any]:
    """
    删除一个同步任务日志记录。
    
    如果 delete_data=True，还会删除该任务时间窗口内写入的采集数据。
    注意：运行中的任务不能删除，需先取消。
    
    Args:
        log_id: 日志记录 ID
        delete_data: 是否同时删除该任务采集的数据
    
    Returns:
        操作结果（含删除的数据条数）
    """
    if database.mongo_db is None:
        return {"success": False, "message": "数据库不可用"}

    try:
        oid = ObjectId(log_id)
    except Exception:
        return {"success": False, "message": f"无效的 log_id: {log_id}"}

    task = await database.mongo_db[SYNC_TASK_LOGS].find_one({"_id": oid})
    if task is None:
        return {"success": False, "message": "任务不存在"}

    if task["status"] == STATUS_RUNNING:
        return {"success": False, "message": "运行中的任务不能删除，请先取消"}

    deleted_data_count = 0

    # 删除该任务时间窗口内的采集数据
    if delete_data:
        from ..utils.config import COLLECTION_NAME

        started_at = task.get("started_at")
        finished_at = task.get("finished_at") or task.get("updated_at")

        if started_at and finished_at:
            data_filter = {
                "updated_at": {
                    "$gte": started_at,
                    "$lte": finished_at,
                },
            }
            result = await database.mongo_db[COLLECTION_NAME].delete_many(data_filter)
            deleted_data_count = result.deleted_count
            logger.info(
                "Deleted %d data records for sync task %s (time range: %s ~ %s)",
                deleted_data_count, log_id, started_at, finished_at,
            )

    # 删除日志记录本身
    await database.mongo_db[SYNC_TASK_LOGS].delete_one({"_id": oid})

    # 清理取消标记（如果有）
    _unmark_cancelled(log_id)

    logger.info(
        "Sync task deleted: log_id=%s delete_data=%s deleted_data_count=%d",
        log_id, delete_data, deleted_data_count,
    )
    return {
        "success": True,
        "message": "任务已删除",
        "deleted_data_count": deleted_data_count,
    }


# ---------------------------------------------------------------------------
# 启动时清理：将残留的 RUNNING 状态标记为 FAILED
# ---------------------------------------------------------------------------
async def cleanup_stale_running_tasks() -> int:
    """
    服务启动时调用：将所有 status=RUNNING 的同步任务标记为 FAILED。
    这些任务是上一次服务重启/崩溃时未正常结束的"僵尸"任务。
    
    Returns:
        清理的任务数量
    """
    if database.mongo_db is None:
        return 0

    now = datetime.utcnow()
    result = await database.mongo_db[SYNC_TASK_LOGS].update_many(
        {"status": STATUS_RUNNING},
        {"$set": {
            "status": STATUS_FAILED,
            "error_message": "任务被中断（服务重启）",
            "finished_at": now,
            "updated_at": now,
        }},
    )

    count = result.modified_count
    if count > 0:
        logger.info("Cleaned up %d stale RUNNING sync task(s) on startup", count)
    return count
