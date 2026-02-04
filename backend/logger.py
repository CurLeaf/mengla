"""
结构化日志模块

提供：
1. 统一的日志格式
2. 请求追踪（trace_id）
3. 采集相关的上下文字段
4. JSON 格式输出（便于日志分析）
"""
from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional

import structlog
from structlog.types import EventDict, WrappedLogger


# ==============================================================================
# 上下文变量：请求追踪
# ==============================================================================
_trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_collect_context: ContextVar[Dict[str, Any]] = ContextVar("collect_context", default={})


def get_trace_id() -> Optional[str]:
    """获取当前请求的 trace_id"""
    return _trace_id.get()


def set_trace_id(trace_id: Optional[str] = None) -> str:
    """设置 trace_id，如未提供则自动生成"""
    if trace_id is None:
        trace_id = str(uuid.uuid4())[:8]
    _trace_id.set(trace_id)
    return trace_id


def clear_trace_id() -> None:
    """清除 trace_id"""
    _trace_id.set(None)


def get_collect_context() -> Dict[str, Any]:
    """获取采集上下文"""
    return _collect_context.get()


def set_collect_context(
    action: Optional[str] = None,
    cat_id: Optional[str] = None,
    granularity: Optional[str] = None,
    period_key: Optional[str] = None,
    **extra,
) -> None:
    """设置采集上下文"""
    ctx = {}
    if action:
        ctx["action"] = action
    if cat_id:
        ctx["cat_id"] = cat_id
    if granularity:
        ctx["granularity"] = granularity
    if period_key:
        ctx["period_key"] = period_key
    ctx.update(extra)
    _collect_context.set(ctx)


def clear_collect_context() -> None:
    """清除采集上下文"""
    _collect_context.set({})


# ==============================================================================
# 结构化日志处理器
# ==============================================================================
def add_trace_id(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """添加 trace_id 到日志"""
    trace_id = get_trace_id()
    if trace_id:
        event_dict["trace_id"] = trace_id
    return event_dict


def add_collect_context(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """添加采集上下文到日志"""
    ctx = get_collect_context()
    if ctx:
        event_dict.update(ctx)
    return event_dict


def add_timestamp(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """添加时间戳"""
    event_dict["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return event_dict


def format_exception(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """格式化异常信息"""
    exc_info = event_dict.pop("exc_info", None)
    if exc_info:
        if isinstance(exc_info, tuple):
            event_dict["error_type"] = exc_info[0].__name__ if exc_info[0] else None
            event_dict["error_message"] = str(exc_info[1]) if exc_info[1] else None
        elif isinstance(exc_info, BaseException):
            event_dict["error_type"] = type(exc_info).__name__
            event_dict["error_message"] = str(exc_info)
    return event_dict


# ==============================================================================
# 日志配置
# ==============================================================================
def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    log_file: Optional[str] = None,
) -> None:
    """
    配置结构化日志
    
    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        json_format: 是否使用 JSON 格式输出
        log_file: 日志文件路径（可选）
    """
    # 配置标准日志
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    
    # 配置 structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_timestamp,
        add_trace_id,
        add_collect_context,
        format_exception,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    
    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # 如果指定了日志文件，添加文件处理器
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(getattr(logging, level.upper()))
        if json_format:
            file_handler.setFormatter(logging.Formatter("%(message)s"))
        else:
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
            )
        logging.getLogger().addHandler(file_handler)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """获取结构化日志器"""
    return structlog.get_logger(name)


# ==============================================================================
# 采集日志辅助函数
# ==============================================================================
class CollectLogger:
    """采集操作专用日志器"""
    
    def __init__(self, logger_name: str = "mengla-collect"):
        self._logger = get_logger(logger_name)
    
    def start(
        self,
        action: str,
        cat_id: str,
        granularity: str,
        period_key: str,
        **extra,
    ) -> str:
        """记录采集开始，返回 trace_id"""
        trace_id = set_trace_id()
        set_collect_context(action, cat_id, granularity, period_key, **extra)
        
        self._logger.info(
            "collect_start",
            action=action,
            cat_id=cat_id,
            granularity=granularity,
            period_key=period_key,
            **extra,
        )
        return trace_id
    
    def success(
        self,
        source: str,
        duration_ms: int,
        data_size: Optional[int] = None,
        **extra,
    ) -> None:
        """记录采集成功"""
        self._logger.info(
            "collect_success",
            source=source,
            duration_ms=duration_ms,
            data_size=data_size,
            success=True,
            **extra,
        )
    
    def cache_hit(
        self,
        source: str,
        duration_ms: int,
        **extra,
    ) -> None:
        """记录缓存命中"""
        self._logger.info(
            "cache_hit",
            source=source,
            duration_ms=duration_ms,
            success=True,
            **extra,
        )
    
    def failure(
        self,
        error: Exception,
        duration_ms: int,
        retryable: bool = False,
        **extra,
    ) -> None:
        """记录采集失败"""
        self._logger.error(
            "collect_failure",
            error_type=type(error).__name__,
            error_message=str(error),
            duration_ms=duration_ms,
            success=False,
            retryable=retryable,
            **extra,
        )
    
    def retry(
        self,
        attempt: int,
        max_attempts: int,
        error: Exception,
        delay: float,
        **extra,
    ) -> None:
        """记录重试"""
        self._logger.warning(
            "collect_retry",
            attempt=attempt,
            max_attempts=max_attempts,
            error_type=type(error).__name__,
            error_message=str(error),
            delay_seconds=delay,
            **extra,
        )
    
    def circuit_open(
        self,
        circuit_name: str,
        **extra,
    ) -> None:
        """记录熔断器打开"""
        self._logger.warning(
            "circuit_open",
            circuit_name=circuit_name,
            **extra,
        )
    
    def finish(self) -> None:
        """完成采集，清除上下文"""
        clear_trace_id()
        clear_collect_context()


# 全局采集日志器
_collect_logger: Optional[CollectLogger] = None


def get_collect_logger() -> CollectLogger:
    """获取采集日志器（单例）"""
    global _collect_logger
    if _collect_logger is None:
        _collect_logger = CollectLogger()
    return _collect_logger
