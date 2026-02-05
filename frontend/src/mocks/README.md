# 模拟数据说明

本目录包含前端开发所需的所有模拟数据，可在无后端服务的情况下进行前端开发和测试。

## 文件结构

```
mocks/
├── mock-data.ts   # 模拟数据定义
├── mock-api.ts    # 模拟 API 服务
└── README.md      # 本文件
```

## 包含的模拟数据

### 1. 类目数据 (Categories)
- `mockCategories` - 包含 4 个一级类目，每个有 3-4 个子类目

### 2. 面板配置 (Panel Config)
- `mockPanelConfig` - 模块配置和布局配置

### 3. 行业趋势数据 (industryTrendRange)
- `mockTrendData` - 30天的趋势数据点
- 包含：销量、GMV、价格等指标

### 4. 行业区间分布 (industryViewV2)
- `mockIndustryViewResponse` - 四种区间分布
  - 销量区间 (industrySalesRangeDtoList)
  - GMV区间 (industryGmvRangeDtoList)
  - 价格区间 (industryPriceRangeDtoList)
  - 品牌占比 (industryBrandRateDtoList)

### 5. 行业排行榜 (high/hot/chance)
- `mockHighResponse` - 蓝海 Top 行业 (20条)
- `mockHotResponse` - 热销 Top 行业 (20条)
- `mockChanceResponse` - 潜力 Top 行业 (20条)

### 6. 任务列表 (Panel Tasks)
- `mockPanelTasks` - 7 个采集任务

## 使用方法

### 方法一：直接导入模拟数据

```typescript
import { mockCategories, mockTrendData, mockHighList } from './mocks/mock-data';

// 直接使用
console.log(mockCategories);
console.log(mockTrendData.industryTrendRange.data);
```

### 方法二：使用模拟 API

```typescript
import { 
  mockFetchCategories, 
  mockQueryMengla,
  mockFetchPanelTasks 
} from './mocks/mock-api';

// 异步调用（带模拟延迟）
const categories = await mockFetchCategories();
const trendData = await mockQueryMengla({ action: 'industryTrendRange', catId: '17027494' });
```

### 方法三：环境变量控制

1. 在 `.env.local` 中设置：
```env
VITE_USE_MOCK_DATA=true
```

2. 使用 `withMock` 条件函数：
```typescript
import { withMock, mockQueryMengla } from './mocks/mock-api';
import { queryMengla as realQueryMengla } from './services/mengla-api';

const data = await withMock(
  () => mockQueryMengla(params),
  () => realQueryMengla(params)
);
```

## 数据结构示例

### 趋势数据点 (TrendPoint)
```json
{
  "timest": "2026-02-01",
  "salesSkuCount": 1234,
  "monthSales": 56789,
  "monthGmv": 1234567,
  "currentDayPrice": 21.50
}
```

### 行业列表项 (HighListRow)
```json
{
  "catId1": 17027494,
  "catName": "Summer Dresses",
  "catNameCn": "夏季连衣裙",
  "skuNum": 15000,
  "saleSkuNum": 8000,
  "saleRatio": 0.5333,
  "monthSales": 65000,
  "monthGmv": 1250000,
  "brandGmvRating": 0.35
}
```

### 区间项 (RangeItem)
```json
{
  "id": 1,
  "title": "0-10",
  "itemCount": 1500,
  "sales": 8000,
  "gmv": 120000,
  "itemCountRate": 0.15,
  "salesRate": 0.08,
  "gmvRate": 0.06
}
```

## 自定义模拟数据

可以通过修改 `mock-data.ts` 中的生成函数来自定义数据：

```typescript
// 生成更多天数的趋势数据
const customTrendPoints = generateTrendPoints(60);

// 生成更多行业列表
const customHighList = generateIndustryList(50, 'high');
```
