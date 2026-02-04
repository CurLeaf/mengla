# 萌拉（MengLa）接口说明

## 查询顺序

所有萌拉相关接口的**数据查询顺序**一致：

1. **MongoDB** — 优先从 MongoDB 按 `granularity`、`period_key`（或趋势的多个 key）、`params_hash` 查询；命中则直接返回，并可选回写 Redis。
2. **Redis** — MongoDB 未命中时，从 Redis 按参数 key 查询；命中则直接返回。
3. **采集服务（Cache）** — MongoDB 与 Redis 均未命中时，调用外部采集服务拉取数据，落库 MongoDB 并写入 Redis 后返回。

响应头 `X-MengLa-Source` 表示本次数据来源：`mongo` | `redis` | `fresh`。

---

## 通用请求参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| product_id | string | 否 | 产品 ID，默认 `""` |
| catId | string | 否 | 类目 ID，若传则必须在 `backend/类目.json` 中 |
| dateType | string | 否 | 时间粒度：如 `DAY`、`MONTH`、`QUARTER`、`YEAR`；行业趋势可为 `DAY`/`MONTH`/`QUARTER`/`YEAR` |
| timest | string | 否 | 时间点，格式随 dateType：如 `yyyy-MM-dd`、`yyyy-MM`、`yyyy-Qn`、`yyyy` |
| starRange | string | 否 | 区间开始（行业趋势/行业区间常用），如 `yyyy-MM-dd` 或 `yyyy-Qn` |
| endRange | string | 否 | 区间结束，格式同 starRange |
| extra | object | 否 | 扩展参数 |

---

## 1. 统一查询接口（含 action）

**POST** `/api/mengla/query`

通过请求体中的 `action` 区分业务类型，其他参数与下方各独立接口一致。

### 请求体参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| action | string | 是 | 取值：`high` \| `hot` \| `chance` \| `industryViewV2` \| `industryTrendRange` |
| product_id | string | 否 | 同通用说明 |
| catId | string | 否 | 同通用说明 |
| dateType | string | 否 | 同通用说明 |
| timest | string | 否 | 同通用说明 |
| starRange | string | 否 | 同通用说明 |
| endRange | string | 否 | 同通用说明 |
| extra | object | 否 | 同通用说明 |

---

## 2. 蓝海 Top 行业

**POST** `/api/mengla/high`

### 请求体参数（无 action，下同）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| product_id | string | 否 | 同通用说明 |
| catId | string | 否 | 同通用说明 |
| dateType | string | 否 | 如 `DAY`、`MONTH`、`QUARTER`、`YEAR` |
| timest | string | 否 | 对应粒度的单时间点 |
| starRange | string | 否 | 可与 timest 一致或传区间开始 |
| endRange | string | 否 | 可与 timest 一致或传区间结束 |
| extra | object | 否 | 同通用说明 |

---

## 3. 热销 Top 行业

**POST** `/api/mengla/hot`

### 请求体参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| product_id | string | 否 | 同通用说明 |
| catId | string | 否 | 同通用说明 |
| dateType | string | 否 | 如 `DAY`、`MONTH`、`QUARTER`、`YEAR` |
| timest | string | 否 | 对应粒度的单时间点 |
| starRange | string | 否 | 可选区间开始 |
| endRange | string | 否 | 可选区间结束 |
| extra | object | 否 | 同通用说明 |

---

## 4. 潜力 Top 行业

**POST** `/api/mengla/chance`

### 请求体参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| product_id | string | 否 | 同通用说明 |
| catId | string | 否 | 同通用说明 |
| dateType | string | 否 | 如 `DAY`、`MONTH`、`QUARTER`、`YEAR` |
| timest | string | 否 | 对应粒度的单时间点 |
| starRange | string | 否 | 可选区间开始 |
| endRange | string | 否 | 可选区间结束 |
| extra | object | 否 | 同通用说明 |

---

## 5. 行业区间/总览（industryViewV2）

**POST** `/api/mengla/industry-view`

### 请求体参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| product_id | string | 否 | 同通用说明 |
| catId | string | 否 | 同通用说明 |
| dateType | string | 否 | 如 `DAY`、`MONTH`、`QUARTER`、`YEAR`；季榜可用 `QUARTERLY_FOR_YEAR` |
| timest | string | 否 | 对应粒度的单时间点，季榜可为 `yyyy-Qn` |
| starRange | string | 否 | 区间开始，季榜可为 `yyyy-Qn` |
| endRange | string | 否 | 区间结束，季榜可为 `yyyy-Qn` |
| extra | object | 否 | 同通用说明 |

---

## 6. 行业趋势（industryTrendRange）

**POST** `/api/mengla/industry-trend`

### 请求体参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| product_id | string | 否 | 同通用说明 |
| catId | string | 否 | 同通用说明 |
| dateType | string | 否 | 趋势粒度：`DAY`、`MONTH`、`QUARTER`、`YEAR` |
| timest | string | 否 | 可选，通常与 endRange 一致 |
| starRange | string | 否 | **建议传** 起止日期/区间开始，如 `yyyy-MM-dd` |
| endRange | string | 否 | **建议传** 起止日期/区间结束，如 `yyyy-MM-dd` |
| extra | object | 否 | 同通用说明 |

说明：行业趋势按颗粒存储（各天/各月等），请求时传 `dateType` + `starRange`、`endRange` 确定查询范围。

---

## 响应与错误

- **成功**：HTTP 200，响应体为解包后的业务 JSON；响应头 `X-MengLa-Source` 为 `mongo`、`redis` 或 `fresh`。
- **400**：如 catId 不在类目列表中。
- **503**：采集服务不可达。
- **504**：请求或采集超时。
- **500**：服务端异常，body 为错误信息。
