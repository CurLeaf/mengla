import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import json
import logging
import traceback

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import os

# 确保应用与 MengLa 调试日志在控制台可见（uvicorn 默认不配置根 logger）
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)
for _name in ("mengla-backend", "mengla-domain", "backend.mengla_client"):
    logging.getLogger(_name).setLevel(logging.INFO)

from .infra import database
from .infra.database import init_db_events
from .scheduler import init_scheduler, PANEL_TASKS
from .tools.backfill import backfill_data
from .core.domain import ACTION_CONFIG, query_mengla_domain
from .utils.period import period_keys_in_range
from .utils.dashboard import get_panel_config, update_panel_config
from .core.queue import create_crawl_job
from .utils.category import (
    get_all_categories,
    get_all_valid_cat_ids,
    get_secondary_categories,
)
# 新增模块
from .infra.cache import get_cache_manager, warmup_cache
from .infra.metrics import get_metrics_collector, get_current_metrics
from .infra.alerting import get_alert_manager, run_alert_check, init_default_notifiers
from .infra.resilience import get_circuit_manager
from .infra.logger import setup_logging


def _panel_admin_enabled() -> bool:
    v = os.getenv("ENABLE_PANEL_ADMIN", "").strip().lower()
    if v:
        return v in ("1", "true", "yes")
    # 非 production 环境下默认开启管理中心，便于本地开发
    env = os.getenv("ENV", "").strip().lower()
    return env != "production"


async def require_panel_admin() -> None:
    """Dependency: raise 403 if panel admin APIs are disabled (non-dev)."""
    if not _panel_admin_enabled():
        raise HTTPException(
            status_code=403,
            detail="Panel admin is disabled. Set ENABLE_PANEL_ADMIN=1 to enable.",
        )


app = FastAPI(title="Industry Monitor API", version="0.1.0")

logger = logging.getLogger("mengla-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db_events(app)

scheduler = init_scheduler()


@app.on_event("startup")
async def _start_scheduler() -> None:
    scheduler.start()


@app.on_event("startup")
async def _init_indexes() -> None:
    # 索引已在 database.init_db_events 的 startup 中创建
    pass


@app.on_event("startup")
async def _init_alerting() -> None:
    """初始化告警系统"""
    init_default_notifiers()


@app.on_event("shutdown")
async def _shutdown_scheduler() -> None:
    scheduler.shutdown(wait=False)


class BackfillRequest(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    interfaces: Optional[List[str]] = None


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


class MengLaStatusRequest(BaseModel):
    """管理中心用：检查指定类目 + 时间范围 + 颗粒度下，各接口是否有数据。"""

    catId: Optional[str] = None
    granularity: str  # "day" | "month" | "quarter" | "year"
    startDate: str    # yyyy-MM-dd
    endDate: str      # yyyy-MM-dd
    actions: Optional[List[str]] = None


class PanelModuleUpdate(BaseModel):
    """Single module in panel config (for PUT /panel/config)."""
    id: str
    name: Optional[str] = None
    enabled: Optional[bool] = None
    order: Optional[int] = None
    props: Optional[Dict[str, Any]] = None


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


class EnqueueFullCrawlRequest(BaseModel):
    """Body for POST /admin/mengla/enqueue-full-crawl: create a queue-based full crawl job."""
    startDate: str    # yyyy-MM-dd
    endDate: str      # yyyy-MM-dd
    granularities: Optional[List[str]] = None  # default: day, month, quarter, year
    actions: Optional[List[str]] = None  # default: all five MengLa actions
    catId: Optional[str] = None


async def _mengla_query_by_action(action: str, body: MengLaQueryParamsBody) -> JSONResponse:
    """
    内部：按 action 执行萌拉查询，校验 catId，调用 query_mengla_domain，统一异常处理。
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
    try:
        result = await query_mengla_domain(
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


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/categories")
async def get_categories():
    """
    返回类目树，数据来源于 backend/category.json。
    为避免频繁读大文件，使用简单内存缓存。
    """
    return get_all_categories()


@app.get("/api/industry/daily")
async def get_industry_daily(date: str):
    """
    示例查询接口：按天返回某个 period_key 的所有行业数据。
    查询顺序：1) MongoDB  2) Redis，命中即返回。
    """
    if database.mongo_db is None:
        raise HTTPException(status_code=500, detail="MongoDB not initialized")

    collection = database.mongo_db["industry_reports"]
    cursor = collection.find({"granularity": "day", "period_key": date})
    docs = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        docs.append(doc)

    if docs:
        if database.redis_client is not None:
            import json
            await database.redis_client.set(
                f"industry:day:{date}", json.dumps(docs), ex=60 * 60 * 24
            )
        return docs

    redis_key = f"industry:day:{date}"
    if database.redis_client is not None:
        cached = await database.redis_client.get(redis_key)
        if cached:
            import json
            return json.loads(cached)

    return docs


@app.post("/admin/mengla/status")
async def get_mengla_status(body: MengLaStatusRequest):
    """
    管理接口：查询指定 catId（可选）+ 时间范围 + 颗粒度 下，
    五个 MengLa 接口在 MongoDB 中各 period_key 是否有数据。
    仅查询 Mongo，不触发采集或写库。
    """
    gran = (body.granularity or "").lower().strip()
    if gran not in {"day", "month", "quarter", "year"}:
        raise HTTPException(status_code=400, detail="invalid granularity")

    # 生成该颗粒度下的所有 period_key 列表
    try:
        keys = period_keys_in_range(gran, body.startDate, body.endDate)
    except Exception as exc:  # noqa: BLE001
        logger.error("failed to generate period keys: %s", exc)
        raise HTTPException(status_code=400, detail="invalid date range") from exc

    if not keys:
        return {
            "catId": body.catId,
            "granularity": gran,
            "startDate": body.startDate,
            "endDate": body.endDate,
            "status": {},
        }

    all_actions = ["high", "hot", "chance", "industryViewV2", "industryTrendRange"]
    actions = body.actions or all_actions
    # 过滤掉未知 action
    unknown = [a for a in actions if a not in ACTION_CONFIG]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown actions: {unknown}")

    if database.mongo_db is None:
        raise HTTPException(status_code=500, detail="MongoDB not initialized")

    status: Dict[str, Dict[str, bool]] = {}

    for action in actions:
        coll_name = ACTION_CONFIG[action]["collection"]
        coll = database.mongo_db[coll_name]

        base_filter: Dict[str, Any] = {
            "granularity": gran,
            "period_key": {"$in": keys},
        }
        # 如需精确到 catId，可根据实际数据结构在 data 内增加过滤：
        # if body.catId:
        #     base_filter["data.catId"] = body.catId

        cursor = coll.find(base_filter, {"period_key": 1})
        docs = await cursor.to_list(length=len(keys) * 2)
        present = {str(d.get("period_key")) for d in docs}

        status[action] = {k: (k in present) for k in keys}

    return {
        "catId": body.catId,
        "granularity": gran,
        "startDate": body.startDate,
        "endDate": body.endDate,
        "status": status,
    }


async def fill_mengla_missing(
    granularity: str,
    start_date: str,
    end_date: str,
    actions: Optional[List[str]] = None,
) -> None:
    """
    Fill missing MengLa data for the given granularity and date range.
    For high/hot/chance/industryViewV2: one query_mengla_domain per period_key.
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
    to_run = [a for a in (actions or all_actions) if a in ACTION_CONFIG]
    if not to_run:
        return

    non_trend = [a for a in to_run if a != "industryTrendRange"]
    for action in non_trend:
        for period_key in keys:
            try:
                await query_mengla_domain(
                    action=action,
                    product_id="",
                    catId="",
                    dateType=gran,
                    timest=period_key,
                    starRange="",
                    endRange="",
                    extra={},
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
            await query_mengla_domain(
                action="industryTrendRange",
                product_id="",
                catId="",
                dateType=gran,
                timest="",
                starRange=start_date,
                endRange=end_date,
                extra={},
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


@app.post("/panel/data/fill", dependencies=[Depends(require_panel_admin)])
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


@app.post("/admin/mengla/enqueue-full-crawl", dependencies=[Depends(require_panel_admin)])
async def enqueue_full_crawl(body: EnqueueFullCrawlRequest):
    """
    Create a queue-based full crawl job (crawl_jobs + crawl_subtasks).
    Worker (run_crawl_queue_once) will consume pending subtasks periodically.
    """
    try:
        start = datetime.strptime(body.startDate, "%Y-%m-%d")
        end = datetime.strptime(body.endDate, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
    if start > end:
        raise HTTPException(status_code=400, detail="startDate must be <= endDate")

    cat_id = (body.catId or "").strip()
    if cat_id:
        valid_cat_ids = get_all_valid_cat_ids()
        if cat_id not in valid_cat_ids:
            raise HTTPException(
                status_code=400,
                detail=f"catId must be from backend/category.json: {cat_id} not in list",
            )

    if database.mongo_db is None:
        raise HTTPException(status_code=503, detail="MongoDB not initialized")

    job_id = await create_crawl_job(
        start_date=body.startDate,
        end_date=body.endDate,
        granularities=body.granularities,
        actions=body.actions,
        cat_id=body.catId,
    )
    if job_id is None:
        raise HTTPException(status_code=503, detail="Failed to create crawl job")

    return {
        "message": "crawl job enqueued",
        "jobId": str(job_id),
        "startDate": body.startDate,
        "endDate": body.endDate,
    }


@app.get("/panel/config")
async def panel_get_config():
    """Get current industry panel config (modules + layout). Public so dashboard can read; write/tasks are protected."""
    return get_panel_config()


@app.put("/panel/config", dependencies=[Depends(require_panel_admin)])
async def panel_put_config(body: PanelConfigUpdate):
    """Update industry panel config (modules and/or layout). Persisted to JSON."""
    updated = update_panel_config(modules=body.modules, layout=body.layout)
    return updated


@app.get("/panel/tasks", dependencies=[Depends(require_panel_admin)])
async def panel_list_tasks():
    """List industry panel related tasks (for admin center)."""
    return [
        {"id": task_id, "name": info["name"], "description": info.get("description", "")}
        for task_id, info in PANEL_TASKS.items()
    ]


@app.post("/panel/tasks/{task_id}/run", dependencies=[Depends(require_panel_admin)])
async def panel_run_task(task_id: str, tasks: BackgroundTasks):
    """Trigger a panel task by id. Runs in background."""
    if task_id not in PANEL_TASKS:
        raise HTTPException(status_code=404, detail=f"unknown task_id: {task_id}")
    run_fn = PANEL_TASKS[task_id]["run"]
    tasks.add_task(run_fn)
    return {"message": "task started", "task_id": task_id}


@app.get("/api/webhook/mengla-notify")
async def mengla_webhook_health():
    """
    Webhook 健康检查端点（GET）：
    - 采集服务可能会先用 GET 请求测试 webhook URL 是否可达
    """
    return {"status": "ok", "message": "webhook endpoint is ready"}


@app.post("/api/webhook/mengla-notify")
async def mengla_webhook(request: Request):
    """
    萌拉托管任务的 webhook 回调入口（POST）：
    - 期望 body 中至少包含 executionId 和 result 字段，结构可按实际平台调整
    - 将结果写入 Redis，以 executionId 为 key，供 MengLaService 轮询
    - 若 Redis 未在 startup 连接（如外部回调先于或未走 startup），则在此懒加载连接
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


@app.post("/api/mengla/query")
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
    try:
        result = await query_mengla_domain(
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


@app.post("/api/mengla/high")
async def mengla_high(body: MengLaQueryParamsBody):
    """
    蓝海 Top 行业。参数：dateType、timest、catId（可选）、starRange/endRange。
    """
    return await _mengla_query_by_action("high", body)


@app.post("/api/mengla/hot")
async def mengla_hot(body: MengLaQueryParamsBody):
    """
    热销 Top 行业。参数：dateType、timest、catId（可选）、starRange/endRange。
    """
    return await _mengla_query_by_action("hot", body)


@app.post("/api/mengla/chance")
async def mengla_chance(body: MengLaQueryParamsBody):
    """
    潜力 Top 行业。参数：dateType、timest、catId（可选）、starRange/endRange。
    """
    return await _mengla_query_by_action("chance", body)


@app.post("/api/mengla/industry-view")
async def mengla_industry_view(body: MengLaQueryParamsBody):
    """
    行业区间/总览（industryViewV2）。参数：dateType、timest、starRange、endRange、catId（可选）。
    """
    return await _mengla_query_by_action("industryViewV2", body)


@app.post("/api/mengla/industry-trend")
async def mengla_industry_trend(body: MengLaQueryParamsBody):
    """
    行业趋势（industryTrendRange）。参数：dateType、starRange、endRange、catId（可选），timest 可选。
    """
    return await _mengla_query_by_action("industryTrendRange", body)


@app.post("/admin/backfill")
async def trigger_backfill(payload: BackfillRequest, tasks: BackgroundTasks):
    """
    历史补录接口：前端调用后立即返回，补录任务在后台运行。
    """
    try:
        start = datetime.strptime(payload.start_date, "%Y-%m-%d")
        end = datetime.strptime(payload.end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")

    if start > end:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    # 使用默认参数调用 backfill_data
    actions = payload.interfaces or ["high", "hot", "chance", "industryViewV2", "industryTrendRange"]
    granularities = ["day", "month", "quarter", "year"]
    cat_ids = [""]  # 默认为空字符串，表示所有类目
    
    tasks.add_task(
        backfill_data,
        payload.start_date,
        payload.end_date,
        actions,
        granularities,
        cat_ids
    )

    return {"message": "backfill started", "start_date": payload.start_date, "end_date": payload.end_date}


@app.get("/")
async def root():
    return {"message": "Industry Monitor API running"}


@app.post("/api/mengla/query-mock")
async def mengla_query_mock(body: MengLaQueryBody):
    """
    临时 Mock 接口：用于在采集服务不可达时测试前端
    使用方法：前端临时修改 API 地址为 /api/mengla/query-mock
    """
    from .mock_data_helper import (
        get_mock_high_data,
        get_mock_industry_view_data,
        get_mock_industry_trend_data,
    )
    
    action = body.action
    if action == "high":
        return get_mock_high_data()
    elif action == "hot":
        return get_mock_high_data()  # 复用蓝海数据
    elif action == "chance":
        return get_mock_high_data()  # 复用蓝海数据
    elif action == "industryViewV2":
        return get_mock_industry_view_data()
    elif action == "industryTrendRange":
        return get_mock_industry_trend_data()
    else:
        return {"error": f"Unknown action: {action}"}


# ==============================================================================
# 监控与运维 API
# ==============================================================================
@app.get("/admin/metrics", dependencies=[Depends(require_panel_admin)])
async def get_metrics():
    """获取采集指标统计"""
    return await get_current_metrics()


@app.get("/admin/metrics/latency", dependencies=[Depends(require_panel_admin)])
async def get_latency_stats():
    """获取延迟百分位统计"""
    collector = get_metrics_collector()
    return await collector.get_latency_percentiles()


@app.get("/admin/alerts", dependencies=[Depends(require_panel_admin)])
async def get_alerts():
    """获取当前活跃告警"""
    manager = get_alert_manager()
    return {
        "active": await manager.get_active_alerts(),
        "rules": await manager.get_rule_status(),
    }


@app.get("/admin/alerts/history", dependencies=[Depends(require_panel_admin)])
async def get_alert_history(limit: int = 100):
    """获取告警历史"""
    manager = get_alert_manager()
    return await manager.get_alert_history(limit)


@app.post("/admin/alerts/check", dependencies=[Depends(require_panel_admin)])
async def check_alerts():
    """手动触发告警检查"""
    return await run_alert_check()


class SilenceRuleRequest(BaseModel):
    rule_name: str
    duration_minutes: int = 60


@app.post("/admin/alerts/silence", dependencies=[Depends(require_panel_admin)])
async def silence_alert_rule(body: SilenceRuleRequest):
    """静默某个告警规则"""
    manager = get_alert_manager()
    success = await manager.silence_rule(body.rule_name, body.duration_minutes)
    if not success:
        raise HTTPException(status_code=404, detail=f"Rule not found: {body.rule_name}")
    return {"message": f"Rule {body.rule_name} silenced for {body.duration_minutes} minutes"}


@app.get("/admin/cache/stats", dependencies=[Depends(require_panel_admin)])
async def get_cache_stats():
    """获取缓存统计"""
    cache_manager = get_cache_manager()
    return cache_manager.get_stats()


class CacheWarmupRequest(BaseModel):
    actions: Optional[List[str]] = None
    cat_ids: Optional[List[str]] = None
    granularities: Optional[List[str]] = None
    limit: int = 100


@app.post("/admin/cache/warmup", dependencies=[Depends(require_panel_admin)])
async def trigger_cache_warmup(body: CacheWarmupRequest, tasks: BackgroundTasks):
    """触发缓存预热"""
    tasks.add_task(
        warmup_cache,
        body.actions,
        body.cat_ids,
        body.granularities,
        body.limit,
    )
    return {"message": "Cache warmup started", "limit": body.limit}


@app.post("/admin/cache/clear-l1", dependencies=[Depends(require_panel_admin)])
async def clear_l1_cache():
    """清空 L1 本地缓存"""
    cache_manager = get_cache_manager()
    await cache_manager.clear_l1()
    return {"message": "L1 cache cleared"}


@app.get("/admin/circuit-breakers", dependencies=[Depends(require_panel_admin)])
async def get_circuit_breakers():
    """获取熔断器状态"""
    manager = get_circuit_manager()
    return manager.get_all_stats()


@app.post("/admin/circuit-breakers/reset", dependencies=[Depends(require_panel_admin)])
async def reset_circuit_breakers():
    """重置所有熔断器"""
    manager = get_circuit_manager()
    await manager.reset_all()
    return {"message": "All circuit breakers reset"}


@app.get("/admin/system/status", dependencies=[Depends(require_panel_admin)])
async def get_system_status():
    """获取系统综合状态"""
    metrics = await get_current_metrics()
    cache_manager = get_cache_manager()
    alert_manager = get_alert_manager()
    circuit_manager = get_circuit_manager()
    
    return {
        "metrics": metrics,
        "cache": cache_manager.get_stats(),
        "alerts": {
            "active_count": len(await alert_manager.get_active_alerts()),
            "rules": await alert_manager.get_rule_status(),
        },
        "circuit_breakers": circuit_manager.get_all_stats(),
        "scheduler": {
            "running": scheduler.running,
            "jobs": [
                {"id": job.id, "name": job.name, "next_run": str(job.next_run_time)}
                for job in scheduler.get_jobs()
            ],
        },
    }

