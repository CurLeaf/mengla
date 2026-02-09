import { format, subDays, subMonths, subQuarters, subYears } from "date-fns";
import { useCallback, useMemo, useState } from "react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Select } from "./ui/select";

export type PeriodType = "update" | "month" | "quarter" | "year";

export function getDefaultTimestForPeriod(period: PeriodType): string {
  const now = new Date();
  switch (period) {
    case "update": {
      const y = subDays(now, 1);
      return format(y, "yyyy-MM-dd");
    }
    case "month": {
      const lastMonth = subMonths(now, 1);
      return format(lastMonth, "yyyy-MM");
    }
    case "quarter": {
      const lastQ = subQuarters(now, 1);
      const q = Math.ceil((lastQ.getMonth() + 1) / 3);
      return `${lastQ.getFullYear()}-Q${q}`;
    }
    case "year":
      return String(subYears(now, 1).getFullYear());
    default:
      return format(now, "yyyy-MM-dd");
  }
}

/**
 * 各 tab 对应请求的 dateType（大写，与后端/采集 API 一致）：
 * - 更新日期 → DAY
 * - 月榜 → MONTH
 * - 季榜 → QUARTER
 * - 年榜 → YEAR
 */
export function periodToDateType(period: PeriodType): string {
  if (period === "update") return "DAY";
  return period.toUpperCase();
}

const PERIODS: { value: PeriodType; label: string }[] = [
  { value: "update", label: "更新日期" },
  { value: "month", label: "月榜" },
  { value: "quarter", label: "季榜" },
  { value: "year", label: "年榜" },
];

function parseMonthTimest(timest: string): { year: number; month: number } {
  const now = new Date();
  const defaultYear = now.getFullYear();
  const defaultMonth = now.getMonth() + 1;
  if (!timest || !timest.includes("-"))
    return { year: defaultYear, month: defaultMonth };
  const parts = timest.split("-").map(Number);
  const y = parts[0] ?? defaultYear;
  const m = parts[1] ?? defaultMonth;
  return {
    year: Number.isNaN(y) ? defaultYear : y,
    month: Number.isNaN(m) ? defaultMonth : m,
  };
}

function parseQuarterTimest(timest: string): {
  year: number;
  quarter: string;
} {
  const now = new Date();
  const defaultYear = now.getFullYear();
  const defaultQ = `Q${Math.ceil((now.getMonth() + 1) / 3)}`;
  if (!timest || !timest.includes("-"))
    return { year: defaultYear, quarter: defaultQ };
  const [y, q] = timest.split("-");
  const year = Number(y);
  const quarter =
    q === "Q1" || q === "Q2" || q === "Q3" || q === "Q4" ? q : defaultQ;
  return { year: Number.isNaN(year) ? defaultYear : year, quarter };
}

function parseYearTimest(timest: string): string {
  const now = new Date().getFullYear();
  if (!timest) return String(now);
  const y = Number(timest);
  return Number.isNaN(y) ? String(now) : String(y);
}

const QUARTER_OPTIONS = [
  { value: "Q1", label: "第一季度" },
  { value: "Q2", label: "第二季度" },
  { value: "Q3", label: "第三季度" },
  { value: "Q4", label: "第四季度" },
];

interface RankPeriodSelectorProps {
  selectedPeriod?: PeriodType;
  selectedTimest?: string;
  onPeriodChange?: (period: PeriodType) => void;
  onTimestChange?: (timest: string) => void;
}

export function RankPeriodSelector({
  selectedPeriod = "month",
  selectedTimest,
  onPeriodChange,
  onTimestChange,
}: RankPeriodSelectorProps) {
  const [internalPeriod, setInternalPeriod] = useState<PeriodType>("month");
  const [internalTimest, setInternalTimest] = useState(() =>
    getDefaultTimestForPeriod("month")
  );

  const isControlled =
    selectedPeriod !== undefined && selectedTimest !== undefined;
  const period = isControlled ? selectedPeriod : internalPeriod;
  const timest = isControlled ? selectedTimest! : internalTimest;

  const handlePeriodChange = useCallback(
    (p: PeriodType) => {
      const nextTimest = getDefaultTimestForPeriod(p);
      if (isControlled) {
        onPeriodChange?.(p);
        onTimestChange?.(nextTimest);
      } else {
        setInternalPeriod(p);
        setInternalTimest(nextTimest);
      }
    },
    [isControlled, onPeriodChange, onTimestChange]
  );

  const handleTimestChange = useCallback(
    (t: string) => {
      if (isControlled) onTimestChange?.(t);
      else setInternalTimest(t);
    },
    [isControlled, onTimestChange]
  );

  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;
  const currentQuarter = `Q${Math.ceil((now.getMonth() + 1) / 3)}`;

  const yearOptions = useMemo(
    () => Array.from({ length: 6 }, (_, i) => currentYear - i),
    [currentYear]
  );
  const monthOptions = useMemo(
    () => Array.from({ length: 12 }, (_, i) => i + 1),
    []
  );

  const dateValue =
    period === "update" && timest.length >= 10
      ? timest.slice(0, 10)
      : period === "month" && timest.length >= 7
        ? `${timest}-01`
        : "";

  const renderDateSelector = () => {
    switch (period) {
      case "update":
        return (
          <Input
            type="date"
            className="w-auto"
            value={dateValue}
            max={format(subDays(now, 1), "yyyy-MM-dd")}
            onChange={(e) => handleTimestChange(e.target.value)}
            aria-label="日期"
            title="选择日期（仅可选昨天及以前）"
          />
        );
      case "month": {
        const { year, month } = parseMonthTimest(timest);
        return (
          <div className="flex items-center gap-2">
            <Select
              className="w-auto"
              value={String(year)}
              onChange={(e) =>
                handleTimestChange(
                  `${e.target.value}-${String(month).padStart(2, "0")}`
                )
              }
              aria-label="年"
            >
              {yearOptions.map((y) => (
                <option key={y} value={y}>
                  {y}年
                </option>
              ))}
            </Select>
            <Select
              className="w-auto"
              value={String(month)}
              onChange={(e) =>
                handleTimestChange(
                  `${year}-${String(e.target.value).padStart(2, "0")}`
                )
              }
              aria-label="月"
            >
              {monthOptions.map((m) => {
                const isCurrentMonth = year === currentYear && m === currentMonth;
                return (
                  <option
                    key={m}
                    value={m}
                    disabled={isCurrentMonth}
                    className="bg-muted text-foreground"
                  >
                    {m}月
                  </option>
                );
              })}
            </Select>
          </div>
        );
      }
      case "quarter": {
        const { year, quarter } = parseQuarterTimest(timest);
        return (
          <div className="flex items-center gap-2">
            <Select
              className="w-auto"
              value={String(year)}
              onChange={(e) => handleTimestChange(`${e.target.value}-${quarter}`)}
              aria-label="年"
            >
              {yearOptions.map((y) => (
                <option key={y} value={y}>
                  {y}年
                </option>
              ))}
            </Select>
            <Select
              className="w-auto"
              value={quarter}
              onChange={(e) => handleTimestChange(`${year}-${e.target.value}`)}
              aria-label="季"
            >
              {QUARTER_OPTIONS.map((q) => {
                const isCurrentQuarter =
                  year === currentYear && q.value === currentQuarter;
                return (
                  <option
                    key={q.value}
                    value={q.value}
                    disabled={isCurrentQuarter}
                    className="bg-muted text-foreground"
                  >
                    {q.label}
                  </option>
                );
              })}
            </Select>
          </div>
        );
      }
      case "year":
        return (
          <Select
            className="w-auto"
            value={parseYearTimest(timest)}
            onChange={(e) => handleTimestChange(e.target.value)}
            aria-label="年"
          >
            {yearOptions.map((y) => {
              const isCurrentYear = y === currentYear;
              return (
                <option
                  key={y}
                  value={y}
                  disabled={isCurrentYear}
                  className="bg-muted text-foreground"
                >
                  {y}年
                </option>
              );
            })}
          </Select>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* 周期 Tab：使用 Button 组件，通过 variant 切换激活状态 */}
      <div className="flex items-center gap-1 rounded-lg border border-border p-0.5">
        {PERIODS.map((p) => (
          <Button
            key={p.value}
            type="button"
            variant={period === p.value ? "default" : "outline"}
            size="xs"
            onClick={() => handlePeriodChange(p.value)}
            aria-label={p.label}
            aria-pressed={period === p.value}
          >
            {p.label}
          </Button>
        ))}
      </div>

      <span
        className="text-xs text-muted-foreground"
        title="选择不同的时间维度查看数据"
      >
        时间
      </span>

      {renderDateSelector()}
    </div>
  );
}
