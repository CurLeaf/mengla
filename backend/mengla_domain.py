from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional

import logging
import os

from . import database
from .mengla_client import MengLaQueryParams, get_mengla_service
from .period_utils import (
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


ACTION_CONFIG: Dict[str, Dict[str, str]] = {
    "high": {"collection": "mengla_high_reports", "redis_prefix": "mengla:high"},
    "hot": {"collection": "mengla_hot_reports", "redis_prefix": "mengla:hot"},
    "chance": {"collection": "mengla_chance_reports", "redis_prefix": "mengla:chance"},
    "industryViewV2": {
        "collection": "mengla_view_reports",
        "redis_prefix": "mengla:view",
    },
    "industryTrendRange": {
        "collection": "mengla_trend_reports",
        "redis_prefix": "mengla:trend",
    },
}


logger = logging.getLogger("mengla-domain")

# 同参采集请求去重表：key 通常为 f"{action}:{params_hash}"
IN_FLIGHT: Dict[str, asyncio.Future] = {}


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


async def query_mengla_domain(
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
    统一的 MengLa 领域查询逻辑：
    返回 (data, source)，source 为 "mongo" | "redis" | "fresh"，便于排查缓存。
    查询顺序：1) MongoDB  2) Redis  3) 采集服务（fresh），命中后返回，未命中则继续下一级。
    - 根据 action + dateType + timest 计算 granularity + period_key
    - 先按 (granularity, period_key, params_hash) 查 Mongo，再查 Redis，最后调 MengLaService
    - 从采集服务拉取后写入 Mongo 与 Redis 参数缓存
    """
    # 确保 Mongo 已初始化；如果 FastAPI 启动钩子未执行，这里兜底连接一次
    if database.mongo_db is None:
        mongo_uri = os.getenv("MONGO_URI", database.MONGO_URI_DEFAULT)
        mongo_db_name = os.getenv("MONGO_DB", database.MONGO_DB_DEFAULT)
        await database.connect_to_mongo(mongo_uri, mongo_db_name)
        if database.mongo_db is None:
            raise RuntimeError("MongoDB 未初始化")

    cfg = ACTION_CONFIG.get(action)
    if cfg is None:
        raise ValueError(f"未知的 MengLa action: {action}")

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

    # 2. 参数 hash：趋势按颗粒存储，hash 不包含 starRange/endRange，便于多 key 共用
    params_hash = _build_params_hash(
        action=action,
        product_id=product_id or "",
        catId=catId or "",
        starRange="" if is_trend else (starRange or ""),
        endRange="" if is_trend else (endRange or ""),
        extra=extra,
    )
    redis_param_key = f"{cfg['redis_prefix']}:{granularity}:{period_key or ''}:{params_hash}"

    collection = database.mongo_db[cfg["collection"]]

    # 3. 优先从 MongoDB 查（趋势：范围内各 period_key 查齐后合并返回；其他：单条）
    if is_trend:
        if not period_keys_list:
            mongo_query = None
            existing_docs = []
        else:
            mongo_query = {
                "granularity": granularity,
                "period_key": {"$in": period_keys_list},
                "params_hash": params_hash,
            }
            # 趋势按 key 唯一，不按整批去重
            cursor = collection.find(mongo_query)
            existing_docs = await cursor.to_list(length=len(period_keys_list) + 100)
        by_key = {d["period_key"]: d for d in existing_docs}
        if period_keys_list and all(pk in by_key for pk in period_keys_list):
            # 按 period_key 顺序合并为前端期望的 { industryTrendRange: { data: [...] } }
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
                    "MengLa Mongo hit (trend): collection=%s granularity=%s keys=%s hash=%s",
                    cfg["collection"],
                    granularity,
                    len(period_keys_list),
                    params_hash,
                )
                return (merged, "mongo")
        existing = None
    else:
        mongo_query = {
            "granularity": granularity,
            "period_key": period_key,
            "params_hash": params_hash,
        }
        await _dedupe_by_query(collection, mongo_query, cfg["collection"])
        existing = await collection.find_one(mongo_query)
        if existing is not None:
            data = existing.get("data")
            if action in ("high", "hot", "chance") and _cached_list_empty(data, action):
                existing = None
                data = None
            if existing is not None and data is not None:
                logger.info(
                    "MengLa Mongo hit: collection=%s query=%s hash=%s",
                    cfg["collection"],
                    mongo_query,
                    params_hash,
                )
                if database.redis_client is not None:
                    await database.redis_client.set(
                        redis_param_key,
                        json.dumps(data, ensure_ascii=False),
                        ex=60 * 60 * 24,
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
                    "MengLa Redis cache hit: action=%s granularity=%s period_key=%s hash=%s",
                    action,
                    granularity,
                    period_key,
                    params_hash,
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
        result = await service.query(params, use_cache=False, timeout_seconds=timeout_seconds)

        # 6. 落库：趋势按颗粒拆分为多文档写入，其他单条写入
        if _is_result_empty(result, action):
            logger.info(
                "MengLa skip persist (new result empty): action=%s",
                action,
            )
        else:
            now = datetime.utcnow()
            if is_trend:
                points = _get_trend_points_from_result(result)
                ttl = 60 * 60 * 24 * 7 if granularity == "day" else 60 * 60 * 24 * 30
                for point in points:
                    if not isinstance(point, dict):
                        continue
                    pt_timest = point.get("timest") or ""
                    pk = timest_to_period_key(granularity, pt_timest)
                    doc = {
                        "granularity": granularity,
                        "period_key": pk,
                        "params_hash": params_hash,
                        "data": {"industryTrendRange": {"data": [point]}},
                        "created_at": now,
                    }
                    filter_period = {
                        "granularity": granularity,
                        "period_key": pk,
                        "params_hash": params_hash,
                    }
                    await collection.replace_one(filter_period, doc, upsert=True)
                    if database.redis_client is not None:
                        rk = f"{cfg['redis_prefix']}:{granularity}:{pk}:{params_hash}"
                        await database.redis_client.set(
                            rk, json.dumps(doc["data"], ensure_ascii=False), ex=ttl
                        )
                logger.info(
                    "MengLa stored to Mongo (trend): collection=%s granularity=%s points=%s hash=%s",
                    cfg["collection"],
                    granularity,
                    len(points),
                    params_hash,
                )
            else:
                existing_again = await collection.find_one(mongo_query)
                if existing_again is not None and not _is_stored_data_empty(existing_again):
                    logger.info(
                        "MengLa skip persist (DB already has data): action=%s query=%s",
                        action,
                        mongo_query,
                    )
                else:
                    doc = {
                        "granularity": granularity,
                        "period_key": period_key,
                        "params_hash": params_hash,
                        "data": result,
                        "created_at": now,
                    }
                    await collection.replace_one(
                        {
                            "granularity": granularity,
                            "period_key": period_key,
                            "params_hash": params_hash,
                        },
                        doc,
                        upsert=True,
                    )
                    logger.info(
                        "MengLa stored to Mongo: collection=%s doc_keys=%s hash=%s",
                        cfg["collection"],
                        list(doc.keys()),
                        params_hash,
                    )
                    if database.redis_client is not None:
                        ttl = 60 * 60 * 24 * 7 if granularity == "day" else 60 * 60 * 24 * 30
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
    request_key = f"{action}:{params_hash}"
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

