"""同步任务日志路由"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.sync_task_log import (
    get_today_sync_tasks,
    get_sync_task_detail,
    cancel_sync_task,
    delete_sync_task,
)
from .deps import require_admin

# ObjectId 格式验证
_OBJECTID_RE = re.compile(r"^[0-9a-fA-F]{24}$")


def _validate_log_id(log_id: str) -> None:
    """校验 log_id 是否为合法的 MongoDB ObjectId 格式"""
    if not _OBJECTID_RE.match(log_id):
        raise HTTPException(status_code=400, detail=f"无效的任务 ID 格式: {log_id}")

router = APIRouter(tags=["Sync Tasks"])


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class DeleteSyncTaskBody(BaseModel):
    delete_data: bool = False


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@router.get("/today", dependencies=[Depends(require_admin)])
async def get_today_sync_tasks_api():
    """获取当天的同步任务列表。"""
    tasks = await get_today_sync_tasks()
    return {"tasks": tasks}


@router.get("/{log_id}", dependencies=[Depends(require_admin)])
async def get_sync_task_detail_api(log_id: str):
    """获取单个同步任务的详情。"""
    _validate_log_id(log_id)
    task = await get_sync_task_detail(log_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"sync task not found: {log_id}")
    return task


@router.post("/{log_id}/cancel", dependencies=[Depends(require_admin)])
async def cancel_sync_task_api(log_id: str):
    """取消一个运行中的同步任务。"""
    _validate_log_id(log_id)
    result = await cancel_sync_task(log_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.delete("/{log_id}", dependencies=[Depends(require_admin)])
async def delete_sync_task_api(log_id: str, body: Optional[DeleteSyncTaskBody] = None):
    """
    删除一个同步任务日志。
    如果 body.delete_data=true，同时删除该任务时间窗口内采集的数据。
    """
    _validate_log_id(log_id)
    delete_data = body.delete_data if body else False
    result = await delete_sync_task(log_id, delete_data=delete_data)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result
