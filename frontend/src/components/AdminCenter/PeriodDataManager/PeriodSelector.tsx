import { useMemo } from "react";
import {
  GRANULARITY_OPTIONS,
  ACTION_OPTIONS,
  QUARTER_OPTIONS,
} from "./shared";
import { Select } from "../../ui/select";
import { Checkbox } from "../../ui/checkbox";
import { Input } from "../../ui/input";

interface PeriodSelectorProps {
  /* ---- actions ---- */
  actions: string[];
  onToggleAction: (value: string) => void;
  /* ---- 单时间 ---- */
  hasNonTrend: boolean;
  singleGranularity: string;
  onSingleGranularityChange: (value: string) => void;
  singleTimest: string;
  onSingleTimestChange: (value: string) => void;
  /* ---- 趋势范围 ---- */
  hasTrend: boolean;
  trendGranularity: string;
  onTrendGranularityChange: (value: string) => void;
  rangeStart: string;
  onRangeStartChange: (value: string) => void;
  rangeEnd: string;
  onRangeEndChange: (value: string) => void;
}

export function PeriodSelector({
  actions,
  onToggleAction,
  hasNonTrend,
  singleGranularity,
  onSingleGranularityChange,
  singleTimest,
  onSingleTimestChange,
  hasTrend,
  trendGranularity,
  onTrendGranularityChange,
  rangeStart,
  onRangeStartChange,
  rangeEnd,
  onRangeEndChange,
}: PeriodSelectorProps) {
  const now = new Date();
  const currentYear = now.getFullYear();
  const yearOptions = useMemo(
    () => Array.from({ length: 8 }, (_, i) => currentYear - i),
    [currentYear]
  );
  const monthOptions = useMemo(
    () => Array.from({ length: 12 }, (_, i) => i + 1),
    []
  );
  const yesterday = useMemo(() => {
    const d = new Date(now);
    d.setDate(d.getDate() - 1);
    return d.toISOString().slice(0, 10);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---- 趋势范围输入 ---- */
  const renderRangeInputs = () => {
    switch (trendGranularity) {
      case "day":
        return (
          <>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">开始日期</label>
              <Input
                type="date"
                value={rangeStart.slice(0, 10)}
                max={yesterday}
                onChange={(e) => onRangeStartChange(e.target.value)}
                aria-label="开始日期"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">结束日期</label>
              <Input
                type="date"
                value={rangeEnd.slice(0, 10)}
                min={rangeStart.slice(0, 10)}
                max={yesterday}
                onChange={(e) => onRangeEndChange(e.target.value)}
                aria-label="结束日期"
              />
            </div>
          </>
        );
      case "month": {
        const parse = (s: string) => {
          const [y, m] = (s || "").split("-").map(Number);
          return { year: y ?? currentYear, month: m ?? 1 };
        };
        const s = parse(rangeStart);
        const e = parse(rangeEnd);
        return (
          <>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">开始</label>
              <div className="flex items-center gap-1">
                <Select value={s.year} onChange={(ev) => onRangeStartChange(`${ev.target.value}-${String(s.month).padStart(2, "0")}`)} aria-label="开始年">
                  {yearOptions.map((y) => <option key={y} value={y}>{y}年</option>)}
                </Select>
                <Select value={s.month} onChange={(ev) => onRangeStartChange(`${s.year}-${String(ev.target.value).padStart(2, "0")}`)} aria-label="开始月">
                  {monthOptions.map((m) => <option key={m} value={m}>{m}月</option>)}
                </Select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">结束</label>
              <div className="flex items-center gap-1">
                <Select value={e.year} onChange={(ev) => onRangeEndChange(`${ev.target.value}-${String(e.month).padStart(2, "0")}`)} aria-label="结束年">
                  {yearOptions.map((y) => <option key={y} value={y}>{y}年</option>)}
                </Select>
                <Select value={e.month} onChange={(ev) => onRangeEndChange(`${e.year}-${String(ev.target.value).padStart(2, "0")}`)} aria-label="结束月">
                  {monthOptions.map((m) => <option key={m} value={m}>{m}月</option>)}
                </Select>
              </div>
            </div>
          </>
        );
      }
      case "quarter": {
        const parse = (s: string) => {
          const [y, q] = (s || "").split("-");
          const year = parseInt(y ?? String(currentYear), 10);
          const quarter = q === "Q1" || q === "Q2" || q === "Q3" || q === "Q4" ? q : "Q1";
          return { year, quarter };
        };
        const s = parse(rangeStart);
        const e = parse(rangeEnd);
        return (
          <>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">开始</label>
              <div className="flex items-center gap-1">
                <Select value={s.year} onChange={(ev) => onRangeStartChange(`${ev.target.value}-${s.quarter}`)} aria-label="开始年">
                  {yearOptions.map((y) => <option key={y} value={y}>{y}年</option>)}
                </Select>
                <Select value={s.quarter} onChange={(ev) => onRangeStartChange(`${s.year}-${ev.target.value}`)} aria-label="开始季">
                  {QUARTER_OPTIONS.map((q) => <option key={q.value} value={q.value}>{q.label}</option>)}
                </Select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">结束</label>
              <div className="flex items-center gap-1">
                <Select value={e.year} onChange={(ev) => onRangeEndChange(`${ev.target.value}-${e.quarter}`)} aria-label="结束年">
                  {yearOptions.map((y) => <option key={y} value={y}>{y}年</option>)}
                </Select>
                <Select value={e.quarter} onChange={(ev) => onRangeEndChange(`${e.year}-${ev.target.value}`)} aria-label="结束季">
                  {QUARTER_OPTIONS.map((q) => <option key={q.value} value={q.value}>{q.label}</option>)}
                </Select>
              </div>
            </div>
          </>
        );
      }
      case "year":
        return (
          <>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">开始年</label>
              <Select value={rangeStart} onChange={(e) => onRangeStartChange(e.target.value)} aria-label="开始年">
                {yearOptions.map((y) => <option key={y} value={y}>{y}年</option>)}
              </Select>
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">结束年</label>
              <Select value={rangeEnd} onChange={(e) => onRangeEndChange(e.target.value)} aria-label="结束年">
                {yearOptions.map((y) => <option key={y} value={y}>{y}年</option>)}
              </Select>
            </div>
          </>
        );
      default:
        return null;
    }
  };

  /* ---- 单时间输入 ---- */
  const renderSingleTimeInputs = () => {
    switch (singleGranularity) {
      case "day":
        return (
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">选择日期</label>
            <Input type="date" value={singleTimest.slice(0, 10)} max={yesterday} onChange={(e) => onSingleTimestChange(e.target.value)} aria-label="日期" />
          </div>
        );
      case "month": {
        const parse = (s: string) => {
          const [y, m] = (s || "").split("-").map(Number);
          return { year: y ?? currentYear, month: m ?? 1 };
        };
        const s = parse(singleTimest);
        return (
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">选择月</label>
            <div className="flex items-center gap-1">
              <Select value={s.year} onChange={(ev) => onSingleTimestChange(`${ev.target.value}-${String(s.month).padStart(2, "0")}`)} aria-label="年">
                {yearOptions.map((y) => <option key={y} value={y}>{y}年</option>)}
              </Select>
              <Select value={s.month} onChange={(ev) => onSingleTimestChange(`${s.year}-${String(ev.target.value).padStart(2, "0")}`)} aria-label="月">
                {monthOptions.map((m) => <option key={m} value={m}>{m}月</option>)}
              </Select>
            </div>
          </div>
        );
      }
      case "quarter": {
        const parse = (s: string) => {
          const [y, q] = (s || "").split("-");
          const year = parseInt(y ?? String(currentYear), 10);
          const quarter = q === "Q1" || q === "Q2" || q === "Q3" || q === "Q4" ? q : "Q1";
          return { year, quarter };
        };
        const s = parse(singleTimest);
        return (
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">选择季</label>
            <div className="flex items-center gap-1">
              <Select value={s.year} onChange={(ev) => onSingleTimestChange(`${ev.target.value}-${s.quarter}`)} aria-label="年">
                {yearOptions.map((y) => <option key={y} value={y}>{y}年</option>)}
              </Select>
              <Select value={s.quarter} onChange={(ev) => onSingleTimestChange(`${s.year}-${ev.target.value}`)} aria-label="季">
                {QUARTER_OPTIONS.map((q) => <option key={q.value} value={q.value}>{q.label}</option>)}
              </Select>
            </div>
          </div>
        );
      }
      case "year":
        return (
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">选择年</label>
            <Select value={singleTimest} onChange={(e) => onSingleTimestChange(e.target.value)} aria-label="年">
              {yearOptions.map((y) => <option key={y} value={y}>{y}年</option>)}
            </Select>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <>
      {/* 接口选择 */}
      <div>
        <label className="block text-xs font-medium text-muted-foreground mb-2">接口（actions）</label>
        <div className="flex flex-wrap gap-3">
          {ACTION_OPTIONS.map((opt) => (
            <label key={opt.value} className="flex items-center gap-2 cursor-pointer">
              <Checkbox
                checked={actions.includes(opt.value)}
                onCheckedChange={() => onToggleAction(opt.value)}
              />
              <span className="text-xs text-muted-foreground">{opt.label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* 单时间选择 */}
      {hasNonTrend && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1.5">单时间（蓝海/热销/潜力/行业区间）</p>
          <div className="mb-2">
            <label className="block text-xs font-medium text-muted-foreground/70 mb-1">粒度</label>
            <Select
              value={singleGranularity}
              onChange={(e) => onSingleGranularityChange(e.target.value)}
              className="w-full max-w-[8rem]"
            >
              {GRANULARITY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </Select>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {renderSingleTimeInputs()}
          </div>
        </div>
      )}

      {/* 趋势范围选择 */}
      {hasTrend && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1.5">时间范围（行业趋势）</p>
          <div className="mb-2">
            <label className="block text-xs font-medium text-muted-foreground/70 mb-1">粒度</label>
            <Select
              value={trendGranularity}
              onChange={(e) => onTrendGranularityChange(e.target.value)}
              className="w-full max-w-[8rem]"
            >
              {GRANULARITY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </Select>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {renderRangeInputs()}
          </div>
        </div>
      )}

      {!hasNonTrend && !hasTrend && (
        <p className="text-xs text-muted-foreground">请至少勾选一个接口。</p>
      )}
    </>
  );
}
