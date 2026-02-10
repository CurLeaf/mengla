import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import asyncio

import httpx

from ..infra import database
from ..utils.period import format_for_collect_api, normalize_granularity, period_to_date_range

logger = logging.getLogger(__name__)


def _safe_int_env(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


@dataclass
class MengLaQueryParams:
    action: str
    product_id: str = ""
    catId: str = ""
    dateType: str = ""
    timest: str = ""
    starRange: str = ""
    endRange: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_request_body(self) -> Dict[str, Any]:
        body = {
            "module": self.action,
            "product_id": self.product_id,
            "catId": self.catId,
            "dateType": self.dateType,
            "timest": self.timest,
            "starRange": self.starRange,
            "endRange": self.endRange,
        }
        body.update(self.extra)
        return body


# ==============================================================================
# 全局请求压力指标（供健康监控面板读取）
# ==============================================================================
class RequestPressure:
    """跟踪外部采集系统的请求压力，所有指标线程安全。"""

    def __init__(self) -> None:
        self.max_inflight: int = _safe_int_env("MAX_INFLIGHT_REQUESTS", 1)
        self._inflight: int = 0
        self._waiting: int = 0  # 等待获取信号量的任务数
        self._total_sent: int = 0
        self._total_completed: int = 0
        self._total_timeout: int = 0
        self._total_error: int = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """请求进入排队，获取到 slot 后才能发送请求"""
        async with self._lock:
            self._waiting += 1
        try:
            await self._semaphore.acquire()
        finally:
            async with self._lock:
                self._waiting -= 1
                self._inflight += 1
                self._total_sent += 1

    async def release(self, *, timeout: bool = False, error: bool = False) -> None:
        """请求完成（成功/超时/错误），释放 slot"""
        async with self._lock:
            self._inflight = max(0, self._inflight - 1)
            self._total_completed += 1
            if timeout:
                self._total_timeout += 1
            if error:
                self._total_error += 1
        self._semaphore.release()

    @property
    def _semaphore(self) -> asyncio.Semaphore:
        # 惰性创建（必须在事件循环中）
        if not hasattr(self, "_sem"):
            self._sem = asyncio.Semaphore(self.max_inflight)
        return self._sem

    def snapshot(self) -> Dict[str, Any]:
        """返回当前压力快照（无锁读取，dashboard 用）"""
        return {
            "max_inflight": self.max_inflight,
            "inflight": self._inflight,
            "waiting": self._waiting,
            "total_sent": self._total_sent,
            "total_completed": self._total_completed,
            "total_timeout": self._total_timeout,
            "total_error": self._total_error,
        }


# 全局单例
_request_pressure: Optional[RequestPressure] = None


def get_request_pressure() -> RequestPressure:
    global _request_pressure
    if _request_pressure is None:
        _request_pressure = RequestPressure()
    return _request_pressure


class MengLaService:
    """
    萌啦数据采集服务

    外部采集系统是串行的（一次只能处理一个请求），限流策略（三层保护）：
    1. MIN_REQUEST_INTERVAL = 5s  — 两次 HTTP 请求之间至少间隔 5 秒
    2. MAX_INFLIGHT（全局信号量）— 同时等待 webhook 结果的请求数上限（默认 1，串行）
       上一个请求拿到 webhook 结果后，才会发送下一个请求
    3. 渐进退避轮询              — webhook 等待期间逐步放缓轮询频率
    """

    MIN_REQUEST_INTERVAL = 5.0

    def __init__(self) -> None:
        self._last_request_time = 0.0
        self._pressure = get_request_pressure()

    async def _wait_for_interval(self) -> None:
        now = time.time()
        diff = now - self._last_request_time
        if diff < self.MIN_REQUEST_INTERVAL:
            await asyncio.sleep(self.MIN_REQUEST_INTERVAL - diff)
        self._last_request_time = time.time()

    async def _get_collect_task_id(self) -> str:
        base_url = os.getenv("COLLECT_SERVICE_URL", "http://localhost:3001")
        api_key = os.getenv("COLLECT_SERVICE_API_KEY", "")
        url = f"{base_url}/api/managed-tasks"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params={"page": 1, "limit": 100}, headers=headers)
        except httpx.ConnectError as e:
            logger.warning("采集服务不可达 %s: %s", url, e)
            raise
        except httpx.TimeoutException as e:
            logger.warning("采集服务请求超时 %s: %s", url, e)
            raise

        if resp.status_code != 200:
            raise RuntimeError(f"获取托管任务列表失败: {resp.status_code} {resp.text}")

        data = resp.json()
        tasks = data.get("data", {}).get("tasks", [])

        for task in tasks:
            if task.get("name") == "萌啦数据采集":
                task_id = task.get("id")
                if task_id:
                    return task_id

        available_names = ", ".join(t.get("name", "?") for t in tasks)
        raise RuntimeError(f'未找到"萌啦数据采集"任务，可用任务: {available_names}')

    async def _request_mengla(self, params: MengLaQueryParams) -> str:
        await self._wait_for_interval()
        collect_type_id = await self._get_collect_task_id()

        base_url = os.getenv("COLLECT_SERVICE_URL", "http://localhost:3001")
        api_key = os.getenv("COLLECT_SERVICE_API_KEY", "")

        webhook_env = os.getenv("MENGLA_WEBHOOK_URL")
        if webhook_env:
            webhook_url = webhook_env.rstrip("/")
        else:
            app_base = os.getenv("APP_BASEURL", "http://localhost:8000")
            webhook_url = f"{app_base.rstrip('/')}/api/webhook/mengla-notify"

        granularity = normalize_granularity(params.dateType or "day")
        parameters = params.to_request_body()

        if params.action == "industryTrendRange":
            pass
        elif granularity == "quarter":
            # 季度统一使用 QUARTERLY_FOR_YEAR
            parameters["dateType"] = "QUARTERLY_FOR_YEAR"
        else:
            parameters["dateType"] = granularity.upper()

        if params.action != "industryTrendRange":
            parameters["timest"] = format_for_collect_api(granularity, params.timest)

        if (params.action == "industryViewV2" and granularity == "quarter") or params.action == "industryTrendRange":
            pass
        else:
            star_raw = params.starRange or params.timest
            end_raw = params.endRange or params.timest
            if star_raw and end_raw and len(star_raw) >= 10 and len(end_raw) >= 10 and "-" in star_raw and "-" in end_raw:
                parameters["starRange"] = star_raw[:10]
                parameters["endRange"] = end_raw[:10]
            else:
                start_d, end_d = period_to_date_range(granularity, params.timest)
                parameters["starRange"] = start_d
                parameters["endRange"] = end_d

        request_body = {"parameters": parameters, "webhookUrl": webhook_url}
        execute_url = f"{base_url}/api/managed-tasks/{collect_type_id}/execute"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        logger.info("[MengLa] execute url=%s params=%s", execute_url, json.dumps(parameters, ensure_ascii=False)[:200])

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(execute_url, headers=headers, content=json.dumps(request_body, ensure_ascii=False))
        except httpx.ConnectError as e:
            logger.warning("采集服务不可达 %s: %s", execute_url, e)
            raise
        except httpx.TimeoutException as e:
            logger.warning("采集服务请求超时 %s: %s", execute_url, e)
            raise

        if resp.status_code != 200:
            logger.error("[MengLa] request failed: %s %s", resp.status_code, resp.text[:200])
            raise RuntimeError(f"采集请求失败: {resp.status_code} {resp.text}")

        try:
            result = resp.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"采集响应 JSON 解析失败: {resp.text[:200]}") from exc

        execution_id = result.get("data", {}).get("executionId")
        if not execution_id:
            raise RuntimeError(f"采集请求失败，未返回 executionId: {result}")

        logger.info("[MengLa] got executionId=%s", execution_id)
        return execution_id

    async def query(
        self, params: MengLaQueryParams, use_cache: bool = True, timeout_seconds: Optional[int] = None
    ) -> Any:
        if database.redis_client is None:
            from ..infra.database import REDIS_URI_DEFAULT, connect_to_redis
            redis_uri = os.getenv("REDIS_URI", REDIS_URI_DEFAULT)
            await connect_to_redis(redis_uri)

        if database.redis_client is None:
            raise RuntimeError("Redis 未初始化")

        if timeout_seconds is None:
            env_timeout = os.getenv("MENGLA_TIMEOUT_SECONDS")
            try:
                timeout_seconds = int(env_timeout) if env_timeout else 300  # 默认 5 分钟
            except ValueError:
                timeout_seconds = 300

        pressure = self._pressure
        snap = pressure.snapshot()
        if snap["waiting"] > 0:
            logger.info(
                "[MengLa] queued — inflight=%d/%d waiting=%d action=%s",
                snap["inflight"], snap["max_inflight"], snap["waiting"], params.action,
            )

        # 全局信号量：限制同时在外部采集系统的 in-flight 请求数
        await pressure.acquire()
        is_timeout = False
        is_error = False
        try:
            execution_id = await self._request_mengla(params)
            exec_key = f"mengla:exec:{execution_id}"

            deadline = time.time() + timeout_seconds
            start_time = time.time()
            poll_count = 0
            last_log_sec = 0

            while time.time() < deadline:
                data = await database.redis_client.get(exec_key)
                poll_count += 1
                elapsed = time.time() - start_time

                if data is not None:
                    parsed = json.loads(data)
                    # 防御：如果 Redis 中残留了 running 状态的心跳数据，跳过继续等待
                    if isinstance(parsed, dict) and parsed.get("status") in ("running", "sync", "pending", "queued"):
                        if poll_count == 1 or int(elapsed) >= last_log_sec + 30:
                            logger.info(
                                "[MengLa] polling skip stale status=%s id=%s",
                                parsed.get("status"), execution_id,
                            )
                        # 删除脏数据，继续等待真正的结果
                        try:
                            await database.redis_client.delete(exec_key)
                        except Exception:
                            pass
                    else:
                        logger.info("[MengLa] webhook_ok id=%s polls=%s sec=%.1f", execution_id, poll_count, elapsed)
                        # 消费后删除 exec key，避免堆积
                        try:
                            await database.redis_client.delete(exec_key)
                        except Exception:
                            pass
                        return parsed

                if int(elapsed) >= last_log_sec + 30:
                    logger.info(
                        "[MengLa] polling id=%s polls=%s sec=%.1f inflight=%d/%d",
                        execution_id, poll_count, elapsed,
                        pressure._inflight, pressure.max_inflight,
                    )
                    last_log_sec = int(elapsed)

                # 渐进退避：前 30s 快速轮询，之后逐步放缓
                if elapsed < 30:
                    await asyncio.sleep(0.1)     # 前 30 秒: 100ms（webhook 通常 30s 内返回）
                elif elapsed < 120:
                    await asyncio.sleep(1.0)     # 30s-2min: 1 秒
                elif elapsed < 300:
                    await asyncio.sleep(5.0)     # 2-5min: 5 秒
                else:
                    await asyncio.sleep(10.0)    # 5min+: 10 秒

            is_timeout = True
            logger.warning("[MengLa] timeout id=%s polls=%s sec=%s", execution_id, poll_count, timeout_seconds)
            raise TimeoutError(f"查询超时（等待 webhook 超过 {timeout_seconds} 秒）")

        except TimeoutError:
            raise
        except Exception:
            is_error = True
            raise
        finally:
            await pressure.release(timeout=is_timeout, error=is_error)


_singleton_service: Optional[MengLaService] = None


def get_mengla_service() -> MengLaService:
    global _singleton_service
    if _singleton_service is None:
        _singleton_service = MengLaService()
    return _singleton_service
