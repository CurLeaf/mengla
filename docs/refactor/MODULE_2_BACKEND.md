# 模块 2 — 后端架构重构

> **负责角色：** 后端开发  
> **优先级：** 🟡 重要  
> **预估工时：** 6-8 天  
> **分支名：** `refactor/module-2-backend`  

---

## 本模块管辖文件（与其他模块零交叉）

```
backend/main.py                 ← 修改（路由拆分、CORS 环境变量化、统一异常处理）
backend/api/                    ← 新建（路由模块目录）
  ├── __init__.py
  ├── auth_routes.py
  ├── category_routes.py
  ├── mengla_routes.py
  ├── panel_routes.py
  ├── admin_routes.py
  ├── sync_task_routes.py
  └── schemas/
      ├── __init__.py
      └── responses.py
backend/middleware/              ← 新建
  ├── __init__.py
  └── error_handler.py
backend/scheduler.py            ← 修改（统一采集函数、间隔配置化、失败重试）
backend/core/domain.py          ← 修改（IN_FLIGHT 并发锁、去重安全化）
backend/core/queue.py           ← 修改（原子 claim 操作）
backend/infra/cache.py          ← 修改（缓存计数器安全化）
backend/infra/alerting.py       ← 修改（告警历史有界化 deque）
backend/infra/metrics.py        ← 修改（指标自动过期清理）
backend/utils/config.py         ← 修改（采集间隔配置、环境变量校验）
```

> **不触碰：** `backend/core/auth.py`、`backend/Dockerfile`、`docker/*`、`frontend/*`

---

## 问题清单

| # | 问题 | 当前文件 | 严重度 |
|---|------|----------|--------|
| 1 | main.py 1200+ 行，所有路由混在一起 | `backend/main.py` | 🟡 |
| 2 | 错误响应格式不一致 | `backend/main.py` | 🟡 |
| 3 | 无全局异常处理中间件 | `backend/main.py` | 🟡 |
| 4 | Pydantic 模型散落各处 | `backend/main.py` | 🟡 |
| 5 | CORS 硬编码 `*` | `backend/main.py` | 🔴 |
| 6 | IN_FLIGHT 字典无并发锁 | `backend/core/domain.py` | 🟡 |
| 7 | `_background_tasks` 集合非线程安全 | `backend/main.py` | 🟡 |
| 8 | Queue claim 非原子操作 | `backend/core/queue.py` | 🟡 |
| 9 | 缓存 hit/miss 计数器竞态 | `backend/infra/cache.py` | 🟢 |
| 10 | `_alert_history` 列表无界增长 | `backend/infra/alerting.py` | 🟡 |
| 11 | `_daily_metrics` 字典无过期 | `backend/infra/metrics.py` | 🟡 |
| 12 | 去重删除缺少安全检查 | `backend/core/domain.py` | 🟡 |
| 13 | 4 个重复的采集函数 | `backend/scheduler.py` | 🟡 |
| 14 | scheduler.py 文件过大 | `backend/scheduler.py` | 🟡 |
| 15 | 采集间隔硬编码 | `backend/scheduler.py` | 🟢 |
| 16 | 定时任务失败无重试 | `backend/scheduler.py` | 🟡 |
| 17 | 启动时环境变量不校验 | `backend/utils/config.py` | 🟡 |

---

## 修复方案

### 一、路由拆分（问题 #1-5）

#### 1.1 main.py 拆分为路由模块

**新建目录结构：**
```
backend/api/
├── __init__.py
├── auth_routes.py        # /auth/*
├── category_routes.py    # /categories
├── mengla_routes.py      # /mengla/*
├── panel_routes.py       # /panel-config
├── admin_routes.py       # /admin/*
├── sync_task_routes.py   # /sync-tasks/*
└── schemas/
    ├── __init__.py
    └── responses.py      # 统一 Pydantic 响应模型
```

**`backend/api/schemas/responses.py`（新建）:**
```python
from pydantic import BaseModel
from typing import Any, Optional

class ApiResponse(BaseModel):
    success: bool = True
    data: Any = None
    message: str = "ok"

class ApiError(BaseModel):
    success: bool = False
    error: str
    message: str
    detail: Optional[str] = None
```

**路由模块示例 — `backend/api/mengla_routes.py`（新建）:**
```python
from fastapi import APIRouter, Depends, Query
from ..api.schemas.responses import ApiResponse, ApiError

router = APIRouter(prefix="/mengla", tags=["MengLa Data"])

@router.get("/", response_model=ApiResponse)
async def get_mengla_data(
    primaryCatId: str = Query(...),
    timest: str = Query(...),
    # ... 其他参数
):
    """获取勐腊行业数据"""
    try:
        result = await query_mengla(...)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiError(error="QUERY_FAILED", message=str(e))
```

**`backend/main.py` 瘦身后结构（修改）:**
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import auth_routes, category_routes, mengla_routes, panel_routes, admin_routes, sync_task_routes
from .middleware.error_handler import register_error_handlers
from .utils.config import validate_env

# 启动时校验环境变量
validate_env()

app = FastAPI(title="MengLa Data Collector")

# CORS 从环境变量读取
origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

# 注册路由
app.include_router(auth_routes.router)
app.include_router(category_routes.router)
app.include_router(mengla_routes.router)
app.include_router(panel_routes.router)
app.include_router(admin_routes.router)
app.include_router(sync_task_routes.router)

# 注册异常处理
register_error_handlers(app)

# 生命周期事件保留在 main.py
@app.on_event("startup")
async def startup(): ...

@app.on_event("shutdown")
async def shutdown(): ...
```

#### 1.2 统一异常处理中间件（新建）
**文件：** `backend/middleware/error_handler.py`
```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger("mengla")

def register_error_handlers(app: FastAPI):
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "VALIDATION_ERROR", "message": str(exc)}
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "INTERNAL_ERROR", "message": "Internal server error"}
        )
```

---

### 二、并发安全与内存治理（问题 #6-12）

#### 2.1 IN_FLIGHT 加锁
**文件：** `backend/core/domain.py`
```python
import asyncio

_in_flight_lock = asyncio.Lock()
IN_FLIGHT: dict[str, asyncio.Task] = {}

async def query_mengla(...):
    cache_key = build_cache_key(...)
    
    async with _in_flight_lock:
        if cache_key in IN_FLIGHT:
            existing = IN_FLIGHT[cache_key]
    
    if existing and not existing.done():
        return await existing
    
    task = asyncio.current_task()
    async with _in_flight_lock:
        IN_FLIGHT[cache_key] = task
    try:
        result = await _do_query(...)
        return result
    finally:
        async with _in_flight_lock:
            IN_FLIGHT.pop(cache_key, None)
```

#### 2.2 后台任务集合安全化
**文件：** `backend/main.py`（移至 `admin_routes.py` 后）
```python
import asyncio

_bg_lock = asyncio.Lock()
_background_tasks: set[asyncio.Task] = set()

async def track_background_task(coro):
    task = asyncio.create_task(coro)
    async with _bg_lock:
        _background_tasks.add(task)
    task.add_done_callback(lambda t: asyncio.create_task(_remove_task(t)))
    return task

async def _remove_task(task):
    async with _bg_lock:
        _background_tasks.discard(task)
```

#### 2.3 Queue 原子 claim
**文件：** `backend/core/queue.py`
```python
async def claim_next(self) -> Optional[dict]:
    """使用 Redis WATCH/MULTI 或 Lua 脚本实现原子 claim"""
    lua_script = """
    local item = redis.call('LPOP', KEYS[1])
    if item then
        redis.call('HSET', KEYS[2], cjson.decode(item)['id'], item)
        return item
    end
    return nil
    """
    result = await self.redis.eval(lua_script, 2, self.queue_key, self.processing_key)
    return json.loads(result) if result else None
```

#### 2.4 缓存计数器安全化
**文件：** `backend/infra/cache.py`
```python
import asyncio

class CacheManager:
    def __init__(self):
        self._stats_lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def record_hit(self):
        async with self._stats_lock:
            self._hits += 1

    async def record_miss(self):
        async with self._stats_lock:
            self._misses += 1
```

#### 2.5 告警历史有界化
**文件：** `backend/infra/alerting.py`
```python
from collections import deque

_alert_history: deque = deque(maxlen=1000)  # 替换原 list

def add_alert(alert: dict):
    _alert_history.append(alert)  # 自动丢弃最旧条目
```

#### 2.6 每日指标自动过期
**文件：** `backend/infra/metrics.py`
```python
from datetime import datetime, timedelta

MAX_METRICS_DAYS = 30

def _cleanup_old_metrics():
    cutoff = (datetime.now() - timedelta(days=MAX_METRICS_DAYS)).strftime("%Y-%m-%d")
    expired = [k for k in _daily_metrics if k < cutoff]
    for k in expired:
        del _daily_metrics[k]

def record_metric(key: str, value: float):
    _cleanup_old_metrics()
    today = datetime.now().strftime("%Y-%m-%d")
    _daily_metrics.setdefault(today, {})[key] = value
```

#### 2.7 去重删除安全检查
**文件：** `backend/core/domain.py`
```python
async def remove_duplicate_data(collection, query: dict) -> int:
    """删除前验证确实存在重复"""
    pipeline = [{"$group": {"_id": query, "count": {"$sum": 1}, "ids": {"$push": "$_id"}}},
                {"$match": {"count": {"$gt": 1}}}]
    duplicates = await collection.aggregate(pipeline).to_list(None)
    removed = 0
    for doc in duplicates:
        ids_to_remove = doc["ids"][1:]  # 保留第一条
        result = await collection.delete_many({"_id": {"$in": ids_to_remove}})
        removed += result.deleted_count
    return removed
```

---

### 三、调度器重构（问题 #13-16）

#### 3.1 统一采集函数
**文件：** `backend/scheduler.py`
```python
# 修改前：4 个几乎相同的函数
async def collect_daily_data(): ...
async def collect_monthly_data(): ...
async def collect_quarterly_data(): ...
async def collect_yearly_data(): ...

# 修改后：1 个统一函数
async def run_period_collect(granularity: str):
    """统一采集入口，granularity = day|month|quarter|year"""
    logger.info(f"Scheduled {granularity} collection started")
    categories = load_categories()
    for cat in categories:
        periods = calculate_periods(cat, granularity)
        for period in periods:
            try:
                await query_mengla(
                    primary_cat_id=cat["id"],
                    timest=period,
                    granularity=granularity,
                    skip_cache=False
                )
                await asyncio.sleep(get_collect_interval())
            except Exception as e:
                logger.error(f"Collection failed: {cat['id']}/{period}/{granularity}: {e}")
                # 失败后延迟重试一次
                await asyncio.sleep(5)
                try:
                    await query_mengla(...)
                except Exception:
                    logger.error(f"Retry also failed, skip: {cat['id']}/{period}")

# 注册定时任务
scheduler.add_job(run_period_collect, 'cron', hour=2, args=['day'], id='daily_collect')
scheduler.add_job(run_period_collect, 'cron', day=1, hour=3, args=['month'], id='monthly_collect')
scheduler.add_job(run_period_collect, 'cron', month='1,4,7,10', day=2, hour=3, args=['quarter'], id='quarterly_collect')
scheduler.add_job(run_period_collect, 'cron', month=1, day=3, hour=3, args=['year'], id='yearly_collect')
```

#### 3.2 采集间隔配置化
**文件：** `backend/utils/config.py`
```python
def get_collect_interval() -> float:
    """采集请求间隔（秒），可通过环境变量调整"""
    return float(os.getenv("COLLECT_INTERVAL_SECONDS", "2.0"))

def validate_env():
    """启动时校验关键环境变量"""
    required = ["MONGO_URI", "REDIS_URI"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
```

---

## 检查清单

- [ ] `main.py` 行数 < 200
- [ ] 所有 API 返回统一 `{ success, data/error, message }` 格式
- [ ] 未处理异常返回 500 + 结构化 JSON（非 HTML 堆栈）
- [ ] `IN_FLIGHT` 操作在锁内执行
- [ ] `_alert_history` 长度不超过 1000
- [ ] 30 天前的 metrics 被自动清理
- [ ] 重复数据删除前有聚合验证
- [ ] `scheduler.py` 中只有 1 个 `run_period_collect` 函数
- [ ] `COLLECT_INTERVAL_SECONDS` 环境变量可调采集间隔
- [ ] CORS origins 从环境变量读取
- [ ] 缺少 MONGO_URI 时应用拒绝启动
