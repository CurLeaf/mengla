import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchMenglaStatus,
  submitPanelDataFill,
  type MengLaStatusResponse,
} from "../../../services/mengla-admin-api";
import type { PeriodType } from "../../RankPeriodSelector";
import { trendRangeToDateRange } from "../../TrendPeriodRangeSelector";
import {
  GRANULARITY_OPTIONS,
  NON_TREND_ACTIONS,
  getDefaultRangeForGranularity,
} from "./shared";
import { PeriodSelector } from "./PeriodSelector";
import { BatchActions } from "./BatchActions";
import { DataTable } from "./DataTable";

export function PeriodDataManager() {
  const queryClient = useQueryClient();

  /* ---- 状态 ---- */
  const [singleGranularity, setSingleGranularity] = useState("month");
  const [trendGranularity, setTrendGranularity] = useState("month");
  const [singleTimest, setSingleTimest] = useState(() => getDefaultRangeForGranularity("month").start);
  const [rangeStart, setRangeStart] = useState(() => getDefaultRangeForGranularity("month").start);
  const [rangeEnd, setRangeEnd] = useState(() => getDefaultRangeForGranularity("month").end);
  const [actions, setActions] = useState<string[]>(["high", "hot", "chance", "industryViewV2", "industryTrendRange"]);
  const [statusResult, setStatusResult] = useState<MengLaStatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  /* ---- 派生值 ---- */
  const singlePeriod: PeriodType = GRANULARITY_OPTIONS.find((g) => g.value === singleGranularity)?.period ?? "month";
  const trendPeriod: PeriodType = GRANULARITY_OPTIONS.find((g) => g.value === trendGranularity)?.period ?? "month";

  const hasNonTrend = useMemo(() => actions.some((a) => NON_TREND_ACTIONS.includes(a)), [actions]);
  const hasTrend = useMemo(() => actions.includes("industryTrendRange"), [actions]);
  const nonTrendList = useMemo(() => actions.filter((a) => NON_TREND_ACTIONS.includes(a)), [actions]);

  const apiDateRangeSingle = useMemo(
    () => trendRangeToDateRange(singlePeriod, singleTimest, singleTimest),
    [singlePeriod, singleTimest]
  );
  const apiDateRange = useMemo(
    () => trendRangeToDateRange(trendPeriod, rangeStart, rangeEnd),
    [trendPeriod, rangeStart, rangeEnd]
  );

  const singleTimestValid = Boolean(singleTimest?.trim());
  const rangeValid = apiDateRange.startDate <= apiDateRange.endDate;
  const formValid =
    (hasNonTrend ? singleTimestValid : true) &&
    (hasTrend ? rangeValid : true) &&
    (hasNonTrend || hasTrend);

  /* ---- Mutations ---- */
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
    onSuccess: (data) => { setStatusResult(data); setStatusError(null); },
    onError: (err) => { setStatusResult(null); setStatusError(String(err)); },
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
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["panel-config"] }); },
  });

  /* ---- 事件处理 ---- */
  const toggleAction = (value: string) => {
    setActions((prev) => prev.includes(value) ? prev.filter((a) => a !== value) : [...prev, value]);
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

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-white">周期数据</h2>
        <p className="mt-1 text-xs text-white/60">
          按粒度与日期范围查询各 period_key 在库状态，并补齐缺失数据。
        </p>
      </div>

      <div className="rounded-lg border border-white/10 bg-black/20 p-4 space-y-4 max-w-2xl">
        <PeriodSelector
          actions={actions}
          onToggleAction={toggleAction}
          hasNonTrend={hasNonTrend}
          singleGranularity={singleGranularity}
          onSingleGranularityChange={handleSingleGranularityChange}
          singleTimest={singleTimest}
          onSingleTimestChange={setSingleTimest}
          hasTrend={hasTrend}
          trendGranularity={trendGranularity}
          onTrendGranularityChange={handleTrendGranularityChange}
          rangeStart={rangeStart}
          onRangeStartChange={setRangeStart}
          rangeEnd={rangeEnd}
          onRangeEndChange={setRangeEnd}
        />

        <BatchActions
          formValid={formValid}
          hasTrend={hasTrend}
          hasNonTrend={hasNonTrend}
          rangeValid={rangeValid}
          singleTimestValid={singleTimestValid}
          statusPending={statusMutation.isPending}
          fillPending={fillMutation.isPending}
          fillSuccess={fillMutation.isSuccess}
          fillError={fillMutation.isError ? String(fillMutation.error) : null}
          onQueryStatus={() => statusMutation.mutate()}
          onFillData={() => fillMutation.mutate()}
        />
      </div>

      <DataTable statusResult={statusResult} statusError={statusError} />
    </section>
  );
}
