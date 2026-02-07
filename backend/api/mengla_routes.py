"""萌拉数据查询与 Webhook 路由"""
import json
import logging
import os
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core.auth import require_auth
from ..core.domain import VALID_ACTIONS, query_mengla
from ..infra import database
from ..utils.category import get_all_valid_cat_ids, get_secondary_categories

router = APIRouter(tags=["MengLa Data"])

logger = logging.getLogger("mengla-backend")


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class MengLaQueryBody(BaseModel):
    action: str
    product_id: Optional[str] = ""
    catId: Optional[str] = ""
    dateType: Optional[str] = ""
    timest: Optional[str] = ""
    starRange: Optional[str] = ""
    endRange: Optional[str] = ""
    extra: Optional[dict] = None


class MengLaQueryParamsBody(BaseModel):
    """五个独立 API 共用：不包含 action，由路由确定。"""
    product_id: Optional[str] = ""
    catId: Optional[str] = ""
    dateType: Optional[str] = ""
    timest: Optional[str] = ""
    starRange: Optional[str] = ""
    endRange: Optional[str] = ""
    extra: Optional[dict] = None


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _validate_date_type(date_type: str) -> None:
    """校验 dateType 参数是否有效"""
    if date_type:
        valid = {"day", "month", "quarter", "year"}
        if date_type.lower() not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"无效的 dateType: {date_type}，必须是 day/month/quarter/year 之一",
            )


async def _mengla_query_by_action(action: str, body: MengLaQueryParamsBody) -> JSONResponse:
    """
    内部：按 action 执行萌拉查询，校验 catId，调用 query_mengla，统一异常处理。
    返回 JSONResponse（含 X-MengLa-Source 头）。
    """
    t0 = time.time()
    logger.info(
        "[MengLa] request action=%s catId=%s dateType=%s timest=%s starRange=%s endRange=%s at=%s",
        action,
        body.catId or "",
        body.dateType or "",
        body.timest or "",
        body.starRange or "",
        body.endRange or "",
        datetime.utcnow().isoformat() + "Z",
    )
    cat_id = (body.catId or "").strip()
    if cat_id:
        valid_cat_ids = get_all_valid_cat_ids()
        if cat_id not in valid_cat_ids:
            raise HTTPException(
                status_code=400,
                detail=f"catId 必须在 backend/category.json 中：当前 catId={cat_id} 不在类目列表中",
            )
    _validate_date_type(body.dateType or "")
    try:
        result = await query_mengla(
            action=action,
            product_id=body.product_id or "",
            catId=body.catId or "",
            dateType=body.dateType or "",
            timest=body.timest or "",
            starRange=body.starRange or "",
            endRange=body.endRange or "",
            extra=body.extra or {},
        )
        data, source = result[0], result[1]
        extra = result[2] if len(result) > 2 else None
        if (body.catId or "").strip():
            secondary = get_secondary_categories((body.catId or "").strip())
            if isinstance(data, dict):
                data = {**data, "secondaryCategories": secondary}
        elapsed = time.time() - t0
        try:
            size = len(json.dumps(data, ensure_ascii=False))
        except (TypeError, ValueError):
            size = -1
        logger.info(
            "[MengLa] response action=%s source=%s size=%s elapsed_sec=%.2f",
            action,
            source,
            size,
            elapsed,
        )
        headers = {"X-MengLa-Source": source, "Access-Control-Expose-Headers": "X-MengLa-Source"}
        if extra and extra.get("partial") and action == "industryTrendRange":
            headers["X-MengLa-Trend-Partial"] = f"{extra.get('requested', 0)},{extra.get('found', 0)}"
            headers["Access-Control-Expose-Headers"] = "X-MengLa-Source, X-MengLa-Trend-Partial"
        return JSONResponse(content=data, headers=headers)
    except TimeoutError as exc:
        logger.error(
            "MengLa query timeout type=%s message=%s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=504, detail="mengla query timeout")
    except httpx.ConnectError as exc:
        logger.warning(
            "MengLa 采集服务不可达 type=%s message=%s",
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail="采集服务不可达，请检查 COLLECT_SERVICE_URL 与网络（如 VPN、防火墙）",
        )
    except httpx.TimeoutException as exc:
        logger.warning(
            "MengLa 采集服务请求超时 type=%s message=%s",
            type(exc).__name__,
            exc,
        )
        raise HTTPException(status_code=504, detail="采集服务请求超时")
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "MengLa query failed type=%s message=%s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@router.post("/api/mengla/query", dependencies=[Depends(require_auth)])
async def mengla_query(body: MengLaQueryBody):
    """
    统一的萌拉查询接口（蓝海 / 行业区间 / 行业趋势）：
    - 前端只需要传 action 和业务参数
    - catId 必须为 backend/category.json 中存在的类目 ID
    - 后端统一做频控、调用托管任务、轮询 Redis、缓存结果，并落库 Mongo
    """
    t0 = time.time()
    logger.info(
        "[MengLa] request action=%s catId=%s dateType=%s timest=%s starRange=%s endRange=%s at=%s",
        body.action,
        body.catId or "",
        body.dateType or "",
        body.timest or "",
        body.starRange or "",
        body.endRange or "",
        datetime.utcnow().isoformat() + "Z",
    )
    cat_id = (body.catId or "").strip()
    if cat_id:
        valid_cat_ids = get_all_valid_cat_ids()
        if cat_id not in valid_cat_ids:
            raise HTTPException(
                status_code=400,
                detail=f"catId 必须在 backend/category.json 中：当前 catId={cat_id} 不在类目列表中",
            )
    _validate_date_type(body.dateType or "")
    try:
        result = await query_mengla(
            action=body.action,
            product_id=body.product_id or "",
            catId=body.catId or "",
            dateType=body.dateType or "",
            timest=body.timest or "",
            starRange=body.starRange or "",
            endRange=body.endRange or "",
            extra=body.extra or {},
        )
        data, source = result[0], result[1]
        extra = result[2] if len(result) > 2 else None
        if (body.catId or "").strip():
            secondary = get_secondary_categories((body.catId or "").strip())
            if isinstance(data, dict):
                data = {**data, "secondaryCategories": secondary}
        elapsed = time.time() - t0
        try:
            size = len(json.dumps(data, ensure_ascii=False))
        except (TypeError, ValueError):
            size = -1
        logger.info(
            "[MengLa] response action=%s source=%s size=%s elapsed_sec=%.2f",
            body.action,
            source,
            size,
            elapsed,
        )
        headers = {"X-MengLa-Source": source, "Access-Control-Expose-Headers": "X-MengLa-Source"}
        if extra and extra.get("partial") and body.action == "industryTrendRange":
            headers["X-MengLa-Trend-Partial"] = f"{extra.get('requested', 0)},{extra.get('found', 0)}"
            headers["Access-Control-Expose-Headers"] = "X-MengLa-Source, X-MengLa-Trend-Partial"
        return JSONResponse(content=data, headers=headers)
    except TimeoutError as exc:
        logger.error(
            "MengLa query timeout type=%s message=%s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=504, detail="mengla query timeout")
    except httpx.ConnectError as exc:
        logger.warning(
            "MengLa 采集服务不可达 type=%s message=%s",
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail="采集服务不可达，请检查 COLLECT_SERVICE_URL 与网络（如 VPN、防火墙）",
        )
    except httpx.TimeoutException as exc:
        logger.warning(
            "MengLa 采集服务请求超时 type=%s message=%s",
            type(exc).__name__,
            exc,
        )
        raise HTTPException(status_code=504, detail="采集服务请求超时")
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "MengLa query failed type=%s message=%s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/api/mengla/high", dependencies=[Depends(require_auth)])
async def mengla_high(body: MengLaQueryParamsBody):
    """蓝海 Top 行业。"""
    return await _mengla_query_by_action("high", body)


@router.post("/api/mengla/hot", dependencies=[Depends(require_auth)])
async def mengla_hot(body: MengLaQueryParamsBody):
    """热销 Top 行业。"""
    return await _mengla_query_by_action("hot", body)


@router.post("/api/mengla/chance", dependencies=[Depends(require_auth)])
async def mengla_chance(body: MengLaQueryParamsBody):
    """潜力 Top 行业。"""
    return await _mengla_query_by_action("chance", body)


@router.post("/api/mengla/industry-view", dependencies=[Depends(require_auth)])
async def mengla_industry_view(body: MengLaQueryParamsBody):
    """行业区间/总览（industryViewV2）。"""
    return await _mengla_query_by_action("industryViewV2", body)


@router.post("/api/mengla/industry-trend", dependencies=[Depends(require_auth)])
async def mengla_industry_trend(body: MengLaQueryParamsBody):
    """行业趋势（industryTrendRange）。"""
    return await _mengla_query_by_action("industryTrendRange", body)


# ---------------------------------------------------------------------------
# Webhook 路由
# ---------------------------------------------------------------------------
@router.get("/api/webhook/mengla-notify")
async def mengla_webhook_health():
    """
    Webhook 健康检查端点（GET）：
    - 采集服务可能会先用 GET 请求测试 webhook URL 是否可达
    """
    return {"status": "ok", "message": "webhook endpoint is ready"}


@router.post("/api/webhook/mengla-notify")
async def mengla_webhook(request: Request):
    """
    萌拉托管任务的 webhook 回调入口（POST）：
    - 期望 body 中至少包含 executionId 和 result 字段
    - 将结果写入 Redis，以 executionId 为 key，供 MengLaService 轮询
    """
    if database.redis_client is None:
        redis_uri = os.getenv("REDIS_URI", database.REDIS_URI_DEFAULT)
        await database.connect_to_redis(redis_uri)
    client = database.redis_client
    if client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")

    payload = await request.json()
    execution_id = (
        payload.get("executionId")
        or payload.get("data", {}).get("executionId")
        or payload.get("execution_id")
    )
    logger.info(
        "[MengLa] webhook received executionId=%s keys=%s",
        execution_id,
        list(payload.keys()) if isinstance(payload, dict) else "?",
    )
    if not execution_id:
        raise HTTPException(status_code=400, detail="missing executionId in payload")

    value = payload.get("resultData") or payload
    await client.set(
        f"mengla:exec:{execution_id}",
        json.dumps(value, ensure_ascii=False),
        ex=60 * 30,
    )
    res = {"status": "ok"}
    logger.info("[MengLa] redis_set key=mengla:exec:%s", execution_id)
    return res
