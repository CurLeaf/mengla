import type { PeriodType } from "../../RankPeriodSelector";
import { getDefaultTrendRangeForPeriod } from "../../TrendPeriodRangeSelector";

export const GRANULARITY_OPTIONS: { value: string; label: string; period: PeriodType }[] = [
  { value: "day", label: "日", period: "update" },
  { value: "month", label: "月", period: "month" },
  { value: "quarter", label: "季", period: "quarter" },
  { value: "year", label: "年", period: "year" },
];

export const ACTION_OPTIONS = [
  { value: "high", label: "蓝海Top" },
  { value: "hot", label: "热销Top" },
  { value: "chance", label: "潜力Top" },
  { value: "industryViewV2", label: "行业区间" },
  { value: "industryTrendRange", label: "行业趋势" },
];

export const NON_TREND_ACTIONS = ["high", "hot", "chance", "industryViewV2"];

export const QUARTER_OPTIONS = [
  { value: "Q1", label: "Q1" },
  { value: "Q2", label: "Q2" },
  { value: "Q3", label: "Q3" },
  { value: "Q4", label: "Q4" },
];

export function getDefaultRangeForGranularity(granularity: string): { start: string; end: string } {
  const period = GRANULARITY_OPTIONS.find((g) => g.value === granularity)?.period ?? "month";
  return getDefaultTrendRangeForPeriod(period);
}
