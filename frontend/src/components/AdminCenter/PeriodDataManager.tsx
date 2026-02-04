import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchMenglaStatus,
  submitPanelDataFill,
  type MengLaStatusResponse,
} from "../../services/mengla-admin-api";
import type { PeriodType } from "../RankPeriodSelector";
import {
  getDefaultTrendRangeForPeriod,
  trendRangeToDateRange,
} from "../TrendPeriodRangeSelector";

const GRANULARITY_OPTIONS: { value: string; label: string; period: PeriodType }[] = [
  { value: "day", label: "日", period: "update" },
  { value: "month", label: "月", period: "month" },
  { value: "quarter", label: "季", period: "quarter" },
  { value: "year", label: "年", period: "year" },
];

const ACTION_OPTIONS = [
  { value: "high", label: "蓝海Top" },
  { value: "hot", label: "热销Top" },
  { value: "chance", label: "潜力Top" },
  { value: "industryViewV2", label: "行业区间" },
  { value: "industryTrendRange", label: "行业趋势" },
];

const NON_TREND_ACTIONS = ["high", "hot", "chance", "industryViewV2"];

const INPUT_STYLE =
  "bg-[#0F0F12] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 focus:border-[#5E6AD2]";

const QUARTER_OPTIONS = [
  { value: "Q1", label: "Q1" },
  { value: "Q2", label: "Q2" },
  { value: "Q3", label: "Q3" },
  { value: "Q4", label: "Q4" },
];

function getDefaultRangeForGranularity(granularity: string): { start: string; end: string } {
  const period = GRANULARITY_OPTIONS.find((g) => g.value === granularity)?.period ?? "month";
  return getDefaultTrendRangeForPeriod(period);
}

export function PeriodDataManager() {
  const queryClient = useQueryClient();
  const [singleGranularity, setSingleGranularity] = useState("month");
  const [trendGranularity, setTrendGranularity] = useState("month");
  const [singleTimest, setSingleTimest] = useState(() =>
    getDefaultRangeForGranularity("month").start
  );
  const [rangeStart, setRangeStart] = useState(() =>
    getDefaultRangeForGranularity("month").start
  );
  const [rangeEnd, setRangeEnd] = useState(() =>
    getDefaultRangeForGranularity("month").end
  );
  const [actions, setActions] = useState<string[]>(ACTION_OPTIONS.map((a) => a.value));
  const [statusResult, setStatusResult] = useState<MengLaStatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [onlyMissingColumns, setOnlyMissingColumns] = useState(false);
  const [onlyMissingRows, setOnlyMissingRows] = useState(false);

  const singlePeriod: PeriodType =
    GRANULARITY_OPTIONS.find((g) => g.value === singleGranularity)?.period ?? "month";
  const trendPeriod: PeriodType =
    GRANULARITY_OPTIONS.find((g) => g.value === trendGranularity)?.period ?? "month";

  const hasNonTrend = useMemo(
    () => actions.some((a) => NON_TREND_ACTIONS.includes(a)),
    [actions]
  );
  const hasTrend = useMemo(
    () => actions.includes("industryTrendRange"),
    [actions]
  );
  const nonTrendList = useMemo(
    () => actions.filter((a) => NON_TREND_ACTIONS.includes(a)),
    [actions]
  );

  const apiDateRangeSingle = useMemo(() => {
    return trendRangeToDateRange(singlePeriod, singleTimest, singleTimest);
  }, [singlePeriod, singleTimest]);

  const apiDateRange = useMemo(() => {
    return trendRangeToDateRange(trendPeriod, rangeStart, rangeEnd);
  }, [trendPeriod, rangeStart, rangeEnd]);

  const singleTimestValid = Boolean(singleTimest?.trim());
  const rangeValid = apiDateRange.startDate <= apiDateRange.endDate;
  const formValid =
    (hasNonTrend ? singleTimestValid : true) &&
    (hasTrend ? rangeValid : true) &&
    (hasNonTrend || hasTrend);

  const statusMutation = useMutation({
    mutationFn: async () => {
      const merged: MengLaStatusResponse = {
        granularity: singleGranularity,
        startDate: apiDateRangeSingle.startDate,
        endDate: apiDateRangeSingle.endDate,
        status: {},
      };
      if (hasNonTrend && nonTrendList.length > 0) {
        const res = await fetchMenglaStatus({
          granularity: singleGranularity,
          startDate: apiDateRangeSingle.startDate,
          endDate: apiDateRangeSingle.endDate,
          actions: nonTrendList,
        });
        Object.assign(merged.status, res.status);
      }
      if (hasTrend) {
        const res = await fetchMenglaStatus({
          granularity: trendGranularity,
          startDate: apiDateRange.startDate,
          endDate: apiDateRange.endDate,
          actions: ["industryTrendRange"],
        });
        Object.assign(merged.status, res.status);
      }
      return merged;
    },
    onSuccess: (data) => {
      setStatusResult(data);
      setStatusError(null);
    },
    onError: (err) => {
      setStatusResult(null);
      setStatusError(String(err));
    },
  });

  const fillMutation = useMutation({
    mutationFn: async () => {
      if (hasNonTrend && nonTrendList.length > 0) {
        await submitPanelDataFill({
          granularity: singleGranularity,
          startDate: apiDateRangeSingle.startDate,
          endDate: apiDateRangeSingle.endDate,
          actions: nonTrendList,
        });
      }
      if (hasTrend) {
        await submitPanelDataFill({
          granularity: trendGranularity,
          startDate: apiDateRange.startDate,
          endDate: apiDateRange.endDate,
          actions: ["industryTrendRange"],
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["panel-config"] });
    },
  });

  const toggleAction = (value: string) => {
    setActions((prev) =>
      prev.includes(value) ? prev.filter((a) => a !== value) : [...prev, value]
    );
  };

  const handleSingleGranularityChange = (value: string) => {
    setSingleGranularity(value);
    setSingleTimest(getDefaultRangeForGranularity(value).start);
  };

  const handleTrendGranularityChange = (value: string) => {
    setTrendGranularity(value);
    const def = getDefaultRangeForGranularity(value);
    setRangeStart(def.start);
    setRangeEnd(def.end);
  };

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
  }, []);

  const renderRangeInputs = () => {
    switch (trendGranularity) {
      case "day":
        return (
          <>
            <div>
              <label className="block text-xs font-medium text-white/80 mb-1.5">开始日期</label>
              <input
                type="date"
                className={INPUT_STYLE}
                value={rangeStart.slice(0, 10)}
                max={yesterday}
                onChange={(e) => setRangeStart(e.target.value)}
                aria-label="开始日期"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-white/80 mb-1.5">结束日期</label>
              <input
                type="date"
                className={INPUT_STYLE}
                value={rangeEnd.slice(0, 10)}
                min={rangeStart.slice(0, 10)}
                max={yesterday}
                onChange={(e) => setRangeEnd(e.target.value)}
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
              <label className="block text-xs font-medium text-white/80 mb-1.5">开始</label>
              <div className="flex items-center gap-1">
                <select
                  className={INPUT_STYLE}
                  value={s.year}
                  onChange={(ev) =>
                    setRangeStart(
                      `${ev.target.value}-${String(s.month).padStart(2, "0")}`
                    )
                  }
                  aria-label="开始年"
                >
                  {yearOptions.map((y) => (
                    <option key={y} value={y}>
                      {y}年
                    </option>
                  ))}
                </select>
                <select
                  className={INPUT_STYLE}
                  value={s.month}
                  onChange={(ev) =>
                    setRangeStart(
                      `${s.year}-${String(ev.target.value).padStart(2, "0")}`
                    )
                  }
                  aria-label="开始月"
                >
                  {monthOptions.map((m) => (
                    <option key={m} value={m}>
                      {m}月
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-white/80 mb-1.5">结束</label>
              <div className="flex items-center gap-1">
                <select
                  className={INPUT_STYLE}
                  value={e.year}
                  onChange={(ev) =>
                    setRangeEnd(
                      `${ev.target.value}-${String(e.month).padStart(2, "0")}`
                    )
                  }
                  aria-label="结束年"
                >
                  {yearOptions.map((y) => (
                    <option key={y} value={y}>
                      {y}年
                    </option>
                  ))}
                </select>
                <select
                  className={INPUT_STYLE}
                  value={e.month}
                  onChange={(ev) =>
                    setRangeEnd(
                      `${e.year}-${String(ev.target.value).padStart(2, "0")}`
                    )
                  }
                  aria-label="结束月"
                >
                  {monthOptions.map((m) => (
                    <option key={m} value={m}>
                      {m}月
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </>
        );
      }
      case "quarter": {
        const parse = (s: string) => {
          const [y, q] = (s || "").split("-");
          const year = parseInt(y ?? String(currentYear), 10);
          const quarter =
            q === "Q1" || q === "Q2" || q === "Q3" || q === "Q4" ? q : "Q1";
          return { year, quarter };
        };
        const s = parse(rangeStart);
        const e = parse(rangeEnd);
        return (
          <>
            <div>
              <label className="block text-xs font-medium text-white/80 mb-1.5">开始</label>
              <div className="flex items-center gap-1">
                <select
                  className={INPUT_STYLE}
                  value={s.year}
                  onChange={(ev) =>
                    setRangeStart(`${ev.target.value}-${s.quarter}`)
                  }
                  aria-label="开始年"
                >
                  {yearOptions.map((y) => (
                    <option key={y} value={y}>
                      {y}年
                    </option>
                  ))}
                </select>
                <select
                  className={INPUT_STYLE}
                  value={s.quarter}
                  onChange={(ev) =>
                    setRangeStart(`${s.year}-${ev.target.value}`)
                  }
                  aria-label="开始季"
                >
                  {QUARTER_OPTIONS.map((q) => (
                    <option key={q.value} value={q.value}>
                      {q.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-white/80 mb-1.5">结束</label>
              <div className="flex items-center gap-1">
                <select
                  className={INPUT_STYLE}
                  value={e.year}
                  onChange={(ev) =>
                    setRangeEnd(`${ev.target.value}-${e.quarter}`)
                  }
                  aria-label="结束年"
                >
                  {yearOptions.map((y) => (
                    <option key={y} value={y}>
                      {y}年
                    </option>
                  ))}
                </select>
                <select
                  className={INPUT_STYLE}
                  value={e.quarter}
                  onChange={(ev) =>
                    setRangeEnd(`${e.year}-${ev.target.value}`)
                  }
                  aria-label="结束季"
                >
                  {QUARTER_OPTIONS.map((q) => (
                    <option key={q.value} value={q.value}>
                      {q.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </>
        );
      }
      case "year":
        return (
          <>
            <div>
              <label className="block text-xs font-medium text-white/80 mb-1.5">开始年</label>
              <select
                className={INPUT_STYLE}
                value={rangeStart}
                onChange={(e) => setRangeStart(e.target.value)}
                aria-label="开始年"
              >
                {yearOptions.map((y) => (
                  <option key={y} value={y}>
                    {y}年
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-white/80 mb-1.5">结束年</label>
              <select
                className={INPUT_STYLE}
                value={rangeEnd}
                onChange={(e) => setRangeEnd(e.target.value)}
                aria-label="结束年"
              >
                {yearOptions.map((y) => (
                  <option key={y} value={y}>
                    {y}年
                  </option>
                ))}
              </select>
            </div>
          </>
        );
      default:
        return null;
    }
  };

  const renderSingleTimeInputs = () => {
    switch (singleGranularity) {
      case "day":
        return (
          <div>
            <label className="block text-xs font-medium text-white/80 mb-1.5">选择日期</label>
            <input
              type="date"
              className={INPUT_STYLE}
              value={singleTimest.slice(0, 10)}
              max={yesterday}
              onChange={(e) => setSingleTimest(e.target.value)}
              aria-label="日期"
            />
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
            <label className="block text-xs font-medium text-white/80 mb-1.5">选择月</label>
            <div className="flex items-center gap-1">
              <select
                className={INPUT_STYLE}
                value={s.year}
                onChange={(ev) =>
                  setSingleTimest(
                    `${ev.target.value}-${String(s.month).padStart(2, "0")}`
                  )
                }
                aria-label="年"
              >
                {yearOptions.map((y) => (
                  <option key={y} value={y}>
                    {y}年
                  </option>
                ))}
              </select>
              <select
                className={INPUT_STYLE}
                value={s.month}
                onChange={(ev) =>
                  setSingleTimest(
                    `${s.year}-${String(ev.target.value).padStart(2, "0")}`
                  )
                }
                aria-label="月"
              >
                {monthOptions.map((m) => (
                  <option key={m} value={m}>
                    {m}月
                  </option>
                ))}
              </select>
            </div>
          </div>
        );
      }
      case "quarter": {
        const parse = (s: string) => {
          const [y, q] = (s || "").split("-");
          const year = parseInt(y ?? String(currentYear), 10);
          const quarter =
            q === "Q1" || q === "Q2" || q === "Q3" || q === "Q4" ? q : "Q1";
          return { year, quarter };
        };
        const s = parse(singleTimest);
        return (
          <div>
            <label className="block text-xs font-medium text-white/80 mb-1.5">选择季</label>
            <div className="flex items-center gap-1">
              <select
                className={INPUT_STYLE}
                value={s.year}
                onChange={(ev) =>
                  setSingleTimest(`${ev.target.value}-${s.quarter}`)
                }
                aria-label="年"
              >
                {yearOptions.map((y) => (
                  <option key={y} value={y}>
                    {y}年
                  </option>
                ))}
              </select>
              <select
                className={INPUT_STYLE}
                value={s.quarter}
                onChange={(ev) =>
                  setSingleTimest(`${s.year}-${ev.target.value}`)
                }
                aria-label="季"
              >
                {QUARTER_OPTIONS.map((q) => (
                  <option key={q.value} value={q.value}>
                    {q.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        );
      }
      case "year":
        return (
          <div>
            <label className="block text-xs font-medium text-white/80 mb-1.5">选择年</label>
            <select
              className={INPUT_STYLE}
              value={singleTimest}
              onChange={(e) => setSingleTimest(e.target.value)}
              aria-label="年"
            >
              {yearOptions.map((y) => (
                <option key={y} value={y}>
                  {y}年
                </option>
              ))}
            </select>
          </div>
        );
      default:
        return null;
    }
  };

  const statusMatrix = statusResult?.status ?? {};

  const actionIds = useMemo(
    () => (statusResult ? Object.keys(statusMatrix) : []),
    [statusResult, statusMatrix]
  );

  const periodKeys = useMemo(() => {
    if (!statusResult) return [];
    const keys = new Set<string>();
    Object.values(statusMatrix).forEach((m) => {
      Object.keys(m ?? {}).forEach((k) => keys.add(k));
    });
    return [...keys].sort();
  }, [statusResult, statusMatrix]);

  const { visibleActionIds, visiblePeriodKeys, perActionMissing } = useMemo(() => {
    const perAction: Record<string, number> = {};
    const perPeriod: Record<string, number> = {};

    actionIds.forEach((actionId) => {
      const map = statusMatrix[actionId] ?? {};
      let missingCount = 0;
      periodKeys.forEach((pk) => {
        const has = map[pk];
        if (!has) {
          missingCount += 1;
          perPeriod[pk] = (perPeriod[pk] ?? 0) + 1;
        }
      });
      perAction[actionId] = missingCount;
    });

    let cols = periodKeys;
    if (onlyMissingColumns) {
      cols = cols.filter((pk) => (perPeriod[pk] ?? 0) > 0);
    }

    let rows = actionIds;
    if (onlyMissingRows) {
      rows = rows.filter((id) => (perAction[id] ?? 0) > 0);
    }

    return {
      visibleActionIds: rows,
      visiblePeriodKeys: cols,
      perActionMissing: perAction,
    };
  }, [actionIds, periodKeys, statusMatrix, onlyMissingColumns, onlyMissingRows]);

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-white">周期数据</h2>
        <p className="mt-1 text-xs text-white/60">
          按粒度与日期范围查询各 period_key 在库状态，并补齐缺失数据。
        </p>
      </div>

      <div className="rounded-lg border border-white/10 bg-black/20 p-4 space-y-4 max-w-2xl">
        <div>
          <label className="block text-xs font-medium text-white/80 mb-2">接口（actions）</label>
          <div className="flex flex-wrap gap-3">
            {ACTION_OPTIONS.map((opt) => (
              <label key={opt.value} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={actions.includes(opt.value)}
                  onChange={() => toggleAction(opt.value)}
                  className="rounded border-white/30 bg-black/40 text-[#5E6AD2] focus:ring-[#5E6AD2]"
                />
                <span className="text-xs text-white/80">{opt.label}</span>
              </label>
            ))}
          </div>
        </div>

        {hasNonTrend && (
          <div>
            <p className="text-xs font-medium text-white/80 mb-1.5">
              单时间（蓝海/热销/潜力/行业区间）
            </p>
            <div className="mb-2">
              <label className="block text-xs font-medium text-white/60 mb-1">粒度</label>
              <select
                value={singleGranularity}
                onChange={(e) => handleSingleGranularityChange(e.target.value)}
                className={`${INPUT_STYLE} w-full max-w-[8rem]`}
              >
                {GRANULARITY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {renderSingleTimeInputs()}
            </div>
          </div>
        )}

        {hasTrend && (
          <div>
            <p className="text-xs font-medium text-white/80 mb-1.5">
              时间范围（行业趋势）
            </p>
            <div className="mb-2">
              <label className="block text-xs font-medium text-white/60 mb-1">粒度</label>
              <select
                value={trendGranularity}
                onChange={(e) => handleTrendGranularityChange(e.target.value)}
                className={`${INPUT_STYLE} w-full max-w-[8rem]`}
              >
                {GRANULARITY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {renderRangeInputs()}
            </div>
          </div>
        )}

        {!hasNonTrend && !hasTrend && (
          <p className="text-xs text-white/50">请至少勾选一个接口。</p>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => statusMutation.mutate()}
            disabled={statusMutation.isPending || !formValid}
            className="px-4 py-2 rounded-lg border border-white/10 text-xs text-white hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 disabled:opacity-50"
          >
            {statusMutation.isPending ? "查询中…" : "查询数据状态"}
          </button>
          <button
            type="button"
            onClick={() => fillMutation.mutate()}
            disabled={fillMutation.isPending || !formValid}
            className="px-4 py-2 rounded-lg border border-white/10 text-xs text-white hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 disabled:opacity-50"
          >
            {fillMutation.isPending ? "提交中…" : "补齐缺失数据"}
          </button>
        </div>

        {hasTrend && !rangeValid && (
          <p className="text-xs text-amber-400">时间范围：开始不能晚于结束，请调整。</p>
        )}
        {hasNonTrend && !singleTimestValid && (
          <p className="text-xs text-amber-400">请选择单时间。</p>
        )}
        {fillMutation.isSuccess && (
          <p className="text-xs text-green-400">
            已提交补齐任务，正在后台执行。可稍后再次点击「查询数据状态」查看。
          </p>
        )}
        {fillMutation.isError && (
          <p className="text-xs text-red-400">{String(fillMutation.error)}</p>
        )}
      </div>

      {statusError && (
        <p className="text-xs text-red-400">{statusError}</p>
      )}

      {statusResult && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3 text-xs text-white/70">
            <span>
              共 {periodKeys.length} 个 period_key，{actionIds.length} 个接口
            </span>
            {actionIds.map((actionId) => (
              <span key={actionId} className="ml-1">
                {ACTION_OPTIONS.find((a) => a.value === actionId)?.label ?? actionId}
                ：缺失 {perActionMissing[actionId] ?? 0}
              </span>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs text-white/70">
            <span className="text-white/60">
              方块表示某接口在对应周期下是否已有 MengLa 数据：
            </span>
            <div className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded-full bg-emerald-400" />
              <span>有数据</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded-full bg-red-500" />
              <span>无数据</span>
            </div>
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="checkbox"
                checked={onlyMissingColumns}
                onChange={(e) => setOnlyMissingColumns(e.target.checked)}
                className="rounded border-white/30 bg-black/40 text-[#5E6AD2] focus:ring-[#5E6AD2]"
              />
              <span>只看有缺失的周期</span>
            </label>
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="checkbox"
                checked={onlyMissingRows}
                onChange={(e) => setOnlyMissingRows(e.target.checked)}
                className="rounded border-white/30 bg-black/40 text-[#5E6AD2] focus:ring-[#5E6AD2]"
              />
              <span>只看有缺失的接口</span>
            </label>
          </div>

          <div className="rounded-lg border border-white/10 bg-black/20 overflow-hidden overflow-x-auto max-h-80 overflow-y-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="sticky top-0 bg-black/40 border-b border-white/10">
                <tr>
                  <th className="px-3 py-2 font-medium text-white/70 whitespace-nowrap">
                    接口 / 周期
                  </th>
                  {visiblePeriodKeys.map((pk) => (
                    <th
                      key={pk}
                      className="px-2 py-2 font-medium text-white/70 text-center whitespace-nowrap"
                    >
                      {pk}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleActionIds.map((actionId) => {
                  const label =
                    ACTION_OPTIONS.find((a) => a.value === actionId)?.label ?? actionId;
                  return (
                    <tr key={actionId} className="border-b border-white/5 hover:bg-white/5">
                      <td className="px-3 py-1.5 text-white/80 whitespace-nowrap">
                        {label}
                      </td>
                      {visiblePeriodKeys.map((pk) => {
                        const has = statusMatrix[actionId]?.[pk];
                        const title = `${label} @ ${pk}: ${has ? "有数据" : "无数据"}`;
                        return (
                          <td
                            key={pk}
                            className="px-2 py-1.5 text-center align-middle"
                            title={title}
                          >
                            <span
                              className={`inline-block h-3 w-3 rounded-full ${
                                has ? "bg-emerald-400" : "bg-red-500"
                              }`}
                            />
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
                {visibleActionIds.length === 0 && visiblePeriodKeys.length === 0 && (
                  <tr>
                    <td
                      colSpan={1}
                      className="px-3 py-2 text-xs text-white/60 whitespace-nowrap"
                    >
                      当前筛选条件下没有需要展示的接口或周期。
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
