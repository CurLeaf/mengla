# API 文档

## OpenAPI 规范

完整的 OpenAPI 3.0 规范文档位于 `openapi.yaml`。

### 在线查看

可以使用以下工具查看和测试 API：

1. **Swagger UI**（推荐）
   - 访问 https://editor.swagger.io/
   - 点击 File → Import URL 或直接粘贴 YAML 内容

2. **Redoc**
   - 访问 https://redocly.github.io/redoc/
   - 上传 `openapi.yaml` 文件

3. **FastAPI 自带文档**
   - 启动后端后访问 http://localhost:8000/docs (Swagger UI)
   - 或访问 http://localhost:8000/redoc (ReDoc)

### 本地预览

```bash
# 使用 npx 启动 Swagger UI
npx swagger-ui-express-serve ./openapi.yaml

# 或使用 Docker
docker run -p 8080:8080 -e SWAGGER_JSON=/app/openapi.yaml -v $(pwd):/app swaggerapi/swagger-ui
```

## API 概览

### 公开接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务状态 |
| GET | `/health` | 健康检查 |
| GET | `/api/categories` | 获取类目树 |
| GET | `/panel/config` | 获取面板配置 |
| POST | `/api/mengla/query` | 统一数据查询 |
| POST | `/api/mengla/high` | 蓝海行业 |
| POST | `/api/mengla/hot` | 热销行业 |
| POST | `/api/mengla/chance` | 潜力行业 |
| POST | `/api/mengla/industry-view` | 行业区间 |
| POST | `/api/mengla/industry-trend` | 行业趋势 |

### Webhook 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/webhook/mengla-notify` | 健康检查 |
| POST | `/api/webhook/mengla-notify` | 采集回调 |

### 管理接口（需要 ENABLE_PANEL_ADMIN=1）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/panel/tasks` | 任务列表 |
| POST | `/panel/tasks/{task_id}/run` | 执行任务 |
| PUT | `/panel/config` | 更新面板配置 |
| POST | `/panel/data/fill` | 补数任务 |
| POST | `/admin/mengla/status` | 数据状态检查 |
| POST | `/admin/mengla/enqueue-full-crawl` | 创建爬取任务 |
| POST | `/admin/backfill` | 历史补录 |
| GET | `/admin/metrics` | 采集指标 |
| GET | `/admin/alerts` | 告警状态 |
| GET | `/admin/cache/stats` | 缓存统计 |
| GET | `/admin/system/status` | 系统综合状态 |

## 快速示例

### 查询蓝海行业

```bash
curl -X POST http://localhost:8000/api/mengla/high \
  -H "Content-Type: application/json" \
  -d '{
    "catId": "17027494",
    "dateType": "MONTH",
    "timest": "2026-02"
  }'
```

### 查询行业趋势

```bash
curl -X POST http://localhost:8000/api/mengla/industry-trend \
  -H "Content-Type: application/json" \
  -d '{
    "catId": "17027494",
    "dateType": "DAY",
    "starRange": "2026-01-01",
    "endRange": "2026-01-31"
  }'
```

### 执行采集任务

```bash
curl -X POST http://localhost:8000/panel/tasks/daily_collect/run
```

## 响应头说明

| 响应头 | 说明 | 值 |
|--------|------|-----|
| X-MengLa-Source | 数据来源 | `l1` (本地缓存), `l2` (Redis), `l3` (MongoDB), `fresh` (实时采集) |
| X-MengLa-Trend-Partial | 趋势数据部分返回 | `requested,found` 格式 |

## 错误码

| HTTP 状态码 | 说明 |
|-------------|------|
| 400 | 请求参数错误（如 catId 不在类目列表中） |
| 403 | 管理功能未启用 |
| 404 | 资源不存在（如任务ID不存在） |
| 500 | 服务器内部错误 |
| 503 | 采集服务不可达 |
| 504 | 请求超时 |
