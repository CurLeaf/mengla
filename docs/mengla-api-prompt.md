# 萌拉接口提示词（API 调用说明）

可直接复制给前端/联调方或作为接口提示词使用。

---

## 数据查询顺序（所有接口一致）

1. **MongoDB** → 2. **Redis** → 3. **采集服务（Cache）**  
未命中前一级时再查下一级；命中即返回。响应头 `X-MengLa-Source` 表示来源：`mongo` | `redis` | `fresh`。

---

## 通用请求体字段（JSON）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| product_id | string | 否 | 产品 ID，默认 "" |
| catId | string | 否 | 类目 ID，须在 类目.json 中；传一级品类时响应会带该一级下的二级品类列表 `secondaryCategories` |
| dateType | string | 否 | 时间粒度：DAY / MONTH / QUARTER / YEAR |
| timest | string | 否 | 时间点：日 yyyy-MM-dd、月 yyyy-MM、季 yyyy-Qn、年 yyyy |
| starRange | string | 否 | 区间开始（趋势/行业区间用） |
| endRange | string | 否 | 区间结束 |
| extra | object | 否 | 扩展参数 |

---

## 响应说明

- 成功：HTTP 200，body 为业务 JSON；当请求带了 **catId（一级品类）** 时，响应会多一个 **`secondaryCategories`** 数组，为该一级下的二级品类列表（来自 类目.json 的 children），便于前端展示或按二级再请求。
- 响应头：`X-MengLa-Source` 表示数据来源（mongo / redis / fresh）。

---

## 接口列表

### 1. 统一查询（通过 action 区分类型）

- **POST** `/api/mengla/query`
- **请求体**：在通用字段基础上增加 **`action`**（必填），取值：`high` | `hot` | `chance` | `industryViewV2` | `industryTrendRange`
- **用途**：一个接口覆盖五种业务，由 action 决定返回蓝海/热销/潜力/行业区间/行业趋势

---

### 2. 蓝海 Top 行业

- **POST** `/api/mengla/high`
- **请求体**：仅通用字段（无 action），常用 `dateType`、`timest`、`catId`
- **用途**：蓝海 Top 行业数据

---

### 3. 热销 Top 行业

- **POST** `/api/mengla/hot`
- **请求体**：仅通用字段，常用 `dateType`、`timest`、`catId`
- **用途**：热销 Top 行业数据

---

### 4. 潜力 Top 行业

- **POST** `/api/mengla/chance`
- **请求体**：仅通用字段，常用 `dateType`、`timest`、`catId`
- **用途**：潜力 Top 行业数据

---

### 5. 行业区间/总览

- **POST** `/api/mengla/industry-view`
- **请求体**：通用字段，常用 `dateType`、`timest`、`starRange`、`endRange`、`catId`；季榜可用 dateType=QUARTERLY_FOR_YEAR、timest/starRange/endRange 为 yyyy-Qn
- **用途**：行业区间分布、行业总览（industryViewV2）

---

### 6. 行业趋势

- **POST** `/api/mengla/industry-trend`
- **请求体**：通用字段，**趋势必传时间范围**：`dateType`（DAY/MONTH/QUARTER/YEAR）、`starRange`、`endRange`（如 yyyy-MM-dd），`catId` 可选
- **用途**：行业趋势（industryTrendRange），按颗粒存储，请求范围内各时间点合并返回

---

## 错误码

- **400**：catId 不在类目列表中
- **503**：采集服务不可达
- **504**：请求或采集超时
- **500**：服务端异常

---

## 示例（cURL）

```bash
# 统一查询 - 蓝海、指定类目与日期
curl -X POST "http://localhost:8000/api/mengla/query" \
  -H "Content-Type: application/json" \
  -d '{"action":"high","catId":"17027494","dateType":"DAY","timest":"2025-02-01"}'

# 独立接口 - 蓝海
curl -X POST "http://localhost:8000/api/mengla/high" \
  -H "Content-Type: application/json" \
  -d '{"catId":"17027494","dateType":"MONTH","timest":"2025-01"}'

# 行业趋势 - 近一年
curl -X POST "http://localhost:8000/api/mengla/industry-trend" \
  -H "Content-Type: application/json" \
  -d '{"catId":"17027494","dateType":"DAY","starRange":"2025-01-01","endRange":"2025-12-31"}'
```

以上请求若带一级品类 `catId`，响应中会包含 `secondaryCategories`（该一级下的二级品类列表）。
