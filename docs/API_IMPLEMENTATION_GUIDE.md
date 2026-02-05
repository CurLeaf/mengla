# API 实现思路文档

> 基于 `openapi.yaml` 规范和现有 `backend/` 实现分析

## 1. 系统架构概述

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (Vue/React)                        │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FastAPI Application (main.py)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐│
│  │   Health    │  │  MengLa     │  │   Panel     │  │   Admin     ││
│  │   Routes    │  │  Query API  │  │   API       │  │   API       ││
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
            │   L1 Cache  │ │   L2 Cache  │ │   L3 Cache  │
            │   (Memory)  │ │   (Redis)   │ │  (MongoDB)  │
            └─────────────┘ └─────────────┘ └─────────────┘
                                    │
                                    ▼
            ┌─────────────────────────────────────────────┐
            │          外部采集服务 (MengLa API)          │
            └─────────────────────────────────────────────┘
```

### 1.2 核心模块划分

| 模块 | 目录/文件 | 职责 |
|------|-----------|------|
| **API 路由** | `main.py` | HTTP 接口定义、请求校验、响应封装 |
| **业务核心** | `core/domain.py` | 查询逻辑、缓存穿透策略 |
| **外部调用** | `core/client.py` | 与 MengLa 采集服务通信 |
| **基础设施** | `infra/` | 数据库、缓存、告警、监控、熔断 |
| **调度任务** | `scheduler.py` | APScheduler 定时任务 |
| **工具脚本** | `tools/` | 补录、清理、诊断工具 |
| **公共工具** | `utils/` | 类目、配置、时间周期处理 |

---

## 2. API 分类与实现思路

### 2.1 健康检查 API

| 路由 | 实现要点 |
|------|----------|
| `GET /` | 返回服务运行状态，无依赖检查 |
| `GET /health` | 可扩展为深度健康检查（DB/Redis 连通性） |

**实现模式**：
```python
@app.get("/health")
async def health_check():
    # 基础版：直接返回 ok
    return {"status": "ok"}
    
    # 深度版（可选）：
    # - 检查 MongoDB 连接
    # - 检查 Redis 连接
    # - 检查采集服务可达性
```

---

### 2.2 类目管理 API

| 路由 | 实现要点 |
|------|----------|
| `GET /api/categories` | 返回完整类目树，支持内存缓存 |

**实现思路**：
1. 数据源：`backend/category.json`（静态文件）
2. 缓存策略：首次加载后常驻内存，无过期
3. 类目校验：所有 `catId` 参数必须在类目树中存在

**代码结构**：
```python
# utils/category.py
_category_cache: Optional[List] = None

def get_all_categories() -> List:
    global _category_cache
    if _category_cache is None:
        _category_cache = load_from_json()
    return _category_cache

def get_all_valid_cat_ids() -> Set[str]:
    """提取所有有效 catId（含子级）"""
    ...
```

---

### 2.3 MengLa 数据查询 API（核心）

#### 2.3.1 统一入口与独立接口

| 路由 | Action | 说明 |
|------|--------|------|
| `POST /api/mengla/query` | 动态 | 统一入口，根据 `action` 分发 |
| `POST /api/mengla/high` | `high` | 蓝海 Top 行业 |
| `POST /api/mengla/hot` | `hot` | 热销 Top 行业 |
| `POST /api/mengla/chance` | `chance` | 潜力 Top 行业 |
| `POST /api/mengla/industry-view` | `industryViewV2` | 行业区间分布 |
| `POST /api/mengla/industry-trend` | `industryTrendRange` | 行业趋势 |

#### 2.3.2 请求参数设计

```python
class MengLaQueryParamsBody(BaseModel):
    product_id: Optional[str] = ""    # 产品ID（可选）
    catId: Optional[str] = ""         # 类目ID（必须在 category.json 中）
    dateType: Optional[str] = ""      # 颗粒度: DAY/MONTH/QUARTER/YEAR
    timest: Optional[str] = ""        # 时间戳: 2026-02
    starRange: Optional[str] = ""     # 开始日期: 2026-01-01
    endRange: Optional[str] = ""      # 结束日期: 2026-01-31
    extra: Optional[dict] = None      # 扩展参数
```

#### 2.3.3 核心查询流程

```
请求进入
    │
    ▼
┌───────────────────┐
│  1. 参数校验       │  - catId 必须在类目列表中
│                   │  - dateType 必须是有效枚举
└───────────────────┘
    │
    ▼
┌───────────────────┐
│  2. 多层缓存查询   │  L1(内存) → L2(Redis) → L3(MongoDB)
│                   │  任一层命中则返回
└───────────────────┘
    │ 全部未命中
    ▼
┌───────────────────┐
│  3. 实时采集       │  调用外部 MengLa API
│                   │  支持熔断保护
└───────────────────┘
    │
    ▼
┌───────────────────┐
│  4. 结果回写       │  异步写入 L1 → L2 → L3
│                   │  附加 secondaryCategories
└───────────────────┘
    │
    ▼
┌───────────────────┐
│  5. 响应封装       │  设置 X-MengLa-Source 头
│                   │  趋势数据设置 X-MengLa-Trend-Partial
└───────────────────┘
```

#### 2.3.4 缓存键设计

```
格式: mengla:{action}:{granularity}:{period_key}:{cat_id}

示例:
- mengla:high:day:20260201:17027494
- mengla:industryTrendRange:month:2026-01:
```

#### 2.3.5 响应头说明

| Header | 值 | 含义 |
|--------|-----|------|
| `X-MengLa-Source` | `l1` | 来自本地内存缓存 |
| `X-MengLa-Source` | `l2` | 来自 Redis 缓存 |
| `X-MengLa-Source` | `l3` | 来自 MongoDB 持久化 |
| `X-MengLa-Source` | `fresh` | 来自实时采集 |
| `X-MengLa-Trend-Partial` | `30,25` | 趋势数据请求30天，实际返回25天 |

---

### 2.4 面板配置 API

| 路由 | 权限 | 实现要点 |
|------|------|----------|
| `GET /panel/config` | 公开 | 返回面板模块配置 |
| `PUT /panel/config` | 管理 | 更新配置并持久化到 JSON |
| `GET /panel/tasks` | 管理 | 列出可执行任务 |
| `POST /panel/tasks/{task_id}/run` | 管理 | 后台执行指定任务 |
| `POST /panel/data/fill` | 管理 | 补数任务 |

**权限控制实现**：
```python
def _panel_admin_enabled() -> bool:
    v = os.getenv("ENABLE_PANEL_ADMIN", "")
    if v:
        return v in ("1", "true", "yes")
    # 非 production 默认开启
    return os.getenv("ENV", "") != "production"

async def require_panel_admin():
    if not _panel_admin_enabled():
        raise HTTPException(403, "Panel admin is disabled")
```

**任务定义**：
```python
PANEL_TASKS = {
    "daily_collect": {
        "name": "每日主采集",
        "description": "采集当天的 day 颗粒度数据",
        "run": run_daily_collect,
    },
    "monthly_collect": {...},
    "quarterly_collect": {...},
    "yearly_collect": {...},
    "backfill_check": {...},
}
```

---

### 2.5 管理与运维 API

#### 2.5.1 数据状态检查

| 路由 | 说明 |
|------|------|
| `POST /admin/mengla/status` | 检查指定条件下各接口数据是否存在 |
| `POST /admin/mengla/enqueue-full-crawl` | 创建队列化爬取任务 |
| `POST /admin/backfill` | 历史数据补录 |

**状态检查实现**：
```python
# 查询 MongoDB 中已存在的 period_key
base_filter = {
    "action": action,
    "granularity": granularity,
    "period_key": {"$in": keys},
}
if cat_id:
    base_filter["cat_id"] = cat_id

# 返回每个 period_key 的存在状态
status = {action: {k: (k in present_keys) for k in all_keys}}
```

#### 2.5.2 监控指标

| 路由 | 返回数据 |
|------|----------|
| `GET /admin/metrics` | 请求总数、成功/失败数、平均延迟、缓存命中率 |
| `GET /admin/metrics/latency` | P50/P90/P99 延迟百分位 |

**指标收集器设计**：
```python
class MetricsCollector:
    def __init__(self):
        self.total_requests = 0
        self.success_count = 0
        self.error_count = 0
        self.latencies = []  # 滑动窗口
    
    async def record_request(self, success: bool, latency_ms: float):
        ...
    
    async def get_latency_percentiles(self):
        return {"p50": ..., "p90": ..., "p99": ...}
```

#### 2.5.3 告警系统

| 路由 | 说明 |
|------|------|
| `GET /admin/alerts` | 获取活跃告警和规则状态 |
| `GET /admin/alerts/history` | 告警历史记录 |
| `POST /admin/alerts/check` | 手动触发检查 |
| `POST /admin/alerts/silence` | 静默指定规则 |

**告警规则示例**：
```python
ALERT_RULES = {
    "high_error_rate": {
        "threshold": 0.1,  # 10% 错误率
        "window_minutes": 5,
        "severity": "critical",
    },
    "high_latency": {
        "threshold_ms": 5000,
        "percentile": "p99",
        "severity": "warning",
    },
}
```

#### 2.5.4 缓存管理

| 路由 | 说明 |
|------|------|
| `GET /admin/cache/stats` | L1/L2 命中率、大小统计 |
| `POST /admin/cache/warmup` | 预热指定范围数据到缓存 |
| `POST /admin/cache/clear-l1` | 清空本地内存缓存 |

#### 2.5.5 熔断器

| 路由 | 说明 |
|------|------|
| `GET /admin/circuit-breakers` | 各熔断器状态（CLOSED/OPEN/HALF-OPEN） |
| `POST /admin/circuit-breakers/reset` | 重置所有熔断器 |

**熔断器实现模式**：
```python
class CircuitBreaker:
    def __init__(self, name, failure_threshold=5, recovery_time=30):
        self.state = "CLOSED"
        self.failures = 0
        
    async def call(self, func, *args):
        if self.state == "OPEN":
            if self._should_try_recovery():
                self.state = "HALF-OPEN"
            else:
                raise CircuitOpenError()
        
        try:
            result = await func(*args)
            self._record_success()
            return result
        except Exception:
            self._record_failure()
            raise
```

#### 2.5.6 系统综合状态

```python
@app.get("/admin/system/status")
async def get_system_status():
    return {
        "metrics": await get_current_metrics(),
        "cache": cache_manager.get_stats(),
        "alerts": {
            "active_count": len(await alert_manager.get_active_alerts()),
            "rules": await alert_manager.get_rule_status(),
        },
        "circuit_breakers": circuit_manager.get_all_stats(),
        "scheduler": {
            "running": scheduler.running,
            "jobs": [job.to_dict() for job in scheduler.get_jobs()],
        },
    }
```

---

### 2.6 Webhook API

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/webhook/mengla-notify` | GET | 健康检查（采集服务测试可达性） |
| `/api/webhook/mengla-notify` | POST | 接收采集完成回调 |

**回调处理流程**：
```
1. 解析 payload 获取 executionId
2. 提取 resultData 或完整 payload
3. 写入 Redis: mengla:exec:{executionId} (TTL=30min)
4. domain.py 中的轮询逻辑读取此 key
```

---

## 3. 核心设计模式

### 3.1 多层缓存穿透

```python
async def query_mengla(action, **params) -> Tuple[dict, str]:
    cache_key = build_cache_key(action, params)
    
    # L1: 本地内存
    if data := l1_cache.get(cache_key):
        return data, "l1"
    
    # L2: Redis
    if data := await redis.get(cache_key):
        l1_cache.set(cache_key, data)
        return json.loads(data), "l2"
    
    # L3: MongoDB
    if doc := await mongo.find_one(build_mongo_filter(action, params)):
        await redis.set(cache_key, json.dumps(doc["data"]))
        l1_cache.set(cache_key, doc["data"])
        return doc["data"], "l3"
    
    # Fresh: 实时采集
    data = await fetch_from_mengla(action, params)
    await write_to_all_caches(cache_key, action, params, data)
    return data, "fresh"
```

### 3.2 参数校验装饰器

```python
def validate_cat_id(func):
    @wraps(func)
    async def wrapper(*args, body: MengLaQueryParamsBody, **kwargs):
        if body.catId and body.catId not in get_all_valid_cat_ids():
            raise HTTPException(400, f"Invalid catId: {body.catId}")
        return await func(*args, body=body, **kwargs)
    return wrapper
```

### 3.3 后台任务模式

```python
@app.post("/panel/data/fill")
async def panel_data_fill(body: PanelDataFillRequest, tasks: BackgroundTasks):
    # 立即返回，任务在后台执行
    tasks.add_task(fill_mengla_missing, body.granularity, body.startDate, body.endDate)
    return {"message": "fill started", ...}
```

### 3.4 统一异常处理

```python
async def _mengla_query_by_action(action: str, body: MengLaQueryParamsBody):
    try:
        result = await query_mengla(action, **body.dict())
        return JSONResponse(content=result[0], headers={"X-MengLa-Source": result[1]})
    except TimeoutError:
        raise HTTPException(504, "mengla query timeout")
    except httpx.ConnectError:
        raise HTTPException(503, "采集服务不可达")
    except httpx.TimeoutException:
        raise HTTPException(504, "采集服务请求超时")
    except Exception as exc:
        raise HTTPException(500, str(exc))
```

---

## 4. 数据模型设计

### 4.1 MongoDB 文档结构

```javascript
// Collection: mengla_data
{
    "_id": ObjectId(...),
    "action": "high",           // high/hot/chance/industryViewV2/industryTrendRange
    "granularity": "day",       // day/month/quarter/year
    "period_key": "20260201",   // 时间标识
    "cat_id": "17027494",       // 类目ID（空字符串表示全局）
    "data": {...},              // 原始响应数据
    "created_at": ISODate(...),
    "updated_at": ISODate(...)
}

// 索引
db.mengla_data.createIndex({action: 1, granularity: 1, period_key: 1, cat_id: 1}, {unique: true})
db.mengla_data.createIndex({created_at: 1}, {expireAfterSeconds: 86400 * 90})  // 90天过期
```

### 4.2 Redis 键设计

| 用途 | 键格式 | TTL |
|------|--------|-----|
| 数据缓存 | `mengla:{action}:{gran}:{period}:{cat}` | 1天 |
| Webhook 结果 | `mengla:exec:{executionId}` | 30分钟 |
| 熔断状态 | `circuit:{name}:state` | 无 |
| 告警计数 | `alert:{rule}:count` | 5分钟 |

---

## 5. 错误码规范

| HTTP | 场景 | detail 示例 |
|------|------|-------------|
| 400 | 参数校验失败 | `catId 必须在 backend/category.json 中` |
| 403 | 管理功能未开启 | `Panel admin is disabled. Set ENABLE_PANEL_ADMIN=1` |
| 404 | 资源不存在 | `unknown task_id: xxx` |
| 500 | 服务器内部错误 | 具体异常信息 |
| 503 | 外部服务不可达 | `采集服务不可达，请检查 COLLECT_SERVICE_URL` |
| 504 | 请求超时 | `mengla query timeout` |

---

## 6. 扩展建议

### 6.1 新增 Action 类型

1. 在 `core/domain.py` 的 `VALID_ACTIONS` 添加新 action
2. 在 `openapi.yaml` 补充新接口定义
3. （可选）在 `main.py` 添加独立路由端点

### 6.2 新增监控指标

1. 在 `infra/metrics.py` 扩展 `MetricsCollector`
2. 在 `main.py` 添加对应 admin 路由

### 6.3 新增告警规则

1. 在 `infra/alerting.py` 的规则配置中添加
2. 实现对应的检查函数

---

## 7. 部署配置

### 7.1 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MONGODB_URI` | MongoDB 连接串 | `mongodb://localhost:27017` |
| `REDIS_URI` | Redis 连接串 | `redis://localhost:6379` |
| `COLLECT_SERVICE_URL` | 采集服务地址 | - |
| `ENABLE_PANEL_ADMIN` | 启用管理功能 | 非生产环境默认开启 |
| `ENV` | 环境标识 | `development` |

### 7.2 启动命令

```bash
# 开发环境
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 生产环境
gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

---

## 8. 测试要点

### 8.1 单元测试

- 缓存命中/穿透场景
- 参数校验边界
- 异常处理分支

### 8.2 集成测试

- 完整查询流程（L1→L2→L3→fresh）
- Webhook 回调处理
- 定时任务执行

### 8.3 压力测试

- 并发查询性能
- 缓存击穿保护
- 熔断器触发阈值
