"""同步任务日志路由"""
from fastapi import APIRouter, Depends, HTTPException

from ..core.sync_task_log import get_today_sync_tasks, get_sync_task_detail
from .deps import require_panel_admin

router = APIRouter(tags=["Sync Tasks"])


@router.get("/api/sync-tasks/today", dependencies=[Depends(require_panel_admin)])
async def get_today_sync_tasks_api():
    """获取当天的同步任务列表。"""
    tasks = await get_today_sync_tasks()
    return {"tasks": tasks}


@router.get("/api/sync-tasks/{log_id}", dependencies=[Depends(require_panel_admin)])
async def get_sync_task_detail_api(log_id: str):
    """获取单个同步任务的详情。"""
    task = await get_sync_task_detail(log_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"sync task not found: {log_id}")
    return task
