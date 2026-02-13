import { useMemo } from "react";
import { periodToDateType, type PeriodType } from "../components/RankPeriodSelector";
import type {
  HighListRow,
  IndustryView,
  MenglaResponseData,
  TrendPoint,
} from "../types/mengla";

/** 季度 timest 规范为 yyyy-Qn（采集 API 要求） */
export function normalizeQuarterTimest(timest: string): string {
  const s = (timest || "").trim();
  if (/^\d{4}-Q[1-4]$/i.test(s)) return s;
  const m = s.match(/^(\d{4})Q?([1-4])$/i);
  if (m) return `${m[1]}-Q${m[2]}`;
  return s;
}

/** 按当前选中的周期生成请求参数 */
export function buildQueryParams(
  action: string,
  primaryCatId: string,
  period: PeriodType,
  timest: string
) {
  const isViewV2Quarter =
    action === "industryViewV2" && period === "quarter";
  const dateType = isViewV2Quarter
    ? "QUARTERLY_FOR_YEAR"
    : periodToDateType(period);
  const normalizedTimest =
    isViewV2Quarter ? normalizeQuarterTimest(timest) : timest;
  return {
    action,
    product_id: "",
    catId: primaryCatId,
    dateType,
    timest: normalizedTimest,
    starRange: normalizedTimest,
    endRange: normalizedTimest,
  };
}

/** 行业趋势请求参数 */
export function buildTrendQueryParams(
  action: string,
  primaryCatId: string,
  trendPeriod: PeriodType,
  starRange: string,
  endRange: string
) {
  return {
    action,
    product_id: "",
    catId: primaryCatId,
    dateType: periodToDateType(trendPeriod),
    timest: endRange,
    starRange,
    endRange,
  };
}

/** 递归解包采集平台返回的 resultData */
export function pickPayload(raw: unknown): MenglaResponseData | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  let payload: unknown = o.resultData ?? o.data ?? o;
  while (payload && typeof payload === "object" && "resultData" in payload) {
    const inner = (payload as Record<string, unknown>).resultData;
    if (!inner) break;
    payload = inner;
  }
  return payload as MenglaResponseData | undefined;
}

/** 从趋势响应数据中提取 TrendPoint[] */
export function useTrendPoints(trendData: MenglaResponseData | undefined): TrendPoint[] {
  return useMemo(() => {
    if (!trendData) return [];
    const inj = trendData?.injectedVars && typeof trendData.injectedVars === "object" ? trendData.injectedVars as Record<string, unknown> : null;
    const injIr = inj?.industryTrendRange as { data?: unknown } | unknown[] | undefined;
    const raw =
      trendData?.industryTrendRange?.data ??
      (Array.isArray(trendData?.industryTrendRange) ? trendData.industryTrendRange : null) ??
      trendData?.data ??
      (injIr && typeof injIr === "object" && !Array.isArray(injIr) && "data" in injIr ? injIr.data : null) ??
      (Array.isArray(injIr) ? injIr : null) ??
      inj?.data ??
      [];
    return (Array.isArray(raw) ? raw : []) as TrendPoint[];
  }, [trendData]);
}

/** 从 industryViewV2 响应中提取 IndustryView */
export function useIndustryView(viewData: MenglaResponseData | undefined): IndustryView | null {
  return useMemo((): IndustryView | null => {
    if (!viewData) return null;
    
    // 尝试多种可能的数据路径
    const v2List = viewData?.industryViewV2List;
    const v2 = viewData?.industryViewV2;
    
    // industryViewV2List.data 是最常见的结构
    if (v2List && typeof v2List === "object") {
      const v2ListRecord = v2List as Record<string, unknown>;
      if ("data" in v2ListRecord && v2ListRecord.data) {
        return { data: v2ListRecord.data as IndustryView["data"] };
      }
      // 直接就是数据对象
      if ("industrySalesRangeDtoList" in v2ListRecord || "industryGmvRangeDtoList" in v2ListRecord) {
        return { data: v2List as IndustryView["data"] };
      }
    }
    
    // industryViewV2 路径
    if (v2 && typeof v2 === "object") {
      const v2Record = v2 as Record<string, unknown>;
      if ("data" in v2Record && v2Record.data) {
        return { data: v2Record.data as IndustryView["data"] };
      }
      if ("industrySalesRangeDtoList" in v2Record || "industryGmvRangeDtoList" in v2Record) {
        return { data: v2 as IndustryView["data"] };
      }
    }
    
    // 直接在 viewData 上
    if ("industrySalesRangeDtoList" in viewData || "industryGmvRangeDtoList" in viewData) {
      return { data: viewData as unknown as IndustryView["data"] };
    }
    
    // 兜底：viewData.data
    if ("data" in viewData && viewData.data && typeof viewData.data === "object") {
      const dataRecord = viewData.data as Record<string, unknown>;
      if ("industrySalesRangeDtoList" in dataRecord || "industryGmvRangeDtoList" in dataRecord) {
        return { data: viewData.data as IndustryView["data"] };
      }
    }
    
    return null;
  }, [viewData]);
}

/** 从 high/hot/chance 响应中提取列表 */
export function useRankList(
  rawData: MenglaResponseData | undefined,
  listKey: "highList" | "hotList" | "chanceList"
): HighListRow[] {
  return useMemo(() => {
    if (!rawData) return [];
    const hl = (rawData as Record<string, unknown>)?.[listKey] as Record<string, unknown> | undefined;
    const data = hl?.data;
    const list =
      (Array.isArray(data) ? data : null) ??
      (data && typeof data === "object" && "list" in data ? (data as { list: unknown }).list : null) ??
      hl?.list ??
      rawData?.list ??
      (Array.isArray(rawData?.data) ? rawData.data : null);
    return (Array.isArray(list) ? list : []) as HighListRow[];
  }, [rawData, listKey]);
}
