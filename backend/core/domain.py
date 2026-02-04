from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import logging
import os

from ..infra import database
from .client import MengLaQueryParams, get_mengla_service
from ..utils.period import (
    format_for_collect_api,
    format_trend_range_for_api,
    make_period_keys,
    normalize_granularity,
    parse_timest_to_datetime,
    period_keys_in_range,
    period_to_date_range,
    timest_to_period_key,
    to_dashed_date,
)
from ..utils.config import (
    CONCURRENT_CONFIG,
    CACHE_TTL,
    COLLECTION_NAME,
    ACTION_MAPPING,
    get_cache_ttl,
    get_expired_at,
    build_redis_data_key,
)
from ..infra.cache import get_cache_manager, CacheManager
from ..infra.resilience import (
    retry_async,
    get_circuit_manager,
    CircuitBreakerError,
    is_retryable_exception,
)
from ..infra.logger import get_collect_logger, CollectLogger


# 有效的 action 列表
VALID_ACTIONS = {"high", "hot", "chance", "industryViewV2", "industryTrendRange"}


logger = logging.getLogger("mengla-domain")

# 同参采集请求去重表：key 通常为 f"{action}:{params_hash}"
IN_FLIGHT: Dict[str, asyncio.Future] = {}

# ==============================================================================
# 并发控制
# ==============================================================================
_semaphore: Optional[asyncio.Semaphore] = None


def get_semaphore() -> asyncio.Semaphore:
    """获取全局并发信号量"""
    global _semaphore
    if _semaphore is None:
        max_concurrent = CONCURRENT_CONFIG.get("max_concurrent", 5)
        _semaphore = asyncio.Semaphore(max_concurrent)
    return _semaphore


async def collect_with_concurrency_control(
    func,
    *args,
    **kwargs,
) -> Any:
    """带并发控制的采集执行"""
    semaphore = get_semaphore()
    async with semaphore:
        return await func(*args, **kwargs)


def _unwrap_result_data(data: Any) -> Any:
    """递归解包 resultData 或 data；不解包 injectedVars（多为请求参数）。"""
    while isinstance(data, dict):
        inner = data.get("resultData") or data.get("data")
        if inner is None:
            break
        data = inner
    return data


def _build_params_hash(
    action: str,
    product_id: str,
    catId: str,
    starRange: str,
    endRange: str,
    extra: Optional[Dict[str, Any]],
) -> str:
    payload = {
        "action": action,
        "product_id": product_id,
        "catId": catId,
        "starRange": starRange,
        "endRange": endRange,
        "extra": extra or {},
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _is_result_empty(result: Any, action: str) -> bool:
    """判断采集结果是否为空，为空则不应更新库。"""
    return not _should_persist_result(result, action)


def _is_stored_data_empty(doc: Optional[Dict[str, Any]]) -> bool:
    """判断库中已有文档是否为空（无 data 或 data 为空）。"""
    if doc is None:
        return True
    data = doc.get("data")
    if data is None:
        return True
    if isinstance(data, dict) and len(data) == 0:
        return True
    if isinstance(data, (list, str)) and len(data) == 0:
        return True
    return False


async def _dedupe_by_query(
    collection: Any,
    mongo_query: Dict[str, Any],
    collection_name: str = "",
) -> None:
    """
    同一 key 下若有多条文档则只保留一条：优先保留有数据的，其次保留 created_at 最新的。
    删除其余重复文档。
    """
    cursor = collection.find(mongo_query)
    docs = await cursor.to_list(length=100)
    if len(docs) <= 1:
        return
    # 排序：有数据的排前面，同为空则按 created_at 降序（新的在前）
    def _sort_key(d: Dict[str, Any]) -> tuple:
        empty = 1 if _is_stored_data_empty(d) else 0
        ct = d.get("created_at")
        ts = ct.timestamp() if ct is not None else 0.0
        return (empty, -ts)

    docs_sorted = sorted(docs, key=_sort_key)
    keep_id = docs_sorted[0]["_id"]
    deleted = 0
    for d in docs_sorted[1:]:
        await collection.delete_one({"_id": d["_id"]})
        deleted += 1
    if deleted:
        logger.warning(
            "MengLa dedupe: collection=%s query=%s kept 1 deleted %d",
            collection_name,
            mongo_query,
            deleted,
        )


def _cached_list_empty(data: Any, action: str) -> bool:
    """判断缓存的 high/hot/chance 文档是否列表为空，空则视为未命中以便重新拉取。与 _unwrap_result_data 一致先解包 resultData。"""
    if data is None or not isinstance(data, dict):
        return True
    inner = data.get("resultData") or data.get("data") or data
    if not isinstance(inner, dict):
        return True
    list_key = {"high": "highList", "hot": "hotList", "chance": "chanceList"}.get(action)
    if not list_key:
        return False
    lst = inner.get(list_key)
    if not isinstance(lst, dict):
        return True
    data_val = lst.get("data")
    if data_val is None:
        return True
    if isinstance(data_val, list):
        return len(data_val) == 0
    if isinstance(data_val, dict):
        items = data_val.get("list") if isinstance(data_val.get("list"), list) else []
        return len(items) == 0
    return True


def _should_persist_result(result: Any, action: str) -> bool:
    """
    仅当采集结果成功且非空时允许落库；code != 0 或 data 为空则不写入 Mongo/Redis 缓存。
    结构示例：highList/hotList/chanceList 为 { code, data: { list: [...] } } 或 { code, data: [...] }。
    与 _unwrap_result_data 一致先解包 resultData。
    """
    if not isinstance(result, dict):
        return False
    inner = result.get("resultData") or result.get("data") or result
    if not isinstance(inner, dict):
        return False
    list_key = {"high": "highList", "hot": "hotList", "chance": "chanceList"}.get(action)
    if list_key:
        lst = inner.get(list_key)
        if not isinstance(lst, dict):
            return False
        if lst.get("code") != 0:
            return False
        data_val = lst.get("data")
        if data_val is None:
            return False
        # data 可能是数组，也可能是 { list: [], pageNo, pageSize, ... }
        if isinstance(data_val, list):
            if len(data_val) == 0:
                return False
        elif isinstance(data_val, dict):
            items = data_val.get("list") if isinstance(data_val.get("list"), list) else []
            if len(items) == 0:
                return False
    if action == "industryTrendRange":
        points = _get_trend_points_from_result(result)
        if not points:
            return False
    return True


def _get_trend_points_from_result(result: Any) -> list:
    """从行业趋势 API 结果中解包出趋势点列表（用于落库与判空）。"""
    if not isinstance(result, dict):
        return []
    inner = result.get("resultData") or result.get("data") or result
    if not isinstance(inner, dict):
        return []
    trend = inner.get("industryTrendRange")
    if isinstance(trend, list):
        return trend
    if isinstance(trend, dict):
        data = trend.get("data")
        return data if isinstance(data, list) else []
    return []


async def _fetch_mengla_data(
    *,
    action: str,
    product_id: str = "",
    catId: str = "",
    dateType: str = "day",
    timest: str = "",
    starRange: str = "",
    endRange: str = "",
    extra: Optional[Dict[str, Any]] = None,
    timeout_seconds: Optional[int] = None,
) -> tuple[Any, str]:
    """
    内部采集函数：直接查询 MongoDB/Redis 或调用外部采集服务
    返回 (data, source)，source 为 "mongo" | "redis" | "fresh"
    """
    # 确保 Mongo 已初始化
    if database.mongo_db is None:
        mongo_uri = os.getenv("MONGO_URI", database.MONGO_URI_DEFAULT)
        mongo_db_name = os.getenv("MONGO_DB", database.MONGO_DB_DEFAULT)
        await database.connect_to_mongo(mongo_uri, mongo_db_name)
        if database.mongo_db is None:
            raise RuntimeError("MongoDB 未初始化")

    if action not in VALID_ACTIONS:
        raise ValueError(f"未知的 MengLa action: {action}")
    
    # 使用统一集合
    collection = database.mongo_db[COLLECTION_NAME]
    cat_id = catId or ""
    redis_prefix = build_redis_data_key(action, cat_id, "", "")

    # 1. 解析时间：行业趋势按粒度+范围内 period_key 列表；其他按单时间点 (granularity, period_key)
    is_trend = action == "industryTrendRange"
    if is_trend:
        if not (starRange and endRange) and not timest:
            raise ValueError("industryTrendRange 必须提供 starRange/endRange 或 timest")

        # 根据颗粒度解析时间范围：
        # - day: 支持 yyyy-MM-dd / yyyyMMdd
        # - month: starRange/endRange 视为月份 period_key，如 2025-01 或 202501
        # - quarter: 视为季度 period_key，如 2025-Q1 或 2025Q1
        # - year: 视为年份，如 2025
        granularity = normalize_granularity(dateType or "day")
        raw_start = (starRange or timest or "").strip()
        raw_end = (endRange or timest or "").strip() or raw_start

        if granularity == "day":
            start_dashed = to_dashed_date(raw_start)
            end_dashed = to_dashed_date(raw_end)
        else:
            # 对 month/quarter/year，先按 period_key 解析出真实日期区间
            start_dashed, _ = period_to_date_range(granularity, raw_start)
            _, end_dashed = period_to_date_range(granularity, raw_end)

        period_keys_list = period_keys_in_range(granularity, start_dashed, end_dashed)
        period_key = None  # 趋势按多 key 查/写，不设单 period_key
    else:
        granularity = normalize_granularity(dateType)
        if timest:
            dt = parse_timest_to_datetime(granularity, timest)
        else:
            dt = datetime.utcnow()
        periods = make_period_keys(dt)
        period_key = periods[granularity]
        period_keys_list = None
        start_dashed = end_dashed = None

    # 2. Redis key（使用新格式）
    redis_param_key = build_redis_data_key(action, cat_id, granularity, period_key or "")

    # 3. 优先从 MongoDB 查（趋势：范围内各 period_key 查齐后合并返回；其他：单条）
    if is_trend:
        if not period_keys_list:
            mongo_query = None
            existing_docs = []
        else:
            mongo_query = {
                "action": action,
                "cat_id": cat_id,
                "granularity": granularity,
                "period_key": {"$in": period_keys_list},
            }
            cursor = collection.find(mongo_query)
            existing_docs = await cursor.to_list(length=len(period_keys_list) + 100)
        by_key = {d["period_key"]: d for d in existing_docs}
        # 全量命中：范围内每个 period_key 都有文档，直接合并返回
        if period_keys_list and all(pk in by_key for pk in period_keys_list):
            points = []
            for pk in period_keys_list:
                doc = by_key[pk]
                data = doc.get("data")
                if not data:
                    break
                unwrapped = _unwrap_result_data(data)
                if isinstance(unwrapped, dict):
                    trend = unwrapped.get("industryTrendRange")
                    if isinstance(trend, list):
                        points.extend(trend)
                    elif isinstance(trend, dict) and isinstance(trend.get("data"), list):
                        points.extend(trend["data"])
                elif isinstance(unwrapped, list):
                    points.extend(unwrapped)
            if len(points) >= len(period_keys_list):
                points.sort(key=lambda p: (p.get("timest") or "") if isinstance(p, dict) else "")
                merged = {"industryTrendRange": {"data": points}}
                logger.info(
                    "MengLa Mongo hit (trend): action=%s cat_id=%s granularity=%s keys=%s",
                    action, cat_id, granularity, len(period_keys_list),
                )
                return (merged, "mongo")
        # 部分命中：Mongo 中只有范围内部分日期的数据，也合并返回，避免走采集超时
        if period_keys_list and by_key:
            points = []
            for pk in period_keys_list:
                if pk not in by_key:
                    continue
                doc = by_key[pk]
                data = doc.get("data")
                if not data:
                    continue
                unwrapped = _unwrap_result_data(data)
                if isinstance(unwrapped, dict):
                    trend = unwrapped.get("industryTrendRange")
                    if isinstance(trend, list):
                        points.extend(trend)
                    elif isinstance(trend, dict) and isinstance(trend.get("data"), list):
                        points.extend(trend["data"])
                elif isinstance(unwrapped, list):
                    points.extend(unwrapped)
            if points:
                points.sort(key=lambda p: (p.get("timest") or "") if isinstance(p, dict) else "")
                merged = {"industryTrendRange": {"data": points}}
                logger.info(
                    "MengLa Mongo partial (trend): action=%s requested=%s found=%s",
                    action, len(period_keys_list), len(by_key),
                )
                return (merged, "mongo", {"partial": True, "requested": len(period_keys_list), "found": len(by_key)})
        existing = None
    else:
        mongo_query = {
            "action": action,
            "cat_id": cat_id,
            "granularity": granularity,
            "period_key": period_key,
        }
        await _dedupe_by_query(collection, mongo_query, COLLECTION_NAME)
        existing = await collection.find_one(mongo_query)
        if existing is not None:
            data = existing.get("data")
            if action in ("high", "hot", "chance") and _cached_list_empty(data, action):
                existing = None
                data = None
            if existing is not None and data is not None:
                logger.info(
                    "MengLa Mongo hit: action=%s cat_id=%s granularity=%s period_key=%s",
                    action, cat_id, granularity, period_key,
                )
                if database.redis_client is not None:
                    ttl = get_cache_ttl(granularity)
                    await database.redis_client.set(
                        redis_param_key,
                        json.dumps(data, ensure_ascii=False),
                        ex=ttl,
                    )
                return (_unwrap_result_data(data), "mongo")

    # 4. 其次从 Redis 查（仅非趋势单条）
    if not is_trend and database.redis_client is not None:
        cached = await database.redis_client.get(redis_param_key)
        if cached is not None:
            _parsed = json.loads(cached)
            if action in ("high", "hot", "chance") and _cached_list_empty(_parsed, action):
                cached = None
            if cached is not None:
                logger.info(
                    "MengLa Redis hit: action=%s cat_id=%s granularity=%s period_key=%s",
                    action, cat_id, granularity, period_key,
                )
                _unwrapped = _unwrap_result_data(_parsed)
                return (_unwrapped, "redis")

    # 5. 从采集服务拉取并落库（增加 in-flight 去重，防止同参并发多次打采集）
    service = get_mengla_service()
    if is_trend:
        # 行业趋势：采集服务的 dateType 保留与请求颗粒度一致的语义
        # granularity 已由 normalize_granularity(dateType) 统一为 day/month/quarter/year
        if granularity == "day":
            date_type_for_api = "DAY"
        elif granularity == "month":
            date_type_for_api = "MONTH"
        elif granularity == "quarter":
            # 趋势按季度：与线上规范一致使用 QUARTERLY_FOR_YEAR
            date_type_for_api = "QUARTERLY_FOR_YEAR"
        elif granularity == "year":
            date_type_for_api = "YEAR"
        else:
            date_type_for_api = "DAY"

        raw_start = (starRange or start_dashed or "").strip()
        raw_end = (endRange or end_dashed or "").strip() or raw_start
        star_for_api, end_for_api = format_trend_range_for_api(
            granularity, raw_start, raw_end
        )
        # timest 为区间结束点的 API 格式（保留连字符：yyyy-MM / yyyy-Qn / yyyy）
        timest_for_api = end_for_api
    else:
        # industryViewV2 季榜：与示例完全一致，dateType=QUARTERLY_FOR_YEAR，timest/starRange/endRange=yyyy-Qn
        if action == "industryViewV2" and granularity == "quarter":
            date_type_for_api = "QUARTERLY_FOR_YEAR"
            _quarter_val = (timest or "").strip() or period_key
            timest_for_api = format_for_collect_api("quarter", _quarter_val)
            star_for_api = (starRange or "").strip() or timest_for_api
            end_for_api = (endRange or "").strip() or timest_for_api
        else:
            date_type_for_api = (dateType or granularity).strip() or granularity
            timest_for_api = (timest or "").strip() or period_key
            star_for_api = (starRange or "").strip() or timest_for_api
            end_for_api = (endRange or "").strip() or timest_for_api

    params = MengLaQueryParams(
        action=action,
        product_id=product_id or "",
        catId=catId or "",
        dateType=date_type_for_api,
        timest=timest_for_api,
        starRange=star_for_api,
        endRange=end_for_api,
        extra=extra or {},
    )

    async def _fetch_and_persist() -> tuple[Any, str]:
        """真正向采集服务发请求并落库，供 in-flight 去重复用。"""
        base_url = os.getenv("COLLECT_SERVICE_URL", "http://localhost:3001")
        logger.info(
            "[MengLa] collect_start action=%s timeout_sec=%s base_url=%s",
            action,
            timeout_seconds,
            base_url.split("?")[0] if base_url else "",
        )
        t0 = time.time()
        result = await service.query(params, use_cache=False, timeout_seconds=timeout_seconds)
        elapsed = time.time() - t0
        try:
            result_size = len(json.dumps(result, ensure_ascii=False))
        except (TypeError, ValueError):
            result_size = -1
        logger.info(
            "[MengLa] collect_done action=%s elapsed_sec=%.2f result_size=%s",
            action,
            elapsed,
            result_size,
        )

        # 6. 落库：趋势按颗粒拆分为多文档写入，其他单条写入（使用新统一集合结构）
        if _is_result_empty(result, action):
            logger.info("MengLa skip persist (empty): action=%s", action)
        else:
            now = datetime.utcnow()
            ttl = get_cache_ttl(granularity)
            expired_at = get_expired_at(granularity)
            
            if is_trend:
                points = _get_trend_points_from_result(result)
                for point in points:
                    if not isinstance(point, dict):
                        continue
                    pt_timest = point.get("timest") or ""
                    pk = timest_to_period_key(granularity, pt_timest)
                    doc = {
                        "action": action,
                        "cat_id": cat_id,
                        "granularity": granularity,
                        "period_key": pk,
                        "data": {"industryTrendRange": {"data": [point]}},
                        "source": "fresh",
                        "created_at": now,
                        "updated_at": now,
                        "expired_at": expired_at,
                    }
                    filter_doc = {
                        "action": action,
                        "cat_id": cat_id,
                        "granularity": granularity,
                        "period_key": pk,
                    }
                    await collection.replace_one(filter_doc, doc, upsert=True)
                    if database.redis_client is not None:
                        rk = build_redis_data_key(action, cat_id, granularity, pk)
                        await database.redis_client.set(
                            rk, json.dumps(doc["data"], ensure_ascii=False), ex=ttl
                        )
                logger.info(
                    "MengLa stored (trend): action=%s cat_id=%s granularity=%s points=%s",
                    action, cat_id, granularity, len(points),
                )
            else:
                existing_again = await collection.find_one(mongo_query)
                if existing_again is not None and not _is_stored_data_empty(existing_again):
                    logger.info(
                        "MengLa skip persist (exists): action=%s cat_id=%s period_key=%s",
                        action, cat_id, period_key,
                    )
                else:
                    doc = {
                        "action": action,
                        "cat_id": cat_id,
                        "granularity": granularity,
                        "period_key": period_key,
                        "data": result,
                        "source": "fresh",
                        "created_at": now,
                        "updated_at": now,
                        "expired_at": expired_at,
                    }
                    await collection.replace_one(mongo_query, doc, upsert=True)
                    logger.info(
                        "MengLa stored: action=%s cat_id=%s granularity=%s period_key=%s",
                        action, cat_id, granularity, period_key,
                    )
                    if database.redis_client is not None:
                        await database.redis_client.set(
                            redis_param_key, json.dumps(result, ensure_ascii=False), ex=ttl
                        )

        if is_trend:
            points = _get_trend_points_from_result(result)
            points.sort(key=lambda p: (p.get("timest") or "") if isinstance(p, dict) else "")
            _unwrapped = {"industryTrendRange": {"data": points}}
        else:
            _unwrapped = _unwrap_result_data(result)
        return (_unwrapped, "fresh")

    # 使用 in-flight 表防止同参并发多次打采集
    request_key = f"{action}:{cat_id}:{granularity}:{period_key or ''}"
    existing_task = IN_FLIGHT.get(request_key)
    if existing_task is not None:
        return await existing_task

    loop = asyncio.get_running_loop()
    task: asyncio.Future = loop.create_task(_fetch_and_persist())
    IN_FLIGHT[request_key] = task
    try:
        return await task
    finally:
        # 仅创建该 task 的请求负责清理
        if IN_FLIGHT.get(request_key) is task:
            IN_FLIGHT.pop(request_key, None)


# ==============================================================================
# 并发批量采集
# ==============================================================================
async def collect_batch(
    tasks: List[Dict[str, Any]],
    max_concurrent: Optional[int] = None,
) -> List[Tuple[Dict[str, Any], Any, str, Optional[Exception]]]:
    """
    并发批量采集
    
    Args:
        tasks: 采集任务列表，每个任务是 query_mengla_domain 的参数字典
        max_concurrent: 最大并发数，默认从配置读取
    
    Returns:
        结果列表，每个元素为 (task, data, source, error)
        - task: 原始任务参数
        - data: 采集结果数据（成功时）
        - source: 数据来源 ("mongo"/"redis"/"fresh")
        - error: 异常对象（失败时）
    """
    if not tasks:
        return []
    
    _max_concurrent = max_concurrent or CONCURRENT_CONFIG.get("max_concurrent", 5)
    semaphore = asyncio.Semaphore(_max_concurrent)
    
    async def execute_one(task: Dict[str, Any]) -> Tuple[Dict[str, Any], Any, str, Optional[Exception]]:
        async with semaphore:
            try:
                data, source = await _fetch_mengla_data(**task)
                return (task, data, source, None)
            except Exception as e:
                logger.warning("Batch collect task failed: %s error=%s", task, e)
                return (task, None, "", e)
    
    results = await asyncio.gather(
        *[execute_one(t) for t in tasks],
        return_exceptions=False,  # 异常已在 execute_one 中处理
    )
    
    return results


async def collect_batch_with_retry(
    tasks: List[Dict[str, Any]],
    max_concurrent: Optional[int] = None,
    max_retries: int = 2,
) -> Dict[str, Any]:
    """
    带重试的并发批量采集
    
    Args:
        tasks: 采集任务列表
        max_concurrent: 最大并发数
        max_retries: 失败任务最大重试次数
    
    Returns:
        统计信息字典，包含 success/failed/results
    """
    collect_logger = get_collect_logger()
    
    results = await collect_batch(tasks, max_concurrent)
    
    succeeded = []
    failed = []
    
    for task, data, source, error in results:
        if error is None:
            succeeded.append({"task": task, "data": data, "source": source})
        else:
            failed.append({"task": task, "error": str(error), "retryable": is_retryable_exception(error)})
    
    # 重试失败的任务
    retry_tasks = [f["task"] for f in failed if f["retryable"]]
    for retry_round in range(max_retries):
        if not retry_tasks:
            break
        
        logger.info("Retry round %d: %d tasks", retry_round + 1, len(retry_tasks))
        retry_results = await collect_batch(retry_tasks, max_concurrent)
        
        new_retry_tasks = []
        for task, data, source, error in retry_results:
            if error is None:
                succeeded.append({"task": task, "data": data, "source": source})
                # 从 failed 中移除
                failed = [f for f in failed if f["task"] != task]
            elif is_retryable_exception(error):
                new_retry_tasks.append(task)
        
        retry_tasks = new_retry_tasks
    
    return {
        "total": len(tasks),
        "success": len(succeeded),
        "failed": len(failed),
        "results": succeeded,
        "errors": failed,
    }


# ==============================================================================
# 统一采集接口（三级缓存 + 熔断器）
# ==============================================================================
async def query_mengla(
    *,
    action: str,
    # 新参数名
    cat_id: str = "",
    granularity: str = "",
    period_key: str = "",
    # 旧参数名（兼容）
    catId: str = "",
    dateType: str = "",
    timest: str = "",
    starRange: str = "",
    endRange: str = "",
    product_id: str = "",
    # 通用参数
    extra: Optional[Dict[str, Any]] = None,
    use_cache: bool = True,
    timeout_seconds: Optional[int] = None,
) -> Tuple[Any, str]:
    """
    统一的 MengLa 查询接口
    
    缓存层级：L1 本地缓存 → L2 Redis → L3 MongoDB → 外部采集
    附加功能：熔断器保护、结构化日志
    
    Args:
        action: 操作类型 (high/hot/chance/industryViewV2/industryTrendRange)
        cat_id/catId: 类目ID，空字符串表示全类目
        granularity/dateType: 颗粒度 (day/month/quarter/year)
        period_key/timest: 时间周期 key
        starRange/endRange: 趋势范围（仅 industryTrendRange 使用）
        extra: 额外参数
        use_cache: 是否使用缓存
        timeout_seconds: 超时时间
    
    Returns:
        (data, source) 元组，source 为 "l1" | "l2" | "l3" | "fresh"
    """
    # 参数兼容：新参数优先
    _cat_id = cat_id or catId or ""
    _granularity = normalize_granularity(granularity or dateType or "day")
    _period_key = period_key or timest or ""
    _star_range = starRange or ""
    _end_range = endRange or ""
    _product_id = product_id or ""
    
    collect_logger = get_collect_logger()
    cache_manager = get_cache_manager()
    circuit_manager = get_circuit_manager()
    
    start_time = time.time()
    trace_id = collect_logger.start(action, _cat_id, _granularity, _period_key)
    
    try:
        # 1. 检查三级缓存（非趋势接口）
        is_trend = action == "industryTrendRange"
        if use_cache and not is_trend:
            cached_data, cache_source = await cache_manager.get(
                action, _cat_id, _granularity, _period_key
            )
            if cached_data is not None:
                duration_ms = int((time.time() - start_time) * 1000)
                collect_logger.cache_hit(cache_source, duration_ms)
                return (cached_data, cache_source)
        
        # 2. 通过熔断器调用外部采集
        circuit = await circuit_manager.get_or_create(f"mengla_{action}")
        
        async def fetch_from_service():
            # 调用内部采集函数
            data, source = await _fetch_mengla_data(
                action=action,
                product_id=_product_id,
                catId=_cat_id,
                dateType=_granularity,
                timest=_period_key,
                starRange=_star_range,
                endRange=_end_range,
                extra=extra,
                timeout_seconds=timeout_seconds,
            )
            return data, source
        
        data, source = await circuit.call(fetch_from_service)
        
        # 3. 写入三级缓存（非趋势接口）
        duration_ms = int((time.time() - start_time) * 1000)
        if not is_trend:
            await cache_manager.set(
                action, _cat_id, _granularity, _period_key,
                data, source="fresh", collect_duration_ms=duration_ms
            )
        
        collect_logger.success(source, duration_ms)
        return (data, source)
        
    except CircuitBreakerError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        collect_logger.circuit_open(e.circuit_name)
        collect_logger.failure(e, duration_ms, retryable=False)
        raise
        
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        collect_logger.failure(e, duration_ms, retryable=is_retryable_exception(e))
        raise
        
    finally:
        collect_logger.finish()
