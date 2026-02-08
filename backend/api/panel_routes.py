"""面板配置与数据补填路由"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from ..core.domain import VALID_ACTIONS, query_mengla
from ..utils.period import period_keys_in_range
from ..utils.dashboard import get_panel_config, update_panel_config
from ..scheduler import PANEL_TASKS
from .deps import require_admin

router = APIRouter(tags=["Panel"])

logger = logging.getLogger("mengla-backend")


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class PanelConfigUpdate(BaseModel):
    """Body for PUT /panel/config."""
    modules: Optional[List[Dict[str, Any]]] = None
    layout: Optional[Dict[str, Any]] = None


class PanelDataFillRequest(BaseModel):
    """Body for POST /panel/data/fill: fill missing MengLa data for a date range."""
    granularity: str  # "day" | "month" | "quarter" | "year"
    startDate: str    # yyyy-MM-dd
    endDate: str      # yyyy-MM-dd
    actions: Optional[List[str]] = None  # default: all five


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
async def fill_mengla_missing(
    granularity: str,
    start_date: str,
    end_date: str,
    actions: Optional[List[str]] = None,
) -> None:
    """
    Fill missing MengLa data for the given granularity and date range.
    For high/hot/chance/industryViewV2: one query_mengla per period_key.
    For industryTrendRange: one call with starRange/endRange for the whole range.
    """
    gran = (granularity or "day").lower().strip()
    if gran not in {"day", "month", "quarter", "year"}:
        logger.warning("fill_mengla_missing: invalid granularity %s", granularity)
        return
    try:
        keys = period_keys_in_range(gran, start_date, end_date)
    except Exception as exc:  # noqa: BLE001
        logger.error("fill_mengla_missing: period_keys_in_range failed: %s", exc)
        return
    if not keys:
        logger.info("fill_mengla_missing: no keys in range %s..%s", start_date, end_date)
        return

    all_actions = ["high", "hot", "chance", "industryViewV2", "industryTrendRange"]
    to_run = [a for a in (actions or all_actions) if a in VALID_ACTIONS]
    if not to_run:
        return

    non_trend = [a for a in to_run if a != "industryTrendRange"]
    for action in non_trend:
        for period_key in keys:
            try:
                await query_mengla(
                    action=action,
                    catId="",
                    dateType=gran,
                    timest=period_key,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "fill_mengla_missing: %s %s failed: %s",
                    action,
                    period_key,
                    exc,
                )
            await asyncio.sleep(1.5)

    if "industryTrendRange" in to_run:
        try:
            await query_mengla(
                action="industryTrendRange",
                catId="",
                dateType=gran,
                starRange=start_date,
                endRange=end_date,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("fill_mengla_missing: industryTrendRange failed: %s", exc)

    logger.info(
        "fill_mengla_missing done: gran=%s range=%s..%s keys=%s actions=%s",
        gran,
        start_date,
        end_date,
        len(keys),
        to_run,
    )


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@router.get("/config")
async def panel_get_config():
    """
    Get current industry panel config (modules + layout).

    Public endpoint — 无需认证。
    设计意图：前端初始化时需要在用户登录前加载面板模块配置以渲染 UI，
    该接口仅返回面板布局和模块列表，不含任何敏感数据。
    """
    return get_panel_config()


@router.put("/config", dependencies=[Depends(require_admin)])
async def panel_put_config(body: PanelConfigUpdate):
    """Update industry panel config (modules and/or layout). Persisted to JSON."""
    updated = update_panel_config(modules=body.modules, layout=body.layout)
    return updated


@router.post("/tasks/{task_id}/run", dependencies=[Depends(require_admin)])
async def panel_run_task(task_id: str):
    """Trigger a panel task by id. Runs in background."""
    from ..utils.tasks import _track_task
    if task_id not in PANEL_TASKS:
        raise HTTPException(status_code=404, detail=f"unknown task_id: {task_id}")
    run_fn = PANEL_TASKS[task_id]["run"]
    _track_task(run_fn())
    return {"message": "task started", "task_id": task_id}


@router.post("/data/fill", dependencies=[Depends(require_admin)])
async def panel_data_fill(body: PanelDataFillRequest, tasks: BackgroundTasks):
    """Submit background task to fill missing MengLa data for the given range."""
    gran = (body.granularity or "").lower().strip()
    if gran not in {"day", "month", "quarter", "year"}:
        raise HTTPException(status_code=400, detail="invalid granularity")
    try:
        keys = period_keys_in_range(gran, body.startDate, body.endDate)
    except Exception as exc:  # noqa: BLE001
        logger.error("panel_data_fill: invalid date range: %s", exc)
        raise HTTPException(status_code=400, detail="invalid date range") from exc
    if not keys:
        return {
            "message": "no period keys in range",
            "granularity": gran,
            "startDate": body.startDate,
            "endDate": body.endDate,
        }
    tasks.add_task(
        fill_mengla_missing,
        gran,
        body.startDate,
        body.endDate,
        body.actions,
    )
    return {
        "message": "fill started",
        "granularity": gran,
        "startDate": body.startDate,
        "endDate": body.endDate,
        "periodKeyCount": len(keys),
    }
