"""
三级缓存架构：L1 本地缓存 → L2 Redis → L3 MongoDB → 外部采集

请求流程：
1. 检查 L1 本地缓存（进程内，LRU，5分钟）
2. 检查 L2 Redis 缓存（分布式，按颗粒度 TTL）
3. 检查 L3 MongoDB（持久化存储）
4. 调用外部采集服务
5. 回填各级缓存
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, List

from cachetools import TTLCache

from ..utils.config import (
    L1_CACHE_CONFIG,
    CACHE_TTL,
    COLLECTION_NAME,
    REDIS_KEY_PREFIX,
    get_cache_ttl,
    get_expired_at,
    build_redis_data_key,
)
from . import database


logger = logging.getLogger("mengla-cache")


# ==============================================================================
# L1 本地缓存（进程内 LRU + TTL）
# ==============================================================================
class L1Cache:
    """L1 本地缓存：进程内 LRU 缓存，带 TTL"""
    
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self._cache = TTLCache(maxsize=max_size, ttl=ttl)
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
    
    def _build_key(self, action: str, cat_id: str, granularity: str, period_key: str) -> str:
        return f"{action}:{cat_id or 'all'}:{granularity}:{period_key}"
    
    async def get(
        self, action: str, cat_id: str, granularity: str, period_key: str
    ) -> Optional[Any]:
        key = self._build_key(action, cat_id, granularity, period_key)
        async with self._lock:
            result = self._cache.get(key)
            if result is not None:
                self._hits += 1
                logger.debug(f"L1 cache hit: {key}")
            else:
                self._misses += 1
            return result
    
    async def set(
        self, action: str, cat_id: str, granularity: str, period_key: str, data: Any
    ) -> None:
        key = self._build_key(action, cat_id, granularity, period_key)
        async with self._lock:
            self._cache[key] = data
            logger.debug(f"L1 cache set: {key}")
    
    async def delete(
        self, action: str, cat_id: str, granularity: str, period_key: str
    ) -> None:
        key = self._build_key(action, cat_id, granularity, period_key)
        async with self._lock:
            self._cache.pop(key, None)
    
    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "size": len(self._cache),
            "max_size": self._cache.maxsize,
        }


# 全局 L1 缓存实例
_l1_cache: Optional[L1Cache] = None


def get_l1_cache() -> L1Cache:
    """获取 L1 缓存实例（单例）"""
    global _l1_cache
    if _l1_cache is None:
        _l1_cache = L1Cache(
            max_size=L1_CACHE_CONFIG["max_size"],
            ttl=L1_CACHE_CONFIG["ttl"],
        )
    return _l1_cache


# ==============================================================================
# L2 Redis 缓存
# ==============================================================================
class L2Cache:
    """L2 Redis 缓存：分布式缓存"""
    
    def __init__(self):
        self._hits = 0
        self._misses = 0
    
    async def get(
        self, action: str, cat_id: str, granularity: str, period_key: str
    ) -> Optional[Any]:
        if database.redis_client is None:
            return None
        
        key = build_redis_data_key(action, cat_id, granularity, period_key)
        try:
            cached = await database.redis_client.get(key)
            if cached is not None:
                self._hits += 1
                logger.debug(f"L2 Redis hit: {key}")
                return json.loads(cached)
            self._misses += 1
            return None
        except Exception as e:
            logger.warning(f"L2 Redis get error: {e}")
            self._misses += 1
            return None
    
    async def set(
        self, action: str, cat_id: str, granularity: str, period_key: str, data: Any
    ) -> None:
        if database.redis_client is None:
            return
        
        key = build_redis_data_key(action, cat_id, granularity, period_key)
        ttl = get_cache_ttl(granularity)
        try:
            await database.redis_client.set(
                key, json.dumps(data, ensure_ascii=False), ex=ttl
            )
            logger.debug(f"L2 Redis set: {key}, ttl={ttl}s")
        except Exception as e:
            logger.warning(f"L2 Redis set error: {e}")
    
    async def delete(
        self, action: str, cat_id: str, granularity: str, period_key: str
    ) -> None:
        if database.redis_client is None:
            return
        
        key = build_redis_data_key(action, cat_id, granularity, period_key)
        try:
            await database.redis_client.delete(key)
        except Exception as e:
            logger.warning(f"L2 Redis delete error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
        }


# 全局 L2 缓存实例
_l2_cache: Optional[L2Cache] = None


def get_l2_cache() -> L2Cache:
    """获取 L2 缓存实例（单例）"""
    global _l2_cache
    if _l2_cache is None:
        _l2_cache = L2Cache()
    return _l2_cache


# ==============================================================================
# L3 MongoDB 存储
# ==============================================================================
class L3Storage:
    """L3 MongoDB 持久化存储"""
    
    def __init__(self):
        self._hits = 0
        self._misses = 0
    
    async def get(
        self, action: str, cat_id: str, granularity: str, period_key: str
    ) -> Optional[Dict[str, Any]]:
        if database.mongo_db is None:
            return None
        
        collection = database.mongo_db[COLLECTION_NAME]
        query = {
            "action": action,
            "cat_id": cat_id or "",
            "granularity": granularity,
            "period_key": period_key,
        }
        
        try:
            doc = await collection.find_one(query)
            if doc is not None:
                self._hits += 1
                logger.debug(f"L3 MongoDB hit: {query}")
                return doc
            self._misses += 1
            return None
        except Exception as e:
            logger.warning(f"L3 MongoDB get error: {e}")
            self._misses += 1
            return None
    
    async def set(
        self,
        action: str,
        cat_id: str,
        granularity: str,
        period_key: str,
        data: Any,
        data_hash: str,
        source: str = "fresh",
        collect_duration_ms: int = 0,
    ) -> None:
        if database.mongo_db is None:
            return
        
        collection = database.mongo_db[COLLECTION_NAME]
        now = datetime.utcnow()
        expired_at = get_expired_at(granularity)
        
        doc = {
            "action": action,
            "cat_id": cat_id or "",
            "granularity": granularity,
            "period_key": period_key,
            "data": data,
            "data_hash": data_hash,
            "source": source,
            "collect_duration_ms": collect_duration_ms,
            "created_at": now,
            "updated_at": now,
            "expired_at": expired_at,
        }
        
        filter_query = {
            "action": action,
            "cat_id": cat_id or "",
            "granularity": granularity,
            "period_key": period_key,
        }
        
        try:
            await collection.replace_one(filter_query, doc, upsert=True)
            logger.debug(f"L3 MongoDB set: {filter_query}")
        except Exception as e:
            logger.warning(f"L3 MongoDB set error: {e}")
    
    async def get_batch(
        self, action: str, cat_id: str, granularity: str, period_keys: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """批量获取多个 period_key 的文档"""
        if database.mongo_db is None:
            return {}
        
        collection = database.mongo_db[COLLECTION_NAME]
        query = {
            "action": action,
            "cat_id": cat_id or "",
            "granularity": granularity,
            "period_key": {"$in": period_keys},
        }
        
        try:
            cursor = collection.find(query)
            docs = await cursor.to_list(length=len(period_keys) + 100)
            return {d["period_key"]: d for d in docs}
        except Exception as e:
            logger.warning(f"L3 MongoDB get_batch error: {e}")
            return {}
    
    def get_stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
        }


# 全局 L3 存储实例
_l3_storage: Optional[L3Storage] = None


def get_l3_storage() -> L3Storage:
    """获取 L3 存储实例（单例）"""
    global _l3_storage
    if _l3_storage is None:
        _l3_storage = L3Storage()
    return _l3_storage


# ==============================================================================
# 三级缓存管理器
# ==============================================================================
class CacheManager:
    """三级缓存管理器：统一管理 L1/L2/L3 缓存"""
    
    def __init__(self):
        self.l1 = get_l1_cache()
        self.l2 = get_l2_cache()
        self.l3 = get_l3_storage()
    
    async def get(
        self, action: str, cat_id: str, granularity: str, period_key: str
    ) -> Tuple[Optional[Any], str]:
        """
        按层级查询缓存，返回 (data, source)
        source: "l1" | "l2" | "l3" | None
        """
        # L1 本地缓存
        data = await self.l1.get(action, cat_id, granularity, period_key)
        if data is not None:
            return (data, "l1")
        
        # L2 Redis 缓存
        data = await self.l2.get(action, cat_id, granularity, period_key)
        if data is not None:
            # 回填 L1
            await self.l1.set(action, cat_id, granularity, period_key, data)
            return (data, "l2")
        
        # L3 MongoDB
        doc = await self.l3.get(action, cat_id, granularity, period_key)
        if doc is not None:
            data = doc.get("data")
            if data is not None:
                # 回填 L1 和 L2
                await self.l1.set(action, cat_id, granularity, period_key, data)
                await self.l2.set(action, cat_id, granularity, period_key, data)
                return (data, "l3")
        
        return (None, "")
    
    async def set(
        self,
        action: str,
        cat_id: str,
        granularity: str,
        period_key: str,
        data: Any,
        source: str = "fresh",
        collect_duration_ms: int = 0,
    ) -> None:
        """写入所有层级缓存"""
        # 计算数据 hash
        try:
            data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
            data_hash = hashlib.md5(data_str.encode()).hexdigest()
        except (TypeError, ValueError):
            data_hash = ""
        
        # 并行写入所有层级
        await asyncio.gather(
            self.l1.set(action, cat_id, granularity, period_key, data),
            self.l2.set(action, cat_id, granularity, period_key, data),
            self.l3.set(
                action, cat_id, granularity, period_key,
                data, data_hash, source, collect_duration_ms
            ),
            return_exceptions=True,
        )
    
    async def invalidate(
        self, action: str, cat_id: str, granularity: str, period_key: str
    ) -> None:
        """使指定缓存失效"""
        await asyncio.gather(
            self.l1.delete(action, cat_id, granularity, period_key),
            self.l2.delete(action, cat_id, granularity, period_key),
            return_exceptions=True,
        )
    
    async def clear_l1(self) -> None:
        """清空 L1 缓存"""
        await self.l1.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取所有层级缓存统计"""
        return {
            "l1": self.l1.get_stats(),
            "l2": self.l2.get_stats(),
            "l3": self.l3.get_stats(),
        }


# 全局缓存管理器实例
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """获取缓存管理器实例（单例）"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


# ==============================================================================
# 缓存预热
# ==============================================================================
async def warmup_cache(
    actions: Optional[List[str]] = None,
    cat_ids: Optional[List[str]] = None,
    granularities: Optional[List[str]] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    缓存预热：从 MongoDB 加载热点数据到 L1 和 L2 缓存
    
    Args:
        actions: 要预热的 action 列表，None 表示全部
        cat_ids: 要预热的类目列表，None 表示全部
        granularities: 要预热的颗粒度列表，None 表示全部
        limit: 最大预热条数
    
    Returns:
        预热统计信息
    """
    if database.mongo_db is None:
        return {"error": "MongoDB not connected", "loaded": 0}
    
    collection = database.mongo_db[COLLECTION_NAME]
    cache_manager = get_cache_manager()
    
    # 构建查询条件
    query: Dict[str, Any] = {}
    if actions:
        query["action"] = {"$in": actions}
    if cat_ids:
        query["cat_id"] = {"$in": cat_ids}
    if granularities:
        query["granularity"] = {"$in": granularities}
    
    # 按更新时间降序获取最新数据
    cursor = collection.find(query).sort("updated_at", -1).limit(limit)
    
    loaded = 0
    errors = 0
    
    try:
        async for doc in cursor:
            try:
                action = doc.get("action", "")
                cat_id = doc.get("cat_id", "")
                granularity = doc.get("granularity", "")
                period_key = doc.get("period_key", "")
                data = doc.get("data")
                
                if data is not None:
                    await cache_manager.l1.set(action, cat_id, granularity, period_key, data)
                    await cache_manager.l2.set(action, cat_id, granularity, period_key, data)
                    loaded += 1
            except Exception as e:
                logger.warning(f"Warmup item error: {e}")
                errors += 1
    except Exception as e:
        logger.error(f"Warmup cursor error: {e}")
    
    result = {
        "loaded": loaded,
        "errors": errors,
        "query": query,
    }
    logger.info(f"Cache warmup completed: {result}")
    return result
