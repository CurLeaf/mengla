"""管理与运维路由：监控指标、告警、缓存、熔断器、调度器控制、数据清空、采集健康"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core.domain import VALID_ACTIONS
from ..core.queue import create_crawl_job
from ..infra import database
from ..infra.cache import get_cache_manager, warmup_cache
from ..infra.metrics import get_metrics_collector, get_current_metrics
from ..infra.alerting import get_alert_manager, run_alert_check
from ..infra.resilience import get_circuit_manager
from ..utils.category import get_all_valid_cat_ids, get_top_level_cat_ids
from ..utils.period import period_keys_in_range, make_period_keys
from ..utils.config import COLLECTION_NAME, REDIS_KEY_PREFIX
from ..tools.backfill import backfill_data
from .deps import require_admin

router = APIRouter(tags=["Admin"])

logger = logging.getLogger("mengla-backend")


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class MengLaStatusRequest(BaseModel):
    """管理中心用：检查指定类目 + 时间范围 + 颗粒度下，各接口是否有数据。"""
    catId: Optional[str] = None
    granularity: str  # "day" | "month" | "quarter" | "year"
    startDate: str    # yyyy-MM-dd
    endDate: str      # yyyy-MM-dd
    actions: Optional[List[str]] = None


class EnqueueFullCrawlRequest(BaseModel):
    """Body for POST /admin/mengla/enqueue-full-crawl."""
    startDate: str    # yyyy-MM-dd
    endDate: str      # yyyy-MM-dd
    granularities: Optional[List[str]] = None
    actions: Optional[List[str]] = None
    catId: Optional[str] = None


class BackfillRequest(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    interfaces: Optional[List[str]] = None


class SilenceRuleRequest(BaseModel):
    rule_name: str
    duration_minutes: int = 60


class CacheWarmupRequest(BaseModel):
    actions: Optional[List[str]] = None
    cat_ids: Optional[List[str]] = None
    granularities: Optional[List[str]] = None
    limit: int = 100


class PurgeRequest(BaseModel):
    confirm: bool = False
    targets: List[str] = ["mongodb", "redis", "l1"]


# ---------------------------------------------------------------------------
# 萌拉数据状态查询
# ---------------------------------------------------------------------------
@router.post("/mengla/status", dependencies=[Depends(require_admin)])
async def get_mengla_status(body: MengLaStatusRequest):
    """
    管理接口：查询指定 catId（可选）+ 时间范围 + 颗粒度 下，
    五个 MengLa 接口在 MongoDB 中各 period_key 是否有数据。
    """
    gran = (body.granularity or "").lower().strip()
    if gran not in {"day", "month", "quarter", "year"}:
        raise HTTPException(status_code=400, detail="invalid granularity")

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
    unknown = [a for a in actions if a not in VALID_ACTIONS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown actions: {unknown}")

    if database.mongo_db is None:
        raise HTTPException(status_code=500, detail="MongoDB not initialized")

    coll = database.mongo_db[COLLECTION_NAME]
    status: Dict[str, Dict[str, bool]] = {}

    for action in actions:
        base_filter: Dict[str, Any] = {
            "action": action,
            "granularity": gran,
            "period_key": {"$in": keys},
        }
        if body.catId:
            base_filter["cat_id"] = body.catId

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


# ---------------------------------------------------------------------------
# 全量爬取任务
# ---------------------------------------------------------------------------
@router.post("/mengla/enqueue-full-crawl", dependencies=[Depends(require_admin)])
async def enqueue_full_crawl(body: EnqueueFullCrawlRequest):
    """Create a queue-based full crawl job."""
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
                detail=f"catId 必须在 backend/category.json 中：当前 catId={cat_id} 不在类目列表中",
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


# ---------------------------------------------------------------------------
# 历史补录
# ---------------------------------------------------------------------------
@router.post("/backfill", dependencies=[Depends(require_admin)])
async def trigger_backfill(payload: BackfillRequest, tasks: BackgroundTasks):
    """历史补录接口：前端调用后立即返回，补录任务在后台运行。"""
    try:
        start = datetime.strptime(payload.start_date, "%Y-%m-%d")
        end = datetime.strptime(payload.end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
    if start > end:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    actions = payload.interfaces or ["high", "hot", "chance", "industryViewV2", "industryTrendRange"]
    granularities = ["day", "month", "quarter", "year"]
    cat_ids = [""]

    tasks.add_task(
        backfill_data,
        payload.start_date,
        payload.end_date,
        actions,
        granularities,
        cat_ids,
    )
    return {"message": "backfill started", "start_date": payload.start_date, "end_date": payload.end_date}


# ---------------------------------------------------------------------------
# 监控指标
# ---------------------------------------------------------------------------
@router.get("/metrics", dependencies=[Depends(require_admin)])
async def get_metrics():
    """获取采集指标统计"""
    return await get_current_metrics()


@router.get("/metrics/latency", dependencies=[Depends(require_admin)])
async def get_latency_stats():
    """获取延迟百分位统计"""
    collector = get_metrics_collector()
    return await collector.get_latency_percentiles()


# ---------------------------------------------------------------------------
# 告警
# ---------------------------------------------------------------------------
@router.get("/alerts", dependencies=[Depends(require_admin)])
async def get_alerts():
    """获取当前活跃告警"""
    manager = get_alert_manager()
    return {
        "active": await manager.get_active_alerts(),
        "rules": await manager.get_rule_status(),
    }


@router.get("/alerts/history", dependencies=[Depends(require_admin)])
async def get_alert_history(limit: int = 100):
    """获取告警历史"""
    manager = get_alert_manager()
    return await manager.get_alert_history(limit)


@router.post("/alerts/check", dependencies=[Depends(require_admin)])
async def check_alerts():
    """手动触发告警检查"""
    return await run_alert_check()


@router.post("/alerts/silence", dependencies=[Depends(require_admin)])
async def silence_alert_rule(body: SilenceRuleRequest):
    """静默某个告警规则"""
    manager = get_alert_manager()
    success = await manager.silence_rule(body.rule_name, body.duration_minutes)
    if not success:
        raise HTTPException(status_code=404, detail=f"Rule not found: {body.rule_name}")
    return {"message": f"Rule {body.rule_name} silenced for {body.duration_minutes} minutes"}


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------
@router.get("/cache/stats", dependencies=[Depends(require_admin)])
async def get_cache_stats():
    """获取缓存统计"""
    cache_manager = get_cache_manager()
    return cache_manager.get_stats()


@router.post("/cache/warmup", dependencies=[Depends(require_admin)])
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


@router.post("/cache/clear-l1", dependencies=[Depends(require_admin)])
async def clear_l1_cache():
    """清空 L1 本地缓存"""
    cache_manager = get_cache_manager()
    await cache_manager.clear_l1()
    return {"message": "L1 cache cleared"}


# ---------------------------------------------------------------------------
# 熔断器
# ---------------------------------------------------------------------------
@router.get("/circuit-breakers", dependencies=[Depends(require_admin)])
async def get_circuit_breakers():
    """获取熔断器状态"""
    manager = get_circuit_manager()
    return manager.get_all_stats()


@router.post("/circuit-breakers/reset", dependencies=[Depends(require_admin)])
async def reset_circuit_breakers():
    """重置所有熔断器"""
    manager = get_circuit_manager()
    await manager.reset_all()
    return {"message": "All circuit breakers reset"}


# ---------------------------------------------------------------------------
# 系统状态
# ---------------------------------------------------------------------------
@router.get("/system/status", dependencies=[Depends(require_admin)])
async def get_system_status():
    """获取系统综合状态"""
    from ..main import scheduler as _scheduler
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
            "running": _scheduler.running,
            "jobs": [
                {"id": job.id, "name": job.name, "next_run": str(job.next_run_time)}
                for job in _scheduler.get_jobs()
            ],
        },
    }


# ---------------------------------------------------------------------------
# 调度器控制
# ---------------------------------------------------------------------------
@router.get("/scheduler/status", dependencies=[Depends(require_admin)])
async def scheduler_status():
    """获取调度器运行状态"""
    from ..main import scheduler as _scheduler
    from ..utils.tasks import _background_tasks
    from apscheduler.schedulers.base import STATE_PAUSED, STATE_RUNNING, STATE_STOPPED
    state_map = {STATE_STOPPED: "stopped", STATE_RUNNING: "running", STATE_PAUSED: "paused"}
    paused_jobs = []
    active_jobs = []
    for job in _scheduler.get_jobs():
        info = {"id": job.id, "name": job.name, "next_run": str(job.next_run_time)}
        if job.next_run_time is None:
            paused_jobs.append(info)
        else:
            active_jobs.append(info)
    return {
        "running": _scheduler.running,
        "state": state_map.get(_scheduler.state, "unknown"),
        "total_jobs": len(_scheduler.get_jobs()),
        "active_jobs": active_jobs,
        "paused_jobs": paused_jobs,
        "background_tasks": len(_background_tasks),
    }


@router.post("/scheduler/pause", dependencies=[Depends(require_admin)])
async def scheduler_pause():
    """暂停调度器"""
    from ..main import scheduler as _scheduler
    if not _scheduler.running:
        return {"message": "scheduler is not running", "paused": False}
    _scheduler.pause()
    logger.info("Scheduler paused via admin API")
    return {"message": "scheduler paused", "paused": True}


@router.post("/scheduler/resume", dependencies=[Depends(require_admin)])
async def scheduler_resume():
    """恢复调度器"""
    from ..main import scheduler as _scheduler
    if not _scheduler.running:
        return {"message": "scheduler is not running", "resumed": False}
    _scheduler.resume()
    logger.info("Scheduler resumed via admin API")
    return {"message": "scheduler resumed", "resumed": True}


# ---------------------------------------------------------------------------
# 后台任务控制
# ---------------------------------------------------------------------------
@router.post("/tasks/cancel-all", dependencies=[Depends(require_admin)])
async def cancel_all_background_tasks():
    """取消所有运行中的后台采集任务。"""
    from ..utils.tasks import _background_tasks
    # 1) 取消 asyncio 后台任务
    cancelled_count = 0
    for task in list(_background_tasks):
        if not task.done():
            task.cancel()
            cancelled_count += 1
    _background_tasks.clear()

    # 2) 标记 sync_task_logs 中运行中的任务为 FAILED
    sync_updated = 0
    if database.mongo_db is not None:
        result = await database.mongo_db["sync_task_logs"].update_many(
            {"status": "RUNNING"},
            {"$set": {
                "status": "FAILED",
                "error_message": "Cancelled by admin",
                "finished_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }},
        )
        sync_updated = result.modified_count

    # 3) 标记 crawl_jobs 中运行中/待执行的任务为 CANCELLED
    crawl_updated = 0
    crawl_sub_updated = 0
    if database.mongo_db is not None:
        result = await database.mongo_db["crawl_jobs"].update_many(
            {"status": {"$in": ["RUNNING", "PENDING"]}},
            {"$set": {"status": "CANCELLED", "updated_at": datetime.utcnow()}},
        )
        crawl_updated = result.modified_count
        result = await database.mongo_db["crawl_subtasks"].update_many(
            {"status": {"$in": ["RUNNING", "PENDING"]}},
            {"$set": {"status": "FAILED", "updated_at": datetime.utcnow()}},
        )
        crawl_sub_updated = result.modified_count

    logger.info(
        "Admin cancel-all: asyncio=%d sync_logs=%d crawl_jobs=%d crawl_subs=%d",
        cancelled_count, sync_updated, crawl_updated, crawl_sub_updated,
    )
    return {
        "message": "All tasks cancelled",
        "cancelled_asyncio_tasks": cancelled_count,
        "cancelled_sync_logs": sync_updated,
        "cancelled_crawl_jobs": crawl_updated,
        "cancelled_crawl_subtasks": crawl_sub_updated,
    }


# ---------------------------------------------------------------------------
# 采集健康监控
# ---------------------------------------------------------------------------
@router.get("/collect-health", dependencies=[Depends(require_admin)])
async def get_collect_health(
    date: Optional[str] = Query(None, description="日期 yyyy-MM-dd，默认今天"),
):
    """
    采集健康监控面板数据：
    - 各 action 的空数据/有数据统计
    - 连续空数据告警列表
    - Redis exec key 堆积数量
    - 轮询超时统计
    """
    if database.mongo_db is None:
        raise HTTPException(status_code=500, detail="MongoDB not initialized")

    target_date = date or datetime.utcnow().strftime("%Y-%m-%d")

    # --- 1. 各 action 的 is_empty 统计 ---
    coll = database.mongo_db[COLLECTION_NAME]
    actions = ["high", "hot", "chance", "industryViewV2", "industryTrendRange"]
    action_stats: Dict[str, Any] = {}

    for action in actions:
        pipeline = [
            {"$match": {
                "action": action,
                "updated_at": {
                    "$gte": datetime.strptime(target_date, "%Y-%m-%d"),
                    "$lt": datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=1),
                },
            }},
            {"$group": {
                "_id": "$is_empty",
                "count": {"$sum": 1},
            }},
        ]
        cursor = coll.aggregate(pipeline)
        results = await cursor.to_list(length=10)
        total = 0
        empty_count = 0
        data_count = 0
        for r in results:
            total += r["count"]
            if r["_id"] is True:
                empty_count = r["count"]
            else:
                data_count = r["count"]
        action_stats[action] = {
            "total": total,
            "empty": empty_count,
            "has_data": data_count,
            "empty_rate": round(empty_count / total, 4) if total > 0 else 0,
        }

    # --- 2. 连续空数据告警 (empty streak) ---
    empty_streaks: List[Dict[str, Any]] = []
    if database.redis_client is not None:
        try:
            cursor_val = "0"
            while True:
                cursor_val, keys = await database.redis_client.scan(
                    cursor=int(cursor_val), match="mengla:empty_streak:*", count=200,
                )
                for key in keys:
                    val = await database.redis_client.get(key)
                    if val is not None:
                        count = int(val)
                        if count >= 2:
                            # key = mengla:empty_streak:action:cat_id
                            parts = key.split(":") if isinstance(key, str) else key.decode().split(":")
                            action_name = parts[2] if len(parts) > 2 else "?"
                            cat_id_val = parts[3] if len(parts) > 3 else "?"
                            empty_streaks.append({
                                "action": action_name,
                                "cat_id": cat_id_val,
                                "streak": count,
                                "level": "critical" if count >= 5 else "warning" if count >= 3 else "info",
                            })
                if cursor_val == 0 or str(cursor_val) == "0":
                    break
            empty_streaks.sort(key=lambda x: x["streak"], reverse=True)
        except Exception as e:
            logger.warning("Failed to scan empty streaks: %s", e)

    # --- 3. Redis exec key 堆积数 ---
    exec_key_count = 0
    if database.redis_client is not None:
        try:
            cursor_val = "0"
            while True:
                cursor_val, keys = await database.redis_client.scan(
                    cursor=int(cursor_val), match="mengla:exec:*", count=500,
                )
                exec_key_count += len(keys)
                if cursor_val == 0 or str(cursor_val) == "0":
                    break
        except Exception:
            pass

    # --- 4. 数据库总文档统计 ---
    total_docs = await coll.count_documents({})
    empty_docs = await coll.count_documents({"is_empty": True})

    # --- 5. 最近采集记录 (最新 10 条) ---
    recent_cursor = coll.find(
        {},
        {"action": 1, "cat_id": 1, "granularity": 1, "period_key": 1,
         "is_empty": 1, "empty_reason": 1, "updated_at": 1, "source": 1, "_id": 0},
    ).sort("updated_at", -1).limit(10)
    recent_records = await recent_cursor.to_list(length=10)
    for rec in recent_records:
        if "updated_at" in rec and rec["updated_at"]:
            rec["updated_at"] = rec["updated_at"].isoformat()

    return {
        "date": target_date,
        "action_stats": action_stats,
        "empty_streaks": empty_streaks,
        "exec_key_count": exec_key_count,
        "total_documents": total_docs,
        "empty_documents": empty_docs,
        "recent_records": recent_records,
    }


# ---------------------------------------------------------------------------
# 数据清空
# ---------------------------------------------------------------------------
@router.post("/data/purge", dependencies=[Depends(require_admin)])
async def purge_all_data(body: PurgeRequest):
    """
    清空采集数据和缓存。
    需要 confirm=true 确认。
    targets 可选: "mongodb", "redis", "l1"
    """
    if not body.confirm:
        raise HTTPException(status_code=400, detail="请传入 confirm=true 确认清空操作")

    results: Dict[str, Any] = {}

    # 1) 清空 MongoDB 采集数据
    if "mongodb" in body.targets and database.mongo_db is not None:
        mongo_stats: Dict[str, int] = {}
        for coll_name in ["mengla_data", "crawl_jobs", "crawl_subtasks", "sync_task_logs"]:
            try:
                r = await database.mongo_db[coll_name].delete_many({})
                mongo_stats[coll_name] = r.deleted_count
            except Exception as e:
                mongo_stats[coll_name] = -1
                logger.warning("Failed to purge collection %s: %s", coll_name, e)
        results["mongodb"] = mongo_stats

    # 2) 清空 Redis 中 mengla:* 前缀的所有 key
    if "redis" in body.targets and database.redis_client is not None:
        redis_deleted = 0
        try:
            cursor_val = "0"
            while True:
                cursor_val, keys = await database.redis_client.scan(
                    cursor=int(cursor_val), match="mengla:*", count=500,
                )
                if keys:
                    await database.redis_client.delete(*keys)
                    redis_deleted += len(keys)
                if cursor_val == 0 or str(cursor_val) == "0":
                    break
        except Exception as e:
            logger.warning("Failed to purge Redis keys: %s", e)
            results["redis"] = {"error": str(e)}
        else:
            results["redis"] = {"deleted_keys": redis_deleted}

    # 3) 清空 L1 内存缓存
    if "l1" in body.targets:
        cache_manager = get_cache_manager()
        await cache_manager.clear_l1()
        results["l1"] = {"cleared": True}

    logger.info("Admin purge completed: targets=%s results=%s", body.targets, results)
    return {"message": "Purge completed", "results": results}
