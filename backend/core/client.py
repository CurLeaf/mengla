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
    """
    Python 版 MengLaService，参考 mengla-service.ts：
    - 频控：请求间隔至少 5s
    - 第一步获取托管任务列表，找到“萌啦数据采集”任务
    - 第二步执行任务，返回 executionId
    - 轮询 Redis 中以 executionId 为 key 的结果（由 webhook 写入）
    """

    MIN_REQUEST_INTERVAL = 5.0  # seconds

    def __init__(self) -> None:
        self._last_request_time = 0.0

    async def _wait_for_interval(self) -> None:
        now = time.time()
        diff = now - self._last_request_time
        if diff < self.MIN_REQUEST_INTERVAL:
            await asyncio.sleep(self.MIN_REQUEST_INTERVAL - diff)
        self._last_request_time = time.time()

    async def _get_collect_task_id(self) -> str:
        # 采集服务在远端（如 extract.b.nps.qzsyzn.com），本后端只负责把任务推过去
        base_url = os.getenv("COLLECT_SERVICE_URL", "http://localhost:3001")
        api_key = os.getenv("COLLECT_SERVICE_API_KEY", "")
        url = f"{base_url}/api/managed-tasks"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    url,
                    params={"page": 1, "limit": 100},
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
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

        # Webhook URL 优先从环境变量 MENGLA_WEBHOOK_URL 读取；
        # 如果未配置，则退回到 APP_BASEURL + 固定路径。
        webhook_env = os.getenv("MENGLA_WEBHOOK_URL")
        if webhook_env:
            webhook_url = webhook_env.rstrip("/")
        else:
            app_base = os.getenv("APP_BASEURL", "http://localhost:8000")
            webhook_url = f"{app_base.rstrip('/')}/api/webhook/mengla-notify"

        # 月/年/季度/日 均按粒度传：dateType 大写；industryViewV2 季榜用 QUARTERLY_FOR_YEAR；industryTrendRange 的 dateType/timest/starRange/endRange 已由 domain 按颗粒填好，不覆盖
        granularity = normalize_granularity(params.dateType or "day")
        parameters = params.to_request_body()
        if params.action == "industryTrendRange":
            pass  # dateType、timest、starRange、endRange 已由 domain 填好（月 yyyy-MM，季 yyyy-Qn，年 yyyy）
        elif params.action == "industryViewV2" and granularity == "quarter":
            parameters["dateType"] = "QUARTERLY_FOR_YEAR"
        else:
            parameters["dateType"] = granularity.upper()
        if params.action != "industryTrendRange":
            parameters["timest"] = format_for_collect_api(granularity, params.timest)
        # industryViewV2 季榜：starRange/endRange 保持 yyyy-Qn；industryTrendRange：保持颗粒格式（月 yyyy-MM，季 yyyy-Qn，年 yyyy，日 yyyy-MM-dd），不覆盖
        if (params.action == "industryViewV2" and granularity == "quarter") or params.action == "industryTrendRange":
            pass  # 使用 to_request_body() 已填好的 starRange/endRange
        else:
            star_raw = params.starRange or params.timest
            end_raw = params.endRange or params.timest
            # 若前端已传完整日期区间（如 yyyy-MM-dd），则直接使用；否则按粒度计算真实区间
            if star_raw and end_raw and len(star_raw) >= 10 and len(end_raw) >= 10 and "-" in star_raw and "-" in end_raw:
                parameters["starRange"] = star_raw[:10] if len(star_raw) >= 10 else star_raw
                parameters["endRange"] = end_raw[:10] if len(end_raw) >= 10 else end_raw
            else:
                start_d, end_d = period_to_date_range(granularity, params.timest)
                parameters["starRange"] = start_d
                parameters["endRange"] = end_d
        request_body = {
            "parameters": parameters,
            "webhookUrl": webhook_url,
        }

        execute_url = f"{base_url}/api/managed-tasks/{collect_type_id}/execute"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    execute_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    content=json.dumps(request_body, ensure_ascii=False),
                )
        except httpx.ConnectError as e:
            logger.warning("采集服务不可达 %s: %s", execute_url, e)
            raise
        except httpx.TimeoutException as e:
            logger.warning("采集服务请求超时 %s: %s", execute_url, e)
            raise

        if resp.status_code != 200:
            raise RuntimeError(f"采集请求失败: {resp.status_code} {resp.text}")

        try:
            result = resp.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"采集响应 JSON 解析失败: {resp.text[:200]}") from exc

        execution_id = result.get("data", {}).get("executionId")
        if not execution_id:
            raise RuntimeError(f"采集请求失败，未返回 executionId: {result}")

        return execution_id

    async def query(
        self, params: MengLaQueryParams, use_cache: bool = True, timeout_seconds: Optional[int] = None
    ) -> Any:
        # 确保 Redis 已初始化；若未初始化则按环境变量兜底连接一次
        if database.redis_client is None:
            from .infra.database import REDIS_URI_DEFAULT, connect_to_redis

            redis_uri = os.getenv("REDIS_URI", REDIS_URI_DEFAULT)
            await connect_to_redis(redis_uri)

        if database.redis_client is None:
            raise RuntimeError("Redis 未初始化")

        # 统一超时时间：优先用传入值，其次用环境变量 MENGLA_TIMEOUT_SECONDS，最后默认 60 分钟
        if timeout_seconds is None:
            env_timeout = os.getenv("MENGLA_TIMEOUT_SECONDS")
            try:
                timeout_seconds = int(env_timeout) if env_timeout else 60 * 60
            except ValueError:
                timeout_seconds = 60 * 60

        execution_id = await self._request_mengla(params)
        exec_key = f"mengla:exec:{execution_id}"

        # 轮询等待 webhook 写入
        import asyncio

        deadline = time.time() + timeout_seconds
        poll_count = 0
        last_log_sec = 0
        while time.time() < deadline:
            data = await database.redis_client.get(exec_key)
            poll_count += 1
            elapsed = time.time() - (deadline - timeout_seconds)
            if data is not None:
                logger.info(
                    "[MengLa] webhook_ok execution_id=%s poll_count=%s waited_sec=%.1f",
                    execution_id,
                    poll_count,
                    elapsed,
                )
                return json.loads(data)
            if int(elapsed) >= last_log_sec + 10:
                logger.info(
                    "[MengLa] polling execution_id=%s poll_count=%s waited_sec=%.1f",
                    execution_id,
                    poll_count,
                    elapsed,
                )
                last_log_sec = int(elapsed)
            await asyncio.sleep(0.1)

        logger.warning(
            "[MengLa] timeout execution_id=%s poll_count=%s waited_sec=%.1f timeout_sec=%s",
            execution_id,
            poll_count,
            time.time() - (deadline - timeout_seconds),
            timeout_seconds,
        )
        raise TimeoutError(f"查询超时（等待 webhook 超过 {timeout_seconds} 秒）")


_singleton_service: Optional[MengLaService] = None


def get_mengla_service() -> MengLaService:
    global _singleton_service
    if _singleton_service is None:
        _singleton_service = MengLaService()
    return _singleton_service

