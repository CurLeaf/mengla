"""
配置中心：集中管理所有配置项
支持从环境变量读取，无需重启即可热更新部分配置
"""
from __future__ import annotations

import logging
import os
from typing import Dict, Any
from datetime import timedelta

_config_logger = logging.getLogger("mengla-config")


def _safe_int(key: str, default: int) -> int:
    """安全地将环境变量解析为 int，解析失败时返回默认值并记录警告。"""
    raw = os.getenv(key, str(default))
    try:
        return int(raw)
    except (ValueError, TypeError):
        _config_logger.warning("Invalid int for env %s=%r, using default %d", key, raw, default)
        return default


def _safe_float(key: str, default: float) -> float:
    """安全地将环境变量解析为 float，解析失败时返回默认值并记录警告。"""
    raw = os.getenv(key, str(default))
    try:
        return float(raw)
    except (ValueError, TypeError):
        _config_logger.warning("Invalid float for env %s=%r, using default %s", key, raw, default)
        return default


# ==============================================================================
# 调度器配置
# ==============================================================================
SCHEDULER_CONFIG = {
    "timezone": "Asia/Shanghai",
    "collect_window": {
        "start": os.getenv("COLLECT_WINDOW_START", "00:30"),
        "end": os.getenv("COLLECT_WINDOW_END", "05:00"),
    },
    "concurrency": _safe_int("COLLECT_CONCURRENCY", 5),
    "retry_times": _safe_int("COLLECT_RETRY_TIMES", 3),
}

# 定时任务配置（支持通过环境变量 CRON_<JOB_ID> 覆盖 cron 表达式）
# 格式：标准 5 段 cron "minute hour day month day_of_week"
CRON_JOBS = {
    "daily_collect": {
        "cron": os.getenv("CRON_DAILY_COLLECT", "0 4 * * *"),  # 默认每日 04:00
        "description": "每日主采集（day 颗粒度）",
    },
    "monthly_collect": {
        "cron": os.getenv("CRON_MONTHLY_COLLECT", "0 5 3 * *"),  # 默认每月3日 05:00
        "description": "月度采集（month 颗粒度）",
    },
    "quarterly_collect": {
        "cron": os.getenv("CRON_QUARTERLY_COLLECT", "0 6 10 1,4,7,10 *"),  # 默认季后10日 06:00
        "description": "季度采集（quarter 颗粒度）",
    },
    "yearly_collect": {
        "cron": os.getenv("CRON_YEARLY_COLLECT", "0 7 20 1 *"),  # 默认1月20日 07:00
        "description": "年度采集（year 颗粒度）",
    },
    "backfill_check": {
        "cron": os.getenv("CRON_BACKFILL_CHECK", "0 */4 * * *"),  # 默认每4小时
        "description": "补数检查",
    },
}


def parse_cron_expr(cron_str: str) -> Dict[str, str]:
    """
    解析标准 5 段 cron 表达式为 APScheduler 的 cron trigger 参数。
    格式: "minute hour day month day_of_week"
    返回: {"minute": ..., "hour": ..., "day": ..., "month": ..., "day_of_week": ...}
    """
    parts = cron_str.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression (expected 5 fields): {cron_str}")
    return {
        "minute": parts[0],
        "hour": parts[1],
        "day": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }


# ==============================================================================
# 缓存 TTL 配置（秒）
# ==============================================================================
CACHE_TTL: Dict[str, int] = {
    "day": 4 * 3600,        # 4小时
    "month": 24 * 3600,     # 24小时
    "quarter": 7 * 86400,   # 7天
    "year": 30 * 86400,     # 30天
}

# Redis 缓存 TTL（与上面保持一致，用于 Redis 操作）
REDIS_TTL = CACHE_TTL.copy()

# L1 本地缓存配置
L1_CACHE_CONFIG = {
    "max_size": _safe_int("L1_CACHE_MAX_SIZE", 1000),
    "ttl": _safe_int("L1_CACHE_TTL", 300),  # 5分钟
}


# ==============================================================================
# MongoDB 数据保留策略（秒）
# ==============================================================================
DATA_RETENTION: Dict[str, int] = {
    "day": 30 * 86400,      # 30天
    "month": 90 * 86400,    # 90天
    "quarter": 365 * 86400, # 1年
    "year": 730 * 86400,    # 2年
}


# ==============================================================================
# 重试机制配置
# ==============================================================================
RETRY_CONFIG = {
    "max_attempts": _safe_int("RETRY_MAX_ATTEMPTS", 3),
    "base_delay": _safe_float("RETRY_BASE_DELAY", 1.0),  # 秒
    "max_delay": _safe_float("RETRY_MAX_DELAY", 60.0),   # 秒
    "exponential_base": 2,
    "jitter": True,  # 添加随机抖动
    "retryable_exceptions": (
        "ConnectionError",
        "TimeoutError",
        "httpx.ConnectError",
        "httpx.ReadTimeout",
    ),
}


# ==============================================================================
# 熔断器配置
# ==============================================================================
CIRCUIT_BREAKER_CONFIG = {
    "failure_threshold": _safe_int("CB_FAILURE_THRESHOLD", 5),   # 触发熔断的连续失败次数
    "success_threshold": _safe_int("CB_SUCCESS_THRESHOLD", 3),   # 恢复所需的连续成功次数
    "timeout": _safe_int("CB_TIMEOUT", 60),                      # 熔断超时（秒）
    "half_open_max_calls": _safe_int("CB_HALF_OPEN_CALLS", 3),   # 半开状态最大探测次数
}


# ==============================================================================
# 并发采集配置
# ==============================================================================
CONCURRENT_CONFIG = {
    "max_concurrent": _safe_int("MAX_CONCURRENT_TASKS", 5),
    "max_inflight": _safe_int("MAX_INFLIGHT_REQUESTS", 1),  # 外部采集系统是串行的，默认 1 个
    "task_timeout": _safe_int("TASK_TIMEOUT", 300),  # 5分钟
    "batch_size": _safe_int("BATCH_SIZE", 10),
}


# ==============================================================================
# 监控告警配置
# ==============================================================================
ALERTING_CONFIG = {
    "rules": [
        {
            "name": "low_success_rate",
            "threshold": 0.95,  # 95%
            "level": "WARNING",
            "cooldown": 600,    # 10分钟
            "description": "采集成功率低于95%",
        },
        {
            "name": "critical_success_rate",
            "threshold": 0.80,  # 80%
            "level": "CRITICAL",
            "cooldown": 300,    # 5分钟
            "description": "采集成功率低于80%",
        },
        {
            "name": "high_latency",
            "threshold": 30.0,  # 30秒
            "level": "WARNING",
            "cooldown": 600,    # 10分钟
            "description": "平均采集延迟超过30秒",
        },
        {
            "name": "low_cache_hit_rate",
            "threshold": 0.50,  # 50%
            "level": "INFO",
            "cooldown": 1800,   # 30分钟
            "description": "缓存命中率低于50%",
        },
    ],
}


# ==============================================================================
# 数据库配置
# ==============================================================================
DB_CONFIG = {
    "mongo_uri": os.getenv("MONGO_URI", "mongodb://localhost:27017"),
    "mongo_db": os.getenv("MONGO_DB", "industry_monitor"),
    "redis_uri": os.getenv("REDIS_URI", "redis://localhost:6379/0"),
}


# ==============================================================================
# 统一集合名称
# ==============================================================================
COLLECTION_NAME = "mengla_data"

# Action 名称映射
ACTION_MAPPING = {
    "high": "high",
    "hot": "hot",
    "chance": "chance",
    "industryViewV2": "view",
    "industryTrendRange": "trend",
}


# ==============================================================================
# Redis Key 前缀
# ==============================================================================
REDIS_KEY_PREFIX = {
    "data": "mengla:data",           # 数据缓存
    "lock": "mengla:lock",           # 分布式锁
    "task_queue": "mengla:task_queue",  # 任务队列
    "stats": "mengla:stats",         # 采集统计
    "circuit": "mengla:circuit",     # 熔断状态
    "rate": "mengla:rate",           # 频控计数
    "empty_streak": "mengla:empty_streak",  # 连续空数据计数
    "exec": "mengla:exec",          # 执行结果（webhook 回调）
}


# ==============================================================================
# 辅助函数
# ==============================================================================
def get_cache_ttl(granularity: str) -> int:
    """获取指定颗粒度的缓存 TTL（秒）"""
    return CACHE_TTL.get(granularity.lower(), CACHE_TTL["day"])


def get_retention_ttl(granularity: str) -> int:
    """获取指定颗粒度的数据保留时间（秒）"""
    return DATA_RETENTION.get(granularity.lower(), DATA_RETENTION["day"])


def get_expired_at(granularity: str) -> "datetime":
    """计算指定颗粒度数据的过期时间"""
    from datetime import datetime, timedelta
    retention_seconds = get_retention_ttl(granularity)
    return datetime.utcnow() + timedelta(seconds=retention_seconds)


def build_redis_data_key(action: str, cat_id: str, granularity: str, period_key: str) -> str:
    """构建 Redis 数据缓存 key"""
    prefix = REDIS_KEY_PREFIX["data"]
    return f"{prefix}:{action}:{cat_id or 'all'}:{granularity}:{period_key}"


def build_redis_lock_key(action: str, cat_id: str, granularity: str, period_key: str) -> str:
    """构建 Redis 分布式锁 key"""
    prefix = REDIS_KEY_PREFIX["lock"]
    return f"{prefix}:{action}:{cat_id or 'all'}:{granularity}:{period_key}"


# ==============================================================================
# 采集间隔配置
# ==============================================================================
def get_collect_interval() -> float:
    """采集请求间隔（秒），可通过环境变量 COLLECT_INTERVAL_SECONDS 调整"""
    return _safe_float("COLLECT_INTERVAL_SECONDS", 2.0)


# ==============================================================================
# 启动时环境变量校验
# ==============================================================================
def validate_env() -> None:
    """
    启动时校验关键环境变量。
    若缺少必要变量则记录警告（不中断启动，兼容本地开发场景——
    本地 .env 或 docker-compose 会提供默认值）。
    """
    import logging
    _logger = logging.getLogger("mengla-config")
    recommended = ["MONGO_URI", "REDIS_URI"]
    missing = [k for k in recommended if not os.getenv(k)]
    if missing:
        _logger.warning(
            "Recommended env vars not set (will use defaults): %s",
            ", ".join(missing),
        )
