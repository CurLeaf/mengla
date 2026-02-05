/**
 * 前端模拟数据
 * 包含所有页面所需的模拟数据
 */

import type { CategoryList } from "../types/category";
import type { PanelConfig } from "../types/panel-config";
import type {
  HighListRow,
  TrendPoint,
  RangeItem,
  IndustryViewData,
} from "../types/mengla";

// ============================================================================
// 1. 类目数据 (Categories)
// ============================================================================
export const mockCategories: CategoryList = [
  {
    catId: 17027494,
    catName: "Women's Clothing",
    catNameCn: "女装",
    children: [
      { catId: 17027495, catName: "Dresses", catNameCn: "连衣裙" },
      { catId: 17027496, catName: "T-Shirts", catNameCn: "T恤" },
      { catId: 17027497, catName: "Pants", catNameCn: "裤子" },
      { catId: 17027498, catName: "Skirts", catNameCn: "裙子" },
    ],
  },
  {
    catId: 17027500,
    catName: "Men's Clothing",
    catNameCn: "男装",
    children: [
      { catId: 17027501, catName: "Shirts", catNameCn: "衬衫" },
      { catId: 17027502, catName: "Jackets", catNameCn: "夹克" },
      { catId: 17027503, catName: "Jeans", catNameCn: "牛仔裤" },
    ],
  },
  {
    catId: 17027510,
    catName: "Electronics",
    catNameCn: "电子产品",
    children: [
      { catId: 17027511, catName: "Phones", catNameCn: "手机" },
      { catId: 17027512, catName: "Tablets", catNameCn: "平板电脑" },
      { catId: 17027513, catName: "Accessories", catNameCn: "配件" },
    ],
  },
  {
    catId: 17027520,
    catName: "Home & Garden",
    catNameCn: "家居园艺",
    children: [
      { catId: 17027521, catName: "Furniture", catNameCn: "家具" },
      { catId: 17027522, catName: "Decor", catNameCn: "装饰品" },
      { catId: 17027523, catName: "Kitchen", catNameCn: "厨房用品" },
    ],
  },
];

// ============================================================================
// 2. 面板配置 (Panel Config)
// ============================================================================
export const mockPanelConfig: PanelConfig = {
  modules: [
    { id: "overview", name: "行业总览", enabled: true, order: 1 },
    { id: "high", name: "蓝海Top行业", enabled: true, order: 2 },
    { id: "hot", name: "热销Top行业", enabled: true, order: 3 },
    { id: "chance", name: "潜力Top行业", enabled: true, order: 4 },
  ],
  layout: {
    defaultPeriod: "month",
    showRankPeriodSelector: true,
  },
};

// ============================================================================
// 3. 行业趋势数据 (industryTrendRange)
// ============================================================================
function generateTrendPoints(days: number = 30): TrendPoint[] {
  const points: TrendPoint[] = [];
  const baseDate = new Date();
  baseDate.setDate(baseDate.getDate() - days);

  for (let i = 0; i < days; i++) {
    const date = new Date(baseDate);
    date.setDate(date.getDate() + i);
    const dateStr = date.toISOString().split("T")[0];

    // 生成有波动的数据
    const baseSales = 50000 + Math.random() * 20000;
    const baseGmv = baseSales * (15 + Math.random() * 10);
    const trend = 1 + (i / days) * 0.2; // 整体上升趋势

    points.push({
      timest: dateStr,
      salesSkuCount: Math.floor(1000 + Math.random() * 500),
      monthSales: Math.floor(baseSales * trend * (0.9 + Math.random() * 0.2)),
      monthGmv: Math.floor(baseGmv * trend * (0.9 + Math.random() * 0.2)),
      currentDayPrice: parseFloat((15 + Math.random() * 10).toFixed(2)),
    });
  }

  return points;
}

export const mockTrendData = {
  industryTrendRange: {
    data: generateTrendPoints(30),
  },
};

// ============================================================================
// 4. 行业区间分布数据 (industryViewV2)
// ============================================================================
const mockSalesRangeList: RangeItem[] = [
  { id: 1, title: "0-10", itemCount: 1500, sales: 8000, gmv: 120000, itemCountRate: 0.15, salesRate: 0.08, gmvRate: 0.06 },
  { id: 2, title: "10-50", itemCount: 3200, sales: 45000, gmv: 900000, itemCountRate: 0.32, salesRate: 0.25, gmvRate: 0.20 },
  { id: 3, title: "50-100", itemCount: 2800, sales: 85000, gmv: 1700000, itemCountRate: 0.28, salesRate: 0.30, gmvRate: 0.28 },
  { id: 4, title: "100-500", itemCount: 1800, sales: 70000, gmv: 1400000, itemCountRate: 0.18, salesRate: 0.25, gmvRate: 0.30 },
  { id: 5, title: "500+", itemCount: 700, sales: 32000, gmv: 960000, itemCountRate: 0.07, salesRate: 0.12, gmvRate: 0.16 },
];

const mockGmvRangeList: RangeItem[] = [
  { id: 1, title: "$0-100", itemCount: 2000, sales: 12000, gmv: 80000, itemCountRate: 0.20, salesRate: 0.10, gmvRate: 0.04 },
  { id: 2, title: "$100-500", itemCount: 3500, sales: 55000, gmv: 550000, itemCountRate: 0.35, salesRate: 0.28, gmvRate: 0.15 },
  { id: 3, title: "$500-1K", itemCount: 2500, sales: 60000, gmv: 900000, itemCountRate: 0.25, salesRate: 0.30, gmvRate: 0.25 },
  { id: 4, title: "$1K-5K", itemCount: 1500, sales: 45000, gmv: 1200000, itemCountRate: 0.15, salesRate: 0.22, gmvRate: 0.35 },
  { id: 5, title: "$5K+", itemCount: 500, sales: 18000, gmv: 720000, itemCountRate: 0.05, salesRate: 0.10, gmvRate: 0.21 },
];

const mockPriceRangeList: RangeItem[] = [
  { id: 1, title: "$0-5", itemCount: 1800, sales: 35000, gmv: 100000, itemCountRate: 0.18, salesRate: 0.18, gmvRate: 0.05 },
  { id: 2, title: "$5-10", itemCount: 2800, sales: 55000, gmv: 400000, itemCountRate: 0.28, salesRate: 0.28, gmvRate: 0.12 },
  { id: 3, title: "$10-20", itemCount: 3000, sales: 60000, gmv: 900000, itemCountRate: 0.30, salesRate: 0.30, gmvRate: 0.28 },
  { id: 4, title: "$20-50", itemCount: 1800, sales: 35000, gmv: 1000000, itemCountRate: 0.18, salesRate: 0.18, gmvRate: 0.32 },
  { id: 5, title: "$50+", itemCount: 600, sales: 12000, gmv: 720000, itemCountRate: 0.06, salesRate: 0.06, gmvRate: 0.23 },
];

const mockBrandRateList: RangeItem[] = [
  { id: 1, title: "无品牌", itemCount: 4500, sales: 90000, gmv: 1350000, itemCountRate: 0.45, salesRate: 0.45, gmvRate: 0.35 },
  { id: 2, title: "小品牌", itemCount: 3000, sales: 60000, gmv: 1080000, itemCountRate: 0.30, salesRate: 0.30, gmvRate: 0.28 },
  { id: 3, title: "中等品牌", itemCount: 1800, sales: 36000, gmv: 900000, itemCountRate: 0.18, salesRate: 0.18, gmvRate: 0.23 },
  { id: 4, title: "知名品牌", itemCount: 700, sales: 14000, gmv: 540000, itemCountRate: 0.07, salesRate: 0.07, gmvRate: 0.14 },
];

export const mockIndustryViewData: IndustryViewData = {
  industrySalesRangeDtoList: mockSalesRangeList,
  industryGmvRangeDtoList: mockGmvRangeList,
  industryPriceRangeDtoList: mockPriceRangeList,
  industryBrandRateDtoList: mockBrandRateList,
};

export const mockIndustryViewResponse = {
  industryViewV2List: {
    data: mockIndustryViewData,
  },
};

// ============================================================================
// 5. 蓝海/热销/潜力 行业列表数据 (high/hot/chance)
// ============================================================================
function generateIndustryList(count: number = 20, type: "high" | "hot" | "chance"): HighListRow[] {
  const categoryNames = [
    { en: "Summer Dresses", cn: "夏季连衣裙" },
    { en: "Phone Cases", cn: "手机壳" },
    { en: "LED Lights", cn: "LED灯" },
    { en: "Yoga Pants", cn: "瑜伽裤" },
    { en: "Wireless Earbuds", cn: "无线耳机" },
    { en: "Kitchen Gadgets", cn: "厨房小工具" },
    { en: "Pet Supplies", cn: "宠物用品" },
    { en: "Makeup Brushes", cn: "化妆刷" },
    { en: "Baby Clothes", cn: "婴儿服装" },
    { en: "Smart Watches", cn: "智能手表" },
    { en: "Camping Gear", cn: "露营装备" },
    { en: "Hair Accessories", cn: "发饰" },
    { en: "Sports Shoes", cn: "运动鞋" },
    { en: "Home Decor", cn: "家居装饰" },
    { en: "Jewelry Sets", cn: "首饰套装" },
    { en: "Laptop Bags", cn: "笔记本包" },
    { en: "Garden Tools", cn: "园艺工具" },
    { en: "Kids Toys", cn: "儿童玩具" },
    { en: "Fitness Equipment", cn: "健身器材" },
    { en: "Car Accessories", cn: "汽车配件" },
  ];

  const list: HighListRow[] = [];

  for (let i = 0; i < count; i++) {
    const cat = categoryNames[i % categoryNames.length];
    const baseMultiplier = type === "hot" ? 2 : type === "chance" ? 1.5 : 1;

    list.push({
      catId1: 17027494 + i,
      catId2: 17027500 + i,
      catId3: 17027600 + i,
      catName: cat.en,
      catNameCn: cat.cn,
      catTag: Math.floor(Math.random() * 5),
      skuNum: Math.floor(5000 + Math.random() * 15000),
      saleSkuNum: Math.floor(1000 + Math.random() * 8000),
      saleRatio: parseFloat((0.2 + Math.random() * 0.6).toFixed(4)),
      monthSales: Math.floor(10000 * baseMultiplier + Math.random() * 50000 * baseMultiplier),
      monthSalesRating: parseFloat((0.05 + Math.random() * 0.3).toFixed(4)),
      monthGmv: Math.floor(200000 * baseMultiplier + Math.random() * 1000000 * baseMultiplier),
      monthGmvRmb: Math.floor(1400000 * baseMultiplier + Math.random() * 7000000 * baseMultiplier),
      monthGmvRating: parseFloat((0.03 + Math.random() * 0.2).toFixed(4)),
      brandGmvRating: parseFloat((0.1 + Math.random() * 0.4).toFixed(4)),
      topGmvRating: parseFloat((0.05 + Math.random() * 0.25).toFixed(4)),
    });
  }

  // 按月销量降序排序
  return list.sort((a, b) => (b.monthSales ?? 0) - (a.monthSales ?? 0));
}

export const mockHighList: HighListRow[] = generateIndustryList(20, "high");
export const mockHotList: HighListRow[] = generateIndustryList(20, "hot");
export const mockChanceList: HighListRow[] = generateIndustryList(20, "chance");

export const mockHighResponse = {
  highList: {
    code: 0,
    data: {
      list: mockHighList,
    },
  },
};

export const mockHotResponse = {
  hotList: {
    code: 0,
    data: {
      list: mockHotList,
    },
  },
};

export const mockChanceResponse = {
  chanceList: {
    code: 0,
    data: {
      list: mockChanceList,
    },
  },
};

// ============================================================================
// 6. 任务列表 (Panel Tasks)
// ============================================================================
export interface PanelTask {
  id: string;
  name: string;
  description: string;
}

export const mockPanelTasks: PanelTask[] = [
  {
    id: "mengla_granular",
    name: "MengLa 日/月/季/年补齐",
    description: "对 high/hot/chance/industryViewV2/industryTrendRange 按当日颗粒度补齐",
  },
  {
    id: "mengla_single_day",
    name: "MengLa 单日补齐",
    description: "同上，仅针对当日 period_key 各接口触发一次",
  },
  {
    id: "daily_collect",
    name: "每日主采集",
    description: "采集当天的 day 颗粒度数据",
  },
  {
    id: "monthly_collect",
    name: "月度采集",
    description: "采集当月的 month 颗粒度数据",
  },
  {
    id: "quarterly_collect",
    name: "季度采集",
    description: "采集当季的 quarter 颗粒度数据",
  },
  {
    id: "yearly_collect",
    name: "年度采集",
    description: "采集当年的 year 颗粒度数据",
  },
  {
    id: "backfill_check",
    name: "补数检查",
    description: "检查最近数据是否有缺失，触发补采",
  },
];

// ============================================================================
// 7. MengLa 数据状态 (Admin - 数据状态检查)
// ============================================================================
export interface MengLaStatusResponse {
  catId?: string | null;
  granularity: string;
  startDate: string;
  endDate: string;
  status: Record<string, Record<string, boolean>>;
}

export function generateMockStatus(
  startDate: string,
  endDate: string,
  granularity: string
): MengLaStatusResponse {
  const actions = ["high", "hot", "chance", "industryViewV2", "industryTrendRange"];
  const status: Record<string, Record<string, boolean>> = {};

  // 生成日期范围内的 period keys
  const start = new Date(startDate);
  const end = new Date(endDate);
  const keys: string[] = [];

  if (granularity === "day") {
    const current = new Date(start);
    while (current <= end) {
      keys.push(current.toISOString().split("T")[0].replace(/-/g, ""));
      current.setDate(current.getDate() + 1);
    }
  } else if (granularity === "month") {
    const current = new Date(start);
    while (current <= end) {
      keys.push(`${current.getFullYear()}${String(current.getMonth() + 1).padStart(2, "0")}`);
      current.setMonth(current.getMonth() + 1);
    }
  }

  for (const action of actions) {
    status[action] = {};
    for (const key of keys) {
      // 随机生成数据存在状态（80% 概率存在）
      status[action][key] = Math.random() > 0.2;
    }
  }

  return {
    catId: null,
    granularity,
    startDate,
    endDate,
    status,
  };
}

// ============================================================================
// 8. 统一的模拟数据查询函数
// ============================================================================
export function getMockDataByAction(action: string): unknown {
  switch (action) {
    case "industryTrendRange":
      return mockTrendData;
    case "industryViewV2":
      return mockIndustryViewResponse;
    case "high":
      return mockHighResponse;
    case "hot":
      return mockHotResponse;
    case "chance":
      return mockChanceResponse;
    default:
      return null;
  }
}

// ============================================================================
// 导出所有模拟数据
// ============================================================================
export const mockData = {
  categories: mockCategories,
  panelConfig: mockPanelConfig,
  trendData: mockTrendData,
  industryViewData: mockIndustryViewResponse,
  highList: mockHighResponse,
  hotList: mockHotResponse,
  chanceList: mockChanceResponse,
  panelTasks: mockPanelTasks,
};

export default mockData;
