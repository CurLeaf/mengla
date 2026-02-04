/** 萌拉查询请求参数 */
export interface MenglaQueryParams {
  action: string;
  product_id?: string;
  catId?: string;
  dateType?: string;
  timest?: string;
  starRange?: string;
  endRange?: string;
  [key: string]: unknown;
}

/** 蓝海类目行 */
export interface HighListRow {
  catId1?: number;
  catId2?: number;
  catId3?: number;
  catName?: string;
  catNameCn?: string;
  catTag?: number;
  skuNum?: number;
  saleSkuNum?: number;
  saleRatio?: number;
  monthSales?: number;
  monthSalesRating?: number;
  monthGmv?: number;
  monthGmvRmb?: number;
  monthGmvRating?: number;
  brandGmvRating?: number;
  topGmvRating?: number;
  [key: string]: unknown;
}

/** 区间项（销量/GMV/价格/品牌） */
export interface RangeItem {
  id?: string | number;
  title?: string;
  itemCount?: number;
  sales?: number;
  gmv?: number;
  itemCountRate?: number;
  salesRate?: number;
  gmvRate?: number;
  [key: string]: unknown;
}

/** 行业区间 data */
export interface IndustryViewData {
  industrySalesRangeDtoList?: RangeItem[];
  industryGmvRangeDtoList?: RangeItem[];
  industryPriceRangeDtoList?: RangeItem[];
  industryBrandRateDtoList?: RangeItem[];
  [key: string]: unknown;
}

/** 行业区间视图 */
export interface IndustryView {
  data?: IndustryViewData;
  [key: string]: unknown;
}

/** 趋势点 */
export interface TrendPoint {
  timest?: string;
  salesSkuCount?: number;
  monthSales?: number;
  monthGmv?: number;
  currentDayPrice?: number;
  [key: string]: unknown;
}

/** 萌拉 API 返回 data 结构（按 action 不同而不同） */
export interface MenglaResponseData {
  highList?: { data?: { list?: HighListRow[] }; list?: HighListRow[] };
  hotList?: { data?: { list?: HighListRow[] }; list?: HighListRow[] };
  chanceList?: { data?: { list?: HighListRow[] }; list?: HighListRow[] };
  list?: HighListRow[];
  industryViewV2List?: IndustryView;
  industryTrendRange?: { data?: TrendPoint[] };
  data?: HighListRow[] | TrendPoint[];
  [key: string]: unknown;
}

/** 萌拉 API 响应 */
export interface MenglaQueryResponse {
  data?: MenglaResponseData;
  [key: string]: unknown;
}
