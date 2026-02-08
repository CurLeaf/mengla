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


class MengLaService:
    """萌啦数据采集服务：频控 5s，执行任务后轮询 Redis 等待 webhook 结果"""

    MIN_REQUEST_INTERVAL = 5.0

    def __init__(self) -> None:
        self._last_request_time = 0.0

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
                logger.info("[MengLa] webhook_ok id=%s polls=%s sec=%.1f", execution_id, poll_count, elapsed)
                # 消费后删除 exec key，避免堆积
                try:
                    await database.redis_client.delete(exec_key)
                except Exception:
                    pass
                return json.loads(data)

            if int(elapsed) >= last_log_sec + 30:
                logger.info("[MengLa] polling id=%s polls=%s sec=%.1f", execution_id, poll_count, elapsed)
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

        logger.warning("[MengLa] timeout id=%s polls=%s sec=%s", execution_id, poll_count, timeout_seconds)
        raise TimeoutError(f"查询超时（等待 webhook 超过 {timeout_seconds} 秒）")


_singleton_service: Optional[MengLaService] = None


def get_mengla_service() -> MengLaService:
    global _singleton_service
    if _singleton_service is None:
        _singleton_service = MengLaService()
    return _singleton_service
