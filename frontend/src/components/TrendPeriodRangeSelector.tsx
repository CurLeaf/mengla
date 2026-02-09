import {
  endOfQuarter,
  format,
  lastDayOfMonth,
  startOfQuarter,
  subDays,
  subMonths,
  subQuarters,
  subYears,
} from "date-fns";
import { useCallback, useMemo } from "react";
import type { PeriodType } from "./RankPeriodSelector";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Select } from "./ui/select";

const PERIODS: { value: PeriodType; label: string }[] = [
  { value: "update", label: "更新日期" },
  { value: "month", label: "月榜" },
  { value: "quarter", label: "季榜" },
  { value: "year", label: "年榜" },
];

/** 各周期默认范围：更新日期=最近30天，月/季/年=上一周期起止相同 */
export function getDefaultTrendRangeForPeriod(
  period: PeriodType
): { start: string; end: string } {
  const now = new Date();
  let result: { start: string; end: string };
  switch (period) {
    case "update": {
      const yesterday = subDays(now, 1);
      const start = subDays(yesterday, 29);
      result = {
        start: format(start, "yyyy-MM-dd"),
        end: format(yesterday, "yyyy-MM-dd"),
      };
      break;
    }
    case "month": {
      const lastMonth = subMonths(now, 1);
      const m = format(lastMonth, "yyyy-MM");
      result = { start: m, end: m };
      break;
    }
    case "quarter": {
      const lastQ = subQuarters(now, 1);
      const q = Math.ceil((lastQ.getMonth() + 1) / 3);
      const s = `${lastQ.getFullYear()}-Q${q}`;
      result = { start: s, end: s };
      break;
    }
    case "year": {
      const y = String(subYears(now, 1).getFullYear());
      result = { start: y, end: y };
      break;
    }
    default:
      result = { start: format(now, "yyyy-MM-dd"), end: format(now, "yyyy-MM-dd") };
  }
  return result;
}

/** 将趋势范围（按周期格式）转为真实起止日期 yyyy-MM-dd，用于请求 */
export function trendRangeToDateRange(
  period: PeriodType,
  start: string,
  end: string
): { startDate: string; endDate: string } {
  if (period === "update") {
    return {
      startDate: start.slice(0, 10),
      endDate: end.slice(0, 10),
    };
  }
  if (period === "month") {
    const [sy, sm] = start.split("-").map(Number);
    const [ey, em] = end.split("-").map(Number);
    const startDate = new Date(sy, (sm ?? 1) - 1, 1);
    const endDate = lastDayOfMonth(new Date(ey, (em ?? 1) - 1, 1));
    const startDateStr = format(startDate, "yyyy-MM-dd");
    const endDateStr = format(endDate, "yyyy-MM-dd");
    return {
      startDate: startDateStr,
      endDate: endDateStr,
    };
  }
  if (period === "quarter") {
    const parseQ = (s: string) => {
      const [y, q] = s.split("-");
      const year = parseInt(y ?? "2025", 10);
      const qn = parseInt((q ?? "Q1").replace("Q", ""), 10) || 1;
      const month = (qn - 1) * 3 + 1;
      return { year, month };
    };
    const s = parseQ(start);
    const e = parseQ(end);
    const startDate = startOfQuarter(new Date(s.year, s.month - 1, 1));
    const endDate = endOfQuarter(new Date(e.year, e.month - 1, 1));
    return {
      startDate: format(startDate, "yyyy-MM-dd"),
      endDate: format(endDate, "yyyy-MM-dd"),
    };
  }
  if (period === "year") {
    const sy = parseInt(start, 10) || new Date().getFullYear();
    const ey = parseInt(end, 10) || new Date().getFullYear();
    return {
      startDate: `${sy}-01-01`,
      endDate: `${ey}-12-31`,
    };
  }
  return { startDate: start.slice(0, 10), endDate: end.slice(0, 10) };
}

const QUARTER_OPTIONS = [
  { value: "Q1", label: "Q1" },
  { value: "Q2", label: "Q2" },
  { value: "Q3", label: "Q3" },
  { value: "Q4", label: "Q4" },
];

interface TrendPeriodRangeSelectorProps {
  period: PeriodType;
  rangeStart: string;
  rangeEnd: string;
  onPeriodChange: (period: PeriodType) => void;
  onRangeChange: (start: string, end: string) => void;
}

export function TrendPeriodRangeSelector({
  period,
  rangeStart,
  rangeEnd,
  onPeriodChange,
  onRangeChange,
}: TrendPeriodRangeSelectorProps) {
  const handlePeriodChange = useCallback(
    (p: PeriodType) => {
      const def = getDefaultTrendRangeForPeriod(p);
      onPeriodChange(p);
      onRangeChange(def.start, def.end);
    },
    [onPeriodChange, onRangeChange]
  );

  const now = new Date();
  const yesterday = format(subDays(now, 1), "yyyy-MM-dd");
  const currentYear = now.getFullYear();
  const yearOptions = useMemo(
    () => Array.from({ length: 6 }, (_, i) => currentYear - i),
    [currentYear]
  );
  const monthOptions = useMemo(
    () => Array.from({ length: 12 }, (_, i) => i + 1),
    []
  );

  const renderRangeInputs = () => {
    switch (period) {
      case "update":
        return (
          <>
            <Input
              type="date"
              className="w-auto"
              value={rangeStart.slice(0, 10)}
              max={yesterday}
              onChange={(e) => {
                const v = e.target.value;
                onRangeChange(v, rangeEnd > v ? rangeEnd : v);
              }}
              aria-label="开始日期"
            />
            <span className="text-muted-foreground">至</span>
            <Input
              type="date"
              className="w-auto"
              value={rangeEnd.slice(0, 10)}
              min={rangeStart.slice(0, 10)}
              max={yesterday}
              onChange={(e) => {
                const v = e.target.value;
                onRangeChange(rangeStart > v ? v : rangeStart, v);
              }}
              aria-label="结束日期"
            />
          </>
        );
      case "month": {
        const parse = (s: string) => {
          const [y, m] = s.split("-").map(Number);
          return { year: y ?? currentYear, month: m ?? 1 };
        };
        const s = parse(rangeStart);
        const e = parse(rangeEnd);
        return (
          <>
            <div className="flex items-center gap-1">
              <Select
                className="w-auto"
                value={s.year}
                onChange={(ev) =>
                  onRangeChange(
                    `${ev.target.value}-${String(s.month).padStart(2, "0")}`,
                    rangeEnd
                  )
                }
              >
                {yearOptions.map((y) => (
                  <option key={y} value={y}>{y}年</option>
                ))}
              </Select>
              <Select
                className="w-auto"
                value={s.month}
                onChange={(ev) =>
                  onRangeChange(
                    `${s.year}-${String(ev.target.value).padStart(2, "0")}`,
                    rangeEnd
                  )
                }
              >
                {monthOptions.map((m) => (
                  <option key={m} value={m}>{m}月</option>
                ))}
              </Select>
            </div>
            <span className="text-muted-foreground">至</span>
            <div className="flex items-center gap-1">
              <Select
                className="w-auto"
                value={e.year}
                onChange={(ev) =>
                  onRangeChange(
                    rangeStart,
                    `${ev.target.value}-${String(e.month).padStart(2, "0")}`
                  )
                }
              >
                {yearOptions.map((y) => (
                  <option key={y} value={y}>{y}年</option>
                ))}
              </Select>
              <Select
                className="w-auto"
                value={e.month}
                onChange={(ev) =>
                  onRangeChange(
                    rangeStart,
                    `${e.year}-${String(ev.target.value).padStart(2, "0")}`
                  )
                }
              >
                {monthOptions.map((m) => (
                  <option key={m} value={m}>{m}月</option>
                ))}
              </Select>
            </div>
          </>
        );
      }
      case "quarter": {
        const parse = (s: string) => {
          const [y, q] = s.split("-");
          const year = parseInt(y ?? String(currentYear), 10);
          const quarter = (q === "Q1" || q === "Q2" || q === "Q3" || q === "Q4") ? q : "Q1";
          return { year, quarter };
        };
        const s = parse(rangeStart);
        const e = parse(rangeEnd);
        return (
          <>
            <div className="flex items-center gap-1">
              <Select
                className="w-auto"
                value={s.year}
                onChange={(ev) =>
                  onRangeChange(`${ev.target.value}-${s.quarter}`, rangeEnd)
                }
              >
                {yearOptions.map((y) => (
                  <option key={y} value={y}>{y}年</option>
                ))}
              </Select>
              <Select
                className="w-auto"
                value={s.quarter}
                onChange={(ev) =>
                  onRangeChange(`${s.year}-${ev.target.value}`, rangeEnd)
                }
              >
                {QUARTER_OPTIONS.map((q) => (
                  <option key={q.value} value={q.value}>{q.label}</option>
                ))}
              </Select>
            </div>
            <span className="text-muted-foreground">至</span>
            <div className="flex items-center gap-1">
              <Select
                className="w-auto"
                value={e.year}
                onChange={(ev) =>
                  onRangeChange(rangeStart, `${ev.target.value}-${e.quarter}`)
                }
              >
                {yearOptions.map((y) => (
                  <option key={y} value={y}>{y}年</option>
                ))}
              </Select>
              <Select
                className="w-auto"
                value={e.quarter}
                onChange={(ev) =>
                  onRangeChange(rangeStart, `${e.year}-${ev.target.value}`)
                }
              >
                {QUARTER_OPTIONS.map((q) => (
                  <option key={q.value} value={q.value}>{q.label}</option>
                ))}
              </Select>
            </div>
          </>
        );
      }
      case "year":
        return (
          <>
            <Select
              className="w-auto"
              value={rangeStart}
              onChange={(e) => onRangeChange(e.target.value, rangeEnd)}
            >
              {yearOptions.map((y) => (
                <option key={y} value={y}>{y}年</option>
              ))}
            </Select>
            <span className="text-muted-foreground">至</span>
            <Select
              className="w-auto"
              value={rangeEnd}
              onChange={(e) => onRangeChange(rangeStart, e.target.value)}
            >
              {yearOptions.map((y) => (
                <option key={y} value={y}>{y}年</option>
              ))}
            </Select>
          </>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="text-xs text-muted-foreground">趋势日期</span>
      <div className="flex items-center gap-1 rounded-lg border border-border p-0.5">
        {PERIODS.map((p) => (
          <Button
            key={p.value}
            type="button"
            variant={period === p.value ? "default" : "outline"}
            size="xs"
            onClick={() => handlePeriodChange(p.value)}
            aria-label={p.label}
          >
            {p.label}
          </Button>
        ))}
      </div>
      {renderRangeInputs()}
    </div>
  );
}
