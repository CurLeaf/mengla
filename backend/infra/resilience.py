"""
弹性机制模块：重试机制 + 熔断器

提供：
1. 重试装饰器：支持指数退避、可配置重试次数
2. 熔断器：防止级联故障，支持自动恢复
"""
from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple, Type, Union

from ..utils.config import RETRY_CONFIG, CIRCUIT_BREAKER_CONFIG


logger = logging.getLogger("mengla-resilience")


# ==============================================================================
# 重试机制
# ==============================================================================
class RetryError(Exception):
    """重试失败异常"""
    def __init__(self, message: str, attempts: int, last_exception: Optional[Exception] = None):
        super().__init__(message)
        self.attempts = attempts
        self.last_exception = last_exception


def is_retryable_exception(exc: Exception) -> bool:
    """判断异常是否可重试"""
    retryable_types = RETRY_CONFIG.get("retryable_exceptions", ())
    
    # 检查类名
    exc_name = type(exc).__name__
    for retryable in retryable_types:
        if isinstance(retryable, str):
            # 字符串匹配（支持 "httpx.ConnectError" 格式）
            if exc_name == retryable or retryable.endswith(f".{exc_name}"):
                return True
            # 检查完整类路径
            full_name = f"{type(exc).__module__}.{exc_name}"
            if full_name == retryable:
                return True
        elif isinstance(retryable, type) and isinstance(exc, retryable):
            return True
    
    # 默认可重试异常
    if isinstance(exc, (ConnectionError, TimeoutError, asyncio.TimeoutError)):
        return True
    
    return False


def calculate_delay(attempt: int, base_delay: float, max_delay: float, jitter: bool = True) -> float:
    """计算退避延迟时间（指数退避 + 可选抖动）"""
    exponential_base = RETRY_CONFIG.get("exponential_base", 2)
    delay = min(base_delay * (exponential_base ** attempt), max_delay)
    
    if jitter:
        # 添加 ±25% 的随机抖动
        jitter_range = delay * 0.25
        delay = delay + random.uniform(-jitter_range, jitter_range)
    
    return max(0, delay)


async def retry_async(
    func: Callable,
    *args,
    max_attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    jitter: Optional[bool] = None,
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs,
) -> Any:
    """
    异步重试执行函数
    
    Args:
        func: 要执行的异步函数
        max_attempts: 最大重试次数，默认从配置读取
        base_delay: 基础延迟（秒），默认从配置读取
        max_delay: 最大延迟（秒），默认从配置读取
        jitter: 是否添加抖动，默认从配置读取
        on_retry: 重试回调函数，接收 (attempt, exception) 参数
    
    Returns:
        函数执行结果
    
    Raises:
        RetryError: 达到最大重试次数后仍失败
    """
    _max_attempts = max_attempts or RETRY_CONFIG["max_attempts"]
    _base_delay = base_delay or RETRY_CONFIG["base_delay"]
    _max_delay = max_delay or RETRY_CONFIG["max_delay"]
    _jitter = jitter if jitter is not None else RETRY_CONFIG.get("jitter", True)
    
    last_exception: Optional[Exception] = None
    
    for attempt in range(_max_attempts):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            
            if not is_retryable_exception(e):
                logger.warning(
                    "Non-retryable exception: %s (type=%s)",
                    e, type(e).__name__
                )
                raise
            
            if attempt < _max_attempts - 1:
                delay = calculate_delay(attempt, _base_delay, _max_delay, _jitter)
                logger.warning(
                    "Retry attempt %d/%d after %.2fs: %s",
                    attempt + 1, _max_attempts, delay, e
                )
                
                if on_retry:
                    try:
                        on_retry(attempt + 1, e)
                    except Exception:
                        pass
                
                await asyncio.sleep(delay)
    
    raise RetryError(
        f"Failed after {_max_attempts} attempts",
        attempts=_max_attempts,
        last_exception=last_exception,
    )


def with_retry(
    max_attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    jitter: Optional[bool] = None,
):
    """
    重试装饰器
    
    Usage:
        @with_retry(max_attempts=3, base_delay=1.0)
        async def fetch_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(
                func, *args,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                jitter=jitter,
                **kwargs,
            )
        return wrapper
    return decorator


# ==============================================================================
# 熔断器
# ==============================================================================
class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"       # 正常状态，请求通过
    OPEN = "open"           # 熔断状态，请求被拒绝
    HALF_OPEN = "half_open" # 半开状态，允许部分探测请求


class CircuitBreakerError(Exception):
    """熔断器打开异常"""
    def __init__(self, message: str, circuit_name: str, state: CircuitState):
        super().__init__(message)
        self.circuit_name = circuit_name
        self.state = state


class CircuitBreaker:
    """
    熔断器实现
    
    状态流转：
    CLOSED → (连续失败达到阈值) → OPEN → (超时后) → HALF_OPEN → (探测成功) → CLOSED
                                                      ↓ (探测失败)
                                                     OPEN
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: Optional[int] = None,
        success_threshold: Optional[int] = None,
        timeout: Optional[int] = None,
        half_open_max_calls: Optional[int] = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold or CIRCUIT_BREAKER_CONFIG["failure_threshold"]
        self.success_threshold = success_threshold or CIRCUIT_BREAKER_CONFIG["success_threshold"]
        self.timeout = timeout or CIRCUIT_BREAKER_CONFIG["timeout"]
        self.half_open_max_calls = half_open_max_calls or CIRCUIT_BREAKER_CONFIG["half_open_max_calls"]
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitState:
        return self._state
    
    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN
    
    @property
    def is_half_open(self) -> bool:
        return self._state == CircuitState.HALF_OPEN
    
    async def _check_state(self) -> bool:
        """检查并更新状态，返回是否允许请求通过"""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            
            if self._state == CircuitState.OPEN:
                # 检查是否超时，转入半开状态
                if self._last_failure_time is not None:
                    elapsed = time.time() - self._last_failure_time
                    if elapsed >= self.timeout:
                        logger.info(
                            "Circuit %s: OPEN -> HALF_OPEN (timeout elapsed: %.1fs)",
                            self.name, elapsed
                        )
                        self._state = CircuitState.HALF_OPEN
                        self._half_open_calls = 0
                        self._success_count = 0
                        return True
                return False
            
            if self._state == CircuitState.HALF_OPEN:
                # 半开状态，限制探测请求数量
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            
            return True
    
    async def record_success(self) -> None:
        """记录成功"""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    logger.info(
                        "Circuit %s: HALF_OPEN -> CLOSED (success_count=%d)",
                        self.name, self._success_count
                    )
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
            elif self._state == CircuitState.CLOSED:
                # 重置失败计数
                self._failure_count = 0
    
    async def record_failure(self, exception: Optional[Exception] = None) -> None:
        """记录失败"""
        async with self._lock:
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                logger.info(
                    "Circuit %s: HALF_OPEN -> OPEN (probe failed: %s)",
                    self.name, exception
                )
                self._state = CircuitState.OPEN
                self._half_open_calls = 0
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold:
                    logger.warning(
                        "Circuit %s: CLOSED -> OPEN (failure_count=%d)",
                        self.name, self._failure_count
                    )
                    self._state = CircuitState.OPEN
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        通过熔断器执行函数
        
        Args:
            func: 要执行的异步函数
        
        Returns:
            函数执行结果
        
        Raises:
            CircuitBreakerError: 熔断器打开时拒绝请求
        """
        allowed = await self._check_state()
        if not allowed:
            raise CircuitBreakerError(
                f"Circuit {self.name} is {self._state.value}",
                circuit_name=self.name,
                state=self._state,
            )
        
        try:
            result = await func(*args, **kwargs)
            await self.record_success()
            return result
        except Exception as e:
            await self.record_failure(e)
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """获取熔断器统计信息"""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "timeout": self.timeout,
            "last_failure_time": self._last_failure_time,
        }
    
    async def reset(self) -> None:
        """手动重置熔断器"""
        async with self._lock:
            logger.info("Circuit %s: Manual reset to CLOSED", self.name)
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            self._half_open_calls = 0


# ==============================================================================
# 熔断器管理器
# ==============================================================================
class CircuitBreakerManager:
    """熔断器管理器：管理多个熔断器实例"""
    
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()
    
    async def get_or_create(
        self,
        name: str,
        failure_threshold: Optional[int] = None,
        success_threshold: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> CircuitBreaker:
        """获取或创建熔断器"""
        async with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(
                    name=name,
                    failure_threshold=failure_threshold,
                    success_threshold=success_threshold,
                    timeout=timeout,
                )
            return self._breakers[name]
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """获取熔断器（不创建）"""
        return self._breakers.get(name)
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有熔断器统计"""
        return {name: cb.get_stats() for name, cb in self._breakers.items()}
    
    async def reset_all(self) -> None:
        """重置所有熔断器"""
        for cb in self._breakers.values():
            await cb.reset()


# 全局熔断器管理器
_circuit_manager: Optional[CircuitBreakerManager] = None


def get_circuit_manager() -> CircuitBreakerManager:
    """获取熔断器管理器（单例）"""
    global _circuit_manager
    if _circuit_manager is None:
        _circuit_manager = CircuitBreakerManager()
    return _circuit_manager


# ==============================================================================
# 组合装饰器：重试 + 熔断
# ==============================================================================
def with_resilience(
    circuit_name: str,
    max_attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
):
    """
    弹性装饰器：结合重试和熔断
    
    Usage:
        @with_resilience("external_api", max_attempts=3)
        async def call_external_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            manager = get_circuit_manager()
            circuit = await manager.get_or_create(circuit_name)
            
            async def execute():
                return await circuit.call(func, *args, **kwargs)
            
            return await retry_async(
                execute,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
            )
        return wrapper
    return decorator
