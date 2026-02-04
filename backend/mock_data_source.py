"""
模拟数据源服务

模拟外部采集服务的行为：
1. 提供托管任务列表 API
2. 提供执行任务 API（返回 executionId）
3. 串行处理请求，模拟采集延迟
4. 通过 webhook 回传数据
5. 提供处理状态查看 API

启动方式：
    cd backend
    python -m mock_data_source

或者：
    uvicorn backend.mock_data_source:app --host 0.0.0.0 --port 3001 --reload
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mock-data-source")

app = FastAPI(title="Mock Data Source", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# 任务状态管理
# ==============================================================================
class TaskStatus(Enum):
    PENDING = "pending"      # 等待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"        # 失败


@dataclass
class TaskRecord:
    """任务记录"""
    execution_id: str
    action: str
    params: Dict[str, Any]
    webhook_url: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0  # 0-100
    message: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "action": self.action,
            "params": self.params,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


# 全局任务队列和记录
task_queue: Deque[TaskRecord] = deque()
task_records: Dict[str, TaskRecord] = {}
processing_lock = asyncio.Lock()
is_worker_running = False


# ==============================================================================
# Mock 数据生成
# ==============================================================================
def generate_mock_high_data(action: str, cat_id: str, count: int = 20) -> Dict[str, Any]:
    """生成蓝海/热销/潜力数据"""
    list_key = f"{action}List"
    
    items = []
    for i in range(count):
        item = {
            "catId1": str(100000 + i),
            "catId2": str(200000 + i) if random.random() > 0.3 else None,
            "catId3": str(300000 + i) if random.random() > 0.5 else None,
            "catName": f"Category_{i}_{action}",
            "catNameCn": f"类目_{i}_{action}",
            "catTag": random.randint(1, 5),
            "skuNum": random.randint(100, 10000),
            "saleSkuNum": random.randint(50, 5000),
            "saleRatio": round(random.uniform(0.1, 0.9), 4),
            "monthSales": round(random.uniform(1000, 100000), 2),
            "monthSalesRating": round(random.uniform(0.01, 0.1), 4),
            "monthSalesDynamics": round(random.uniform(-0.5, 0.5), 4),
            "monthGmv": round(random.uniform(10000, 1000000), 2),
            "monthGmvRmb": round(random.uniform(100000, 10000000), 2),
            "monthGmvRating": round(random.uniform(0.01, 0.1), 4),
            "monthGmvDynamics": round(random.uniform(-0.5, 0.5), 4),
            "brandGmv": round(random.uniform(1000, 100000), 2),
            "brandGmvRmb": round(random.uniform(10000, 1000000), 2),
            "brandGmvRating": round(random.uniform(0.01, 0.3), 4),
            "topGmv": round(random.uniform(5000, 500000), 2),
            "topGmvRating": round(random.uniform(0.05, 0.5), 4),
            "topAvgPrice": round(random.uniform(10, 1000), 2),
            "topAvgPriceRmb": round(random.uniform(100, 10000), 2),
        }
        items.append(item)
    
    return {
        list_key: {
            "code": 0,
            "data": {
                "list": items,
                "pageNo": 1,
                "pageSize": count,
                "total": count,
            }
        }
    }


def generate_mock_view_data(cat_id: str) -> Dict[str, Any]:
    """生成行业视图数据"""
    # 销量区间
    sales_ranges = []
    for i, title in enumerate(["0-10", "10-50", "50-100", "100-500", "500+"]):
        sales_ranges.append({
            "id": str(i + 1),
            "title": title,
            "itemCount": random.randint(100, 5000),
            "sales": round(random.uniform(1000, 50000), 2),
            "gmv": round(random.uniform(10000, 500000), 2),
            "itemCountRate": round(random.uniform(0.1, 0.3), 4),
            "salesRate": round(random.uniform(0.1, 0.3), 4),
            "gmvRate": round(random.uniform(0.1, 0.3), 4),
        })
    
    # GMV 区间
    gmv_ranges = []
    for i, title in enumerate(["0-1K", "1K-5K", "5K-10K", "10K-50K", "50K+"]):
        gmv_ranges.append({
            "id": str(i + 1),
            "title": title,
            "itemCount": random.randint(100, 5000),
            "sales": round(random.uniform(1000, 50000), 2),
            "gmv": round(random.uniform(10000, 500000), 2),
            "itemCountRate": round(random.uniform(0.1, 0.3), 4),
            "salesRate": round(random.uniform(0.1, 0.3), 4),
            "gmvRate": round(random.uniform(0.1, 0.3), 4),
        })
    
    # 价格区间
    price_ranges = []
    for i, title in enumerate(["0-50", "50-100", "100-200", "200-500", "500+"]):
        price_ranges.append({
            "id": str(i + 1),
            "title": title,
            "itemCount": random.randint(100, 5000),
            "sales": round(random.uniform(1000, 50000), 2),
            "gmv": round(random.uniform(10000, 500000), 2),
            "itemCountRate": round(random.uniform(0.1, 0.3), 4),
            "salesRate": round(random.uniform(0.1, 0.3), 4),
            "gmvRate": round(random.uniform(0.1, 0.3), 4),
        })
    
    # 品牌占比
    brand_rates = []
    for i in range(5):
        brand_rates.append({
            "catId": str(100000 + i),
            "catName": f"SubCategory_{i}",
            "catNameCn": f"子类目_{i}",
            "brandGmv": round(random.uniform(10000, 100000), 2),
            "brandGmvRate": round(random.uniform(0.05, 0.3), 4),
            "brandItemCount": random.randint(10, 500),
            "brandItemCountRate": round(random.uniform(0.05, 0.3), 4),
            "brandSales": round(random.uniform(1000, 10000), 2),
            "brandSalesRate": round(random.uniform(0.05, 0.3), 4),
            "typeId": str(i + 1),
        })
    
    return {
        "industryViewV2List": {
            "code": 0,
            "data": {
                "industrySalesRangeDtoList": sales_ranges,
                "industryGmvRangeDtoList": gmv_ranges,
                "industryPriceRangeDtoList": price_ranges,
                "industryBrandRateDtoList": brand_rates,
            }
        }
    }


def generate_mock_trend_data(granularity: str, start_range: str, end_range: str) -> Dict[str, Any]:
    """生成行业趋势数据"""
    from datetime import datetime, timedelta
    
    points = []
    
    # 根据颗粒度生成时间点
    try:
        if granularity.upper() == "DAY":
            # 生成每日数据点
            start = datetime.strptime(start_range[:10], "%Y-%m-%d")
            end = datetime.strptime(end_range[:10], "%Y-%m-%d")
            current = start
            while current <= end:
                points.append(current.strftime("%Y-%m-%d"))
                current += timedelta(days=1)
        elif granularity.upper() == "MONTH":
            # 生成每月数据点
            year = int(start_range[:4])
            month = int(start_range[5:7]) if len(start_range) > 5 else 1
            end_year = int(end_range[:4])
            end_month = int(end_range[5:7]) if len(end_range) > 5 else 12
            while (year, month) <= (end_year, end_month):
                points.append(f"{year}-{month:02d}")
                month += 1
                if month > 12:
                    month = 1
                    year += 1
        elif granularity.upper() in ("QUARTER", "QUARTERLY_FOR_YEAR"):
            # 生成季度数据点
            year = int(start_range[:4])
            for q in range(1, 5):
                points.append(f"{year}-Q{q}")
        else:
            # 年度
            year = int(start_range[:4])
            points.append(str(year))
    except Exception:
        # 默认生成一些数据点
        points = [f"2026-{i:02d}" for i in range(1, 13)]
    
    trend_data = []
    base_sales = random.uniform(10000, 100000)
    base_gmv = random.uniform(100000, 1000000)
    
    for i, timest in enumerate(points[:30]):  # 最多30个点
        # 添加一些趋势变化
        factor = 1 + (i * 0.02) + random.uniform(-0.1, 0.1)
        trend_data.append({
            "timest": timest,
            "salesSkuCount": int(random.uniform(500, 5000) * factor),
            "salesSkuRatio": round(random.uniform(0.1, 0.5), 4),
            "monthSales": round(base_sales * factor, 2),
            "monthSalesRatio": round(random.uniform(-0.2, 0.3), 4),
            "monthGmv": round(base_gmv * factor, 2),
            "monthGmvRatio": round(random.uniform(-0.2, 0.3), 4),
            "currentDayPrice": round(random.uniform(50, 500), 2),
        })
    
    return {
        "industryTrendRange": {
            "code": 0,
            "data": trend_data,
        }
    }


def generate_mock_data(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """根据 action 生成对应的 mock 数据"""
    cat_id = params.get("catId", "")
    
    if action in ("high", "hot", "chance"):
        return generate_mock_high_data(action, cat_id)
    elif action == "industryViewV2":
        return generate_mock_view_data(cat_id)
    elif action == "industryTrendRange":
        granularity = params.get("dateType", "DAY")
        start_range = params.get("starRange", "2026-01-01")
        end_range = params.get("endRange", "2026-12-31")
        return generate_mock_trend_data(granularity, start_range, end_range)
    else:
        return {"error": f"Unknown action: {action}"}


# ==============================================================================
# 任务处理 Worker
# ==============================================================================
async def process_task(task: TaskRecord) -> None:
    """处理单个任务"""
    task.status = TaskStatus.PROCESSING
    task.started_at = datetime.utcnow()
    task.progress = 0
    task.message = "开始处理..."
    
    logger.info(
        "开始处理任务: execution_id=%s action=%s",
        task.execution_id, task.action
    )
    
    try:
        # 模拟处理步骤
        steps = [
            (10, "正在连接数据源..."),
            (20, "正在验证参数..."),
            (30, "正在查询数据..."),
            (50, "正在解析响应..."),
            (70, "正在处理数据..."),
            (90, "正在生成结果..."),
        ]
        
        for progress, message in steps:
            task.progress = progress
            task.message = message
            logger.info(
                "任务进度: execution_id=%s progress=%d%% message=%s",
                task.execution_id, progress, message
            )
            # 随机延迟 1-3 秒，模拟真实处理
            await asyncio.sleep(random.uniform(1.0, 3.0))
        
        # 生成 mock 数据
        task.progress = 95
        task.message = "正在准备回调..."
        result_data = generate_mock_data(task.action, task.params)
        task.result = result_data
        
        # 调用 webhook 回传数据
        task.progress = 98
        task.message = "正在回调..."
        
        webhook_payload = {
            "executionId": task.execution_id,
            "resultData": result_data,
            "status": "success",
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                task.webhook_url,
                json=webhook_payload,
            )
            if resp.status_code == 200:
                logger.info(
                    "Webhook 回调成功: execution_id=%s webhook_url=%s",
                    task.execution_id, task.webhook_url
                )
            else:
                logger.warning(
                    "Webhook 回调失败: execution_id=%s status=%d",
                    task.execution_id, resp.status_code
                )
        
        task.progress = 100
        task.status = TaskStatus.COMPLETED
        task.message = "处理完成"
        task.completed_at = datetime.utcnow()
        
        logger.info(
            "任务完成: execution_id=%s action=%s 耗时=%.1f秒",
            task.execution_id, task.action,
            (task.completed_at - task.started_at).total_seconds()
        )
        
    except Exception as e:
        task.status = TaskStatus.FAILED
        task.error = str(e)
        task.message = f"处理失败: {e}"
        task.completed_at = datetime.utcnow()
        logger.error(
            "任务失败: execution_id=%s error=%s",
            task.execution_id, e
        )


async def task_worker() -> None:
    """任务处理 Worker（串行处理）"""
    global is_worker_running
    
    if is_worker_running:
        return
    
    is_worker_running = True
    logger.info("任务 Worker 启动")
    
    try:
        while True:
            # 检查队列
            task = None
            async with processing_lock:
                if task_queue:
                    task = task_queue.popleft()
            
            if task:
                await process_task(task)
            else:
                # 队列为空，等待
                await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        logger.info("任务 Worker 停止")
    finally:
        is_worker_running = False


# ==============================================================================
# API 端点
# ==============================================================================
@app.on_event("startup")
async def startup():
    """启动时启动 Worker"""
    asyncio.create_task(task_worker())
    logger.info("Mock 数据源服务启动")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-data-source"}


@app.get("/api/managed-tasks")
async def get_managed_tasks():
    """返回托管任务列表"""
    return {
        "code": 0,
        "data": {
            "tasks": [
                {
                    "id": "mock-mengla-task-001",
                    "name": "萌啦数据采集",
                    "description": "模拟萌啦数据采集任务",
                    "status": "active",
                }
            ],
            "total": 1,
        }
    }


class ExecuteTaskRequest(BaseModel):
    parameters: Dict[str, Any]
    webhookUrl: str


@app.post("/api/managed-tasks/{task_id}/execute")
async def execute_task(task_id: str, body: ExecuteTaskRequest):
    """执行采集任务"""
    execution_id = str(uuid.uuid4())
    
    # 获取 action
    action = body.parameters.get("module", "unknown")
    
    # 创建任务记录
    task = TaskRecord(
        execution_id=execution_id,
        action=action,
        params=body.parameters,
        webhook_url=body.webhookUrl,
    )
    
    # 添加到队列
    async with processing_lock:
        task_queue.append(task)
        task_records[execution_id] = task
    
    logger.info(
        "任务已入队: execution_id=%s action=%s webhook=%s queue_size=%d",
        execution_id, action, body.webhookUrl, len(task_queue)
    )
    
    return {
        "code": 0,
        "data": {
            "executionId": execution_id,
            "message": "任务已提交",
        }
    }


# ==============================================================================
# 状态查看 API（供前端使用）
# ==============================================================================
@app.get("/api/status/queue")
async def get_queue_status():
    """获取队列状态"""
    async with processing_lock:
        queue_list = [t.to_dict() for t in task_queue]
    
    # 获取最近的任务
    recent = sorted(
        task_records.values(),
        key=lambda t: t.created_at,
        reverse=True
    )[:20]
    
    return {
        "queue_size": len(task_queue),
        "queue": queue_list,
        "recent_tasks": [t.to_dict() for t in recent],
        "worker_running": is_worker_running,
    }


@app.get("/api/status/task/{execution_id}")
async def get_task_status(execution_id: str):
    """获取单个任务状态"""
    if execution_id not in task_records:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = task_records[execution_id]
    return task.to_dict()


@app.get("/api/status/processing")
async def get_processing_status():
    """获取当前处理状态（供前端实时显示）"""
    # 找到正在处理的任务
    processing = None
    for task in task_records.values():
        if task.status == TaskStatus.PROCESSING:
            processing = task
            break
    
    # 统计
    stats = {
        "pending": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
    }
    for task in task_records.values():
        stats[task.status.value] = stats.get(task.status.value, 0) + 1
    
    return {
        "current_task": processing.to_dict() if processing else None,
        "queue_size": len(task_queue),
        "stats": stats,
        "worker_running": is_worker_running,
    }


@app.delete("/api/status/clear")
async def clear_history():
    """清除历史记录"""
    async with processing_lock:
        # 保留队列中的任务和正在处理的任务
        to_keep = {t.execution_id for t in task_queue}
        for task in task_records.values():
            if task.status == TaskStatus.PROCESSING:
                to_keep.add(task.execution_id)
        
        # 删除已完成的
        to_delete = [eid for eid in task_records if eid not in to_keep]
        for eid in to_delete:
            del task_records[eid]
    
    return {"message": f"Cleared {len(to_delete)} records"}


# ==============================================================================
# 主入口
# ==============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.mock_data_source:app",
        host="0.0.0.0",
        port=3001,
        reload=True,
    )
