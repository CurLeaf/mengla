# 勐腊数据采集系统 — API 接口文档

> **Base URL:** `http://<host>:8000`　|　**认证:** `Authorization: Bearer <token>`
>
> **永久 Token（可直接使用）:**
> ```
> eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhcGk6YXBpIiwiaWF0IjoxNzcwNTQxMDQ3LCJ0eXBlIjoiYXBpX3Rva2VuIiwibGFiZWwiOiJhcGkifQ.NgdGBHGmuSStICViuQwodeQMNI0NplLpUaDOy6B8Ddw
> ```

---

## 快速索引

| 接口 | 方法 | 路径 | 认证 | 用途 |
|------|------|------|:----:|------|
| [面板配置](#11-获取面板配置) | GET | `/api/panel/config` | - | 初始化模块布局 |
| [蓝海 Top](#42-蓝海-top) | POST | `/api/data/mengla/high` | ✅ | 蓝海排行榜 |
| [热销 Top](#43-热销-top) | POST | `/api/data/mengla/hot` | ✅ | 热销排行榜 |
| [潜力 Top](#44-潜力-top) | POST | `/api/data/mengla/chance` | ✅ | 潜力排行榜 |
| [行业概览](#45-行业概览) | POST | `/api/data/mengla/industry-view` | ✅ | 分布图 + 品牌占比 |
| [行业趋势](#46-行业趋势) | POST | `/api/data/mengla/industry-trend` | ✅ | 时间序列折线图 |

> 管理端接口见 [第三节](#三管理端接口)

---

## 对接流程

```
1. GET  /api/panel/config         → 面板配置（决定显示哪些模块）
2. POST /api/data/mengla/{action} → 按需查询行业数据
```

---

## 一、面板配置

### 1.1 获取面板配置

`GET /api/panel/config`　**无需认证**

```typescript
interface PanelConfig {
  modules: {
    id: "overview" | "high" | "hot" | "chance";
    name: string;        // 模块中文名
    enabled: boolean;
    order: number;
    props?: Record<string, unknown>;
  }[];
  layout: {
    defaultPeriod?: "day" | "month" | "quarter" | "year";
    showRankPeriodSelector?: boolean;
  };
}
```

### 1.2 更新面板配置

`PUT /api/panel/config`　**需要管理员认证**

请求体同 `PanelConfig`，`modules` / `layout` 均可选，只传需更新的部分。

---

## 二、行业数据查询（核心）

> 所有接口均为 **POST**，均需 **Bearer Token**。
> 可用统一入口 `POST /api/data/mengla/query`（需加 `action` 字段），也可用独立端点。

### 公共参数

| 字段 | 类型 | 说明 |
|------|------|------|
| `action` | string | 统一入口必填：`"high"` / `"hot"` / `"chance"` / `"industryViewV2"` / `"industryTrendRange"` |
| `catId` | string | 类目 ID，`""` = 全部 |
| `dateType` | string | 粒度：`"day"` / `"month"` / `"quarter"` / `"year"` |
| `timest` | string | 时间周期 key（排行/概览用） |
| `starRange` | string | 起始日期（仅趋势用） |
| `endRange` | string | 结束日期（仅趋势用） |

**`timest` 格式对照:**

| dateType | timest 示例 |
|----------|------------|
| `day` | `2025-06-01` |
| `month` | `2025-06` |
| `quarter` | `2025-Q1` |
| `year` | `2025` |

**响应头:**

| Header | 说明 |
|--------|------|
| `X-MengLa-Source` | 数据来源：`l1`(内存) / `l2`(Redis) / `l3`(MongoDB) / `fresh`(实时采集) |
| `X-MengLa-Trend-Partial` | 趋势是否部分返回，如 `"12,8"` = 请求12个点返回8个 |

**附加字段:** 传入 `catId` 时，响应会包含 `secondaryCategories` 子类目列表。

---

### 4.1 统一入口

`POST /api/data/mengla/query`

```json
{ "action": "high", "catId": "", "dateType": "month", "timest": "2025-06" }
```

### 4.2 蓝海 Top

`POST /api/data/mengla/high`　统一入口 `action = "high"`

**请求:**

```json
{ "catId": "", "dateType": "month", "timest": "2025-06" }
```

**响应:** `{ highList: { code: 0, data: { list: HighListRow[] } }, secondaryCategories: [] }`

### 4.3 热销 Top

`POST /api/data/mengla/hot`　统一入口 `action = "hot"`

请求同 4.2。响应: `{ hotList: { code: 0, data: { list: HighListRow[] } }, secondaryCategories: [] }`

### 4.4 潜力 Top

`POST /api/data/mengla/chance`　统一入口 `action = "chance"`

请求同 4.2。响应: `{ chanceList: { code: 0, data: { list: HighListRow[] } }, secondaryCategories: [] }`

### 4.5 行业概览

`POST /api/data/mengla/industry-view`　统一入口 `action = "industryViewV2"`

请求同 4.2。

**响应:**

```json
{
  "industryViewV2List": {
    "industrySalesRangeDtoList": "RangeItem[]  // 销量区间分布",
    "industryGmvRangeDtoList":   "RangeItem[]  // GMV 区间分布",
    "industryPriceRangeDtoList": "RangeItem[]  // 价格区间分布",
    "industryBrandRateDtoList":  "BrandRateItem[] // 品牌占比"
  },
  "secondaryCategories": []
}
```

### 4.6 行业趋势

`POST /api/data/mengla/industry-trend`　统一入口 `action = "industryTrendRange"`

**请求:** 使用 `starRange` / `endRange` 替代 `timest`

```json
{ "catId": "", "dateType": "month", "starRange": "2025-01-01", "endRange": "2025-06-30" }
```

**响应:** `{ industryTrendRange: { data: TrendPoint[] }, secondaryCategories: [] }`

---

## 页面-接口映射

| 页面 | 接口 | 必要参数 |
|------|------|----------|
| 蓝海排行榜 | `POST .../high` | `dateType` + `timest` + `catId`(可选) |
| 热销排行榜 | `POST .../hot` | 同上 |
| 潜力排行榜 | `POST .../chance` | 同上 |
| 行业概览(分布图) | `POST .../industry-view` | 同上 |
| 行业趋势(折线图) | `POST .../industry-trend` | `dateType` + `starRange` + `endRange` + `catId`(可选) |

---

## 类型定义

### HighListRow（蓝海/热销/潜力 通用）

```typescript
interface HighListRow {
  catNameCn: string;           // 类目中文名
  catName: string;             // 类目英文名
  catTag: number;              // 类目标签
  catId1: string;              // 一级类目 ID
  catId2: string;              // 二级类目 ID
  catId3: string;              // 三级类目 ID
  skuNum: number;              // SKU 总数
  saleSkuNum: number;          // 在售 SKU 数
  saleRatio: number;           // 在售比例 (0~1)
  monthSales: number;          // 月销量
  monthSalesRating: number;    // 月销量评分
  monthSalesDynamics: number;  // 月销量环比变动
  monthGmv: number;            // 月 GMV（美元）
  monthGmvRmb: number;         // 月 GMV（人民币）
  monthGmvRating: number;      // 月 GMV 评分
  monthGmvDynamics: number;    // 月 GMV 环比变动
  brand: string;               // 品牌名
  brandGmv: number;            // 品牌 GMV（美元）
  brandGmvRmb: number;         // 品牌 GMV（人民币）
  brandGmvRating: number;      // 品牌 GMV 占比 (0~1)
  topGmv: number;              // Top 商品 GMV
  topGmvRating: number;        // Top 商品 GMV 占比
  topAvgPrice: number;         // Top 商品均价（美元）
  topAvgPriceRmb: number;      // Top 商品均价（人民币）
}
```

### RangeItem（行业概览区间分布）

```typescript
interface RangeItem {
  id: string;            // 区间 ID
  title: string;         // 区间标题，如 "$0-5"
  itemCount: number;     // 商品数量
  sales: number;         // 销量
  gmv: number;           // GMV
  itemCountRate: number; // 商品数量占比 (0~1)
  salesRate: number;     // 销量占比 (0~1)
  gmvRate: number;       // GMV 占比 (0~1)
}
```

### BrandRateItem（品牌占比）

```typescript
interface BrandRateItem {
  catId: string;              // 类目 ID
  catName: string;            // 类目英文名
  catNameCn: string;          // 类目中文名
  brandGmv: number;           // 品牌 GMV
  brandGmvRate: number;       // 品牌 GMV 占比 (0~1)
  brandItemCount: number;     // 品牌商品数
  brandItemCountRate: number; // 品牌商品占比 (0~1)
  brandSales: number;         // 品牌销量
  brandSalesRate: number;     // 品牌销量占比 (0~1)
  typeId: string;             // 类型 ID
}
```

### TrendPoint（趋势数据点）

```typescript
interface TrendPoint {
  timest: string;          // 时间标记，如 "2025-01"
  salesSkuCount: number;   // 在售 SKU 数
  salesSkuRatio: number;   // 在售 SKU 比例
  monthSales: number;      // 月销量
  monthSalesRatio: number; // 月销量环比
  monthGmv: number;        // 月 GMV
  monthGmvRatio: number;   // 月 GMV 环比
  currentDayPrice: number; // 当日均价
}
```

---

## 三、管理端接口

> 以下接口仅供管理后台使用，均需**管理员认证**。

### 5.1 数据可用性

`POST /api/admin/mengla/status`

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `catId` | string | 否 | 类目 ID |
| `granularity` | string | 是 | `"day"` / `"month"` / `"quarter"` / `"year"` |
| `startDate` | string | 是 | `yyyy-MM-dd` |
| `endDate` | string | 是 | `yyyy-MM-dd` |
| `actions` | string[] | 否 | 要查询的 action，默认全部 |

### 5.2 采集健康监控

`GET /api/admin/collect-health?date=2025-06-01`

### 5.3 调度器控制

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/admin/scheduler/status` | GET | 调度器状态 |
| `/api/admin/scheduler/pause` | POST | 暂停 |
| `/api/admin/scheduler/resume` | POST | 恢复 |

### 5.4 任务管理

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/panel/tasks/{task_id}/run` | POST | 手动触发任务 |
| `/api/admin/tasks/cancel-all` | POST | 取消所有任务 |

### 5.5 数据操作

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/panel/data/fill` | POST | 数据补录 |
| `/api/admin/backfill` | POST | 历史回填 |
| `/api/admin/mengla/enqueue-full-crawl` | POST | 全量爬取 |
| `/api/admin/data/purge` | POST | ⚠️ 清空数据和缓存 |

### 5.6 缓存与熔断器

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/admin/cache/stats` | GET | 缓存统计 |
| `/api/admin/cache/warmup` | POST | 缓存预热 |
| `/api/admin/cache/clear-l1` | POST | 清除 L1 缓存 |
| `/api/admin/circuit-breakers` | GET | 熔断器状态 |
| `/api/admin/circuit-breakers/reset` | POST | 重置熔断器 |

### 5.7 监控与告警

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/admin/metrics` | GET | 采集指标 |
| `/api/admin/metrics/latency` | GET | 延迟统计 |
| `/api/admin/alerts` | GET | 活跃告警 |
| `/api/admin/alerts/history?limit=100` | GET | 告警历史 |
| `/api/admin/alerts/check` | POST | 手动告警检查 |
| `/api/admin/alerts/silence` | POST | 静默告警 |
| `/api/admin/system/status` | GET | 系统综合状态 |

### 5.8 同步任务日志

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/sync-tasks/today` | GET | 今日任务列表 |
| `/api/sync-tasks/{log_id}` | GET | 任务详情 |
| `/api/sync-tasks/{log_id}/cancel` | POST | 取消任务 |
| `/api/sync-tasks/{log_id}` | DELETE | 删除日志 |

---

## cURL 示例

```bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhcGk6YXBpIiwiaWF0IjoxNzcwNTQxMDQ3LCJ0eXBlIjoiYXBpX3Rva2VuIiwibGFiZWwiOiJhcGkifQ.NgdGBHGmuSStICViuQwodeQMNI0NplLpUaDOy6B8Ddw"

# 蓝海 Top（月粒度，2025年6月）
curl -X POST http://localhost:8000/api/data/mengla/high \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"catId":"","dateType":"month","timest":"2025-06"}'

# 行业趋势（2025 上半年）
curl -X POST http://localhost:8000/api/data/mengla/industry-trend \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"catId":"","dateType":"month","starRange":"2025-01-01","endRange":"2025-06-30"}'
```
