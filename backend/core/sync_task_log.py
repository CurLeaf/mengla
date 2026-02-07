"""
Sync Task Log: 记录同步任务的执行状态和进度。
用于在管理中心展示当天的采集任务列表。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId

from ..infra.database import mongo_db

# Collection name
SYNC_TASK_LOGS = "sync_task_logs"

# Task status
STATUS_RUNNING = "RUNNING"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"

# Trigger types
TRIGGER_MANUAL = "manual"
TRIGGER_SCHEDULED = "scheduled"


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
    if mongo_db is None:
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
    
    result = await mongo_db[SYNC_TASK_LOGS].insert_one(doc)
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
    if mongo_db is None or not log_id:
        return
    
    try:
        oid = ObjectId(log_id)
    except Exception:
        return
    
    update: Dict[str, Any] = {"$set": {"updated_at": datetime.utcnow()}}
    
    if completed_delta or failed_delta:
        update["$inc"] = {}
        if completed_delta:
            update["$inc"]["progress.completed"] = completed_delta
        if failed_delta:
            update["$inc"]["progress.failed"] = failed_delta
    
    await mongo_db[SYNC_TASK_LOGS].update_one({"_id": oid}, update)


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
    if mongo_db is None or not log_id:
        return
    
    try:
        oid = ObjectId(log_id)
    except Exception:
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
    
    await mongo_db[SYNC_TASK_LOGS].update_one({"_id": oid}, update)


async def get_today_sync_tasks() -> List[Dict[str, Any]]:
    """
    获取当天的同步任务列表。
    
    Returns:
        任务列表，按创建时间倒序排列
    """
    if mongo_db is None:
        return []
    
    # 计算今天的开始时间 (UTC)
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    cursor = mongo_db[SYNC_TASK_LOGS].find(
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
    if mongo_db is None or not log_id:
        return None
    
    try:
        oid = ObjectId(log_id)
    except Exception:
        return None
    
    task = await mongo_db[SYNC_TASK_LOGS].find_one({"_id": oid})
    
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
    if mongo_db is None:
        return None
    
    task = await mongo_db[SYNC_TASK_LOGS].find_one({
        "task_id": task_id,
        "status": STATUS_RUNNING,
    })
    
    if task:
        task["id"] = str(task.pop("_id"))
        return task
    
    return None
