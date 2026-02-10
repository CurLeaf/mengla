"""Webhook 回调路由"""
import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request

from ..infra import database
from .deps import require_webhook_signature

router = APIRouter(tags=["Webhook"])

logger = logging.getLogger("mengla-backend")


@router.get("/mengla-notify")
async def mengla_webhook_health():
    """
    Webhook 健康检查端点（GET）：
    - 采集服务可能会先用 GET 请求测试 webhook URL 是否可达
    """
    return {"status": "ok", "message": "webhook endpoint is ready"}


@router.post("/mengla-notify", dependencies=[Depends(require_webhook_signature)])
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

    # 只有任务真正完成（或失败）时才写入 Redis，忽略 running/sync 心跳
    status = (payload.get("status") or "").lower()
    if status in ("running", "sync", "pending", "queued"):
        logger.info(
            "[MengLa] webhook skip (status=%s) executionId=%s",
            status,
            execution_id,
        )
        return {"status": "ok", "skipped": True, "reason": f"status={status}"}

    value = payload.get("resultData") or payload.get("data") or payload
    await client.set(
        f"mengla:exec:{execution_id}",
        json.dumps(value, ensure_ascii=False),
        ex=60 * 30,
    )
    logger.info("[MengLa] redis_set key=mengla:exec:%s status=%s", execution_id, status)
    return {"status": "ok"}
