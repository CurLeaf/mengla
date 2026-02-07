"""
指标收集模块

提供：
1. 采集指标统计（成功率、耗时、缓存命中率等）
2. 实时指标查询
3. 历史指标存储
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Deque

from ..utils.config import REDIS_KEY_PREFIX
from . import database


# ==============================================================================
# 指标数据结构
# ==============================================================================
@dataclass
class CollectMetrics:
    """采集指标"""
    total_tasks: int = 0
    success_count: int = 0
    fail_count: int = 0
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    total_duration_ms: int = 0
    
    # 按来源统计
    source_counts: Dict[str, int] = field(default_factory=dict)
    
    # 按 action 统计
    action_counts: Dict[str, int] = field(default_factory=dict)
    action_failures: Dict[str, int] = field(default_factory=dict)
    
    # 时间戳
    start_time: Optional[datetime] = None
    last_update_time: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_tasks == 0:
            return 1.0
        return self.success_count / self.total_tasks
    
    @property
    def cache_hit_rate(self) -> float:
        """缓存命中率"""
        total = self.cache_hit_count + self.cache_miss_count
        if total == 0:
            return 0.0
        return self.cache_hit_count / total
    
    @property
    def avg_duration_ms(self) -> float:
        """平均耗时（毫秒）"""
        if self.success_count == 0:
            return 0.0
        return self.total_duration_ms / self.success_count
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "total_tasks": self.total_tasks,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "success_rate": round(self.success_rate, 4),
            "cache_hit_count": self.cache_hit_count,
            "cache_miss_count": self.cache_miss_count,
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "total_duration_ms": self.total_duration_ms,
            "source_counts": self.source_counts,
            "action_counts": self.action_counts,
            "action_failures": self.action_failures,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "last_update_time": self.last_update_time.isoformat() if self.last_update_time else None,
        }


@dataclass
class LatencyRecord:
    """延迟记录"""
    timestamp: datetime
    action: str
    duration_ms: int
    source: str
    success: bool


# ==============================================================================
# 指标收集器
# ==============================================================================
class MetricsCollector:
    """指标收集器"""
    
    def __init__(self, window_size: int = 1000):
        """
        Args:
            window_size: 滑动窗口大小，保留最近 N 条延迟记录
        """
        self._metrics = CollectMetrics()
        self._latency_records: Deque[LatencyRecord] = deque(maxlen=window_size)
        self._lock = asyncio.Lock()
        self._daily_metrics: Dict[str, CollectMetrics] = {}  # key: yyyy-MM-dd
    
    async def record_success(
        self,
        action: str,
        duration_ms: int,
        source: str,
        cache_hit: bool = False,
    ) -> None:
        """记录成功的采集"""
        async with self._lock:
            now = datetime.utcnow()
            
            self._metrics.total_tasks += 1
            self._metrics.success_count += 1
            self._metrics.total_duration_ms += duration_ms
            self._metrics.last_update_time = now
            
            if self._metrics.start_time is None:
                self._metrics.start_time = now
            
            # 来源统计
            self._metrics.source_counts[source] = self._metrics.source_counts.get(source, 0) + 1
            
            # action 统计
            self._metrics.action_counts[action] = self._metrics.action_counts.get(action, 0) + 1
            
            # 缓存统计
            if cache_hit:
                self._metrics.cache_hit_count += 1
            else:
                self._metrics.cache_miss_count += 1
            
            # 延迟记录
            self._latency_records.append(LatencyRecord(
                timestamp=now,
                action=action,
                duration_ms=duration_ms,
                source=source,
                success=True,
            ))
            
            # 每日统计
            date_key = now.strftime("%Y-%m-%d")
            await self._update_daily_metrics(date_key, action, duration_ms, source, success=True, cache_hit=cache_hit)
    
    async def record_failure(
        self,
        action: str,
        duration_ms: int,
        error_type: str = "",
    ) -> None:
        """记录失败的采集"""
        async with self._lock:
            now = datetime.utcnow()
            
            self._metrics.total_tasks += 1
            self._metrics.fail_count += 1
            self._metrics.cache_miss_count += 1
            self._metrics.last_update_time = now
            
            if self._metrics.start_time is None:
                self._metrics.start_time = now
            
            # action 失败统计
            self._metrics.action_failures[action] = self._metrics.action_failures.get(action, 0) + 1
            
            # 延迟记录
            self._latency_records.append(LatencyRecord(
                timestamp=now,
                action=action,
                duration_ms=duration_ms,
                source="error",
                success=False,
            ))
            
            # 每日统计
            date_key = now.strftime("%Y-%m-%d")
            await self._update_daily_metrics(date_key, action, duration_ms, "", success=False, cache_hit=False)
    
    def _cleanup_old_daily_metrics(self) -> None:
        """清理 30 天前的每日指标数据，防止 _daily_metrics 无限增长。"""
        max_days = 30
        cutoff = (datetime.utcnow() - timedelta(days=max_days)).strftime("%Y-%m-%d")
        expired_keys = [k for k in self._daily_metrics if k < cutoff]
        for k in expired_keys:
            del self._daily_metrics[k]

    async def _update_daily_metrics(
        self,
        date_key: str,
        action: str,
        duration_ms: int,
        source: str,
        success: bool,
        cache_hit: bool,
    ) -> None:
        """更新每日指标（同时清理过期数据）"""
        # 定期清理过期的每日指标
        self._cleanup_old_daily_metrics()

        if date_key not in self._daily_metrics:
            self._daily_metrics[date_key] = CollectMetrics()
            self._daily_metrics[date_key].start_time = datetime.utcnow()
        
        daily = self._daily_metrics[date_key]
        daily.total_tasks += 1
        daily.last_update_time = datetime.utcnow()
        
        if success:
            daily.success_count += 1
            daily.total_duration_ms += duration_ms
            daily.source_counts[source] = daily.source_counts.get(source, 0) + 1
            daily.action_counts[action] = daily.action_counts.get(action, 0) + 1
            if cache_hit:
                daily.cache_hit_count += 1
            else:
                daily.cache_miss_count += 1
        else:
            daily.fail_count += 1
            daily.action_failures[action] = daily.action_failures.get(action, 0) + 1
            daily.cache_miss_count += 1
    
    async def get_metrics(self) -> Dict[str, Any]:
        """获取当前指标"""
        async with self._lock:
            return self._metrics.to_dict()
    
    async def get_daily_metrics(self, date: Optional[str] = None) -> Dict[str, Any]:
        """获取每日指标"""
        async with self._lock:
            if date is None:
                date = datetime.utcnow().strftime("%Y-%m-%d")
            
            if date in self._daily_metrics:
                return self._daily_metrics[date].to_dict()
            return {}
    
    async def get_recent_latencies(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的延迟记录"""
        async with self._lock:
            records = list(self._latency_records)[-limit:]
            return [
                {
                    "timestamp": r.timestamp.isoformat(),
                    "action": r.action,
                    "duration_ms": r.duration_ms,
                    "source": r.source,
                    "success": r.success,
                }
                for r in records
            ]
    
    async def get_latency_percentiles(self, window_minutes: int = 60) -> Dict[str, float]:
        """获取延迟百分位数"""
        async with self._lock:
            cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
            recent = [r.duration_ms for r in self._latency_records if r.timestamp >= cutoff and r.success]
            
            if not recent:
                return {"p50": 0, "p90": 0, "p95": 0, "p99": 0}
            
            recent.sort()
            n = len(recent)
            
            return {
                "p50": recent[int(n * 0.50)] if n > 0 else 0,
                "p90": recent[int(n * 0.90)] if n > 0 else 0,
                "p95": recent[int(n * 0.95)] if n > 0 else 0,
                "p99": recent[int(n * 0.99)] if n > 0 else 0,
                "count": n,
                "window_minutes": window_minutes,
            }
    
    async def reset(self) -> None:
        """重置指标"""
        async with self._lock:
            self._metrics = CollectMetrics()
            self._latency_records.clear()
            self._daily_metrics.clear()
    
    async def persist_to_redis(self) -> None:
        """持久化指标到 Redis"""
        if database.redis_client is None:
            return
        
        async with self._lock:
            date_key = datetime.utcnow().strftime("%Y-%m-%d")
            redis_key = f"{REDIS_KEY_PREFIX['stats']}:{date_key}"
            
            metrics_dict = self._metrics.to_dict()
            
            try:
                await database.redis_client.hset(
                    redis_key,
                    mapping={k: str(v) for k, v in metrics_dict.items() if not isinstance(v, dict)}
                )
                # 设置过期时间为 7 天
                await database.redis_client.expire(redis_key, 7 * 86400)
            except Exception as e:
                import logging
                logging.getLogger("mengla-metrics").warning(f"Failed to persist metrics: {e}")


# ==============================================================================
# 全局指标收集器
# ==============================================================================
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """获取指标收集器（单例）"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


# ==============================================================================
# 便捷函数
# ==============================================================================
async def record_collect_success(
    action: str,
    duration_ms: int,
    source: str,
    cache_hit: bool = False,
) -> None:
    """记录采集成功"""
    collector = get_metrics_collector()
    await collector.record_success(action, duration_ms, source, cache_hit)


async def record_collect_failure(
    action: str,
    duration_ms: int,
    error_type: str = "",
) -> None:
    """记录采集失败"""
    collector = get_metrics_collector()
    await collector.record_failure(action, duration_ms, error_type)


async def get_current_metrics() -> Dict[str, Any]:
    """获取当前指标"""
    collector = get_metrics_collector()
    return await collector.get_metrics()
