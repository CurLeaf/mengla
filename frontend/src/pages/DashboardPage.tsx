import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { TrendChart } from "../components/TrendChart";
import { DistributionSection } from "../components/DistributionCards";
import {
  getDefaultTimestForPeriod,
  type PeriodType,
} from "../components/RankPeriodSelector";
import {
  getDefaultTrendRangeForPeriod,
  TrendPeriodRangeSelector,
} from "../components/TrendPeriodRangeSelector";
import { queryMengla } from "../services/mengla-api";
import {
  buildTrendQueryParams,
  buildQueryParams,
  pickPayload,
  useTrendPoints,
  useIndustryView,
} from "../hooks/useMenglaQuery";
import { useOutletContext } from "react-router-dom";
import type { LayoutContext } from "../App";

export default function DashboardPage() {
  const { primaryCatId } = useOutletContext<LayoutContext>();
  const queryClient = useQueryClient();

  /* ---- 趋势：独立状态 ---- */
  const [trendPeriod, setTrendPeriod] = useState<PeriodType>("update");
  const [trendRangeStart, setTrendRangeStart] = useState(() =>
    getDefaultTrendRangeForPeriod("update").start
  );
  const [trendRangeEnd, setTrendRangeEnd] = useState(() =>
    getDefaultTrendRangeForPeriod("update").end
  );

  const trendQueryKey = [
    "mengla", "industryTrendRange", primaryCatId,
    trendPeriod, trendRangeStart, trendRangeEnd,
  ];

  const trendQuery = useQuery({
    queryKey: trendQueryKey,
    queryFn: () =>
      queryMengla(
        buildTrendQueryParams("industryTrendRange", primaryCatId, trendPeriod, trendRangeStart, trendRangeEnd)
      ),
    enabled: !!primaryCatId && !!trendRangeStart && !!trendRangeEnd,
    staleTime: 5 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    networkMode: "always",
    retry: 2,
  });

  /* ---- 区间分布：独立状态 ---- */
  const [distributionPeriod, setDistributionPeriod] = useState<PeriodType>("update");
  const [distributionTimest, setDistributionTimest] = useState(() =>
    getDefaultTimestForPeriod("update")
  );

  const viewQueryKey = [
    "mengla", "industryViewV2", primaryCatId,
    distributionPeriod, distributionTimest,
  ];

  const viewQuery = useQuery({
    queryKey: viewQueryKey,
    queryFn: () =>
      queryMengla(
        buildQueryParams("industryViewV2", primaryCatId, distributionPeriod, distributionTimest)
      ),
    enabled: !!primaryCatId && !!distributionTimest,
    staleTime: 5 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    networkMode: "always",
    retry: 2,
  });

  /* ---- 派生数据 ---- */
  const trendPoints = useTrendPoints(pickPayload(trendQuery.data));
  const industryView = useIndustryView(pickPayload(viewQuery.data));

  /* ---- 渲染：两个 section 各自独立，互不阻塞 ---- */
  return (
    <div className="space-y-6">
      {/* 趋势 section */}
      <section className="space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div>
              <p className="text-xs font-mono tracking-[0.2em] text-muted-foreground uppercase">TREND</p>
              <h2 className="mt-1 text-sm font-semibold text-foreground">行业趋势</h2>
            </div>
            {trendQuery.isFetching && !trendQuery.isLoading && (
              <Loader2 className="w-3 h-3 animate-spin text-primary" title="更新中" />
            )}
          </div>
          <TrendPeriodRangeSelector
            period={trendPeriod}
            rangeStart={trendRangeStart}
            rangeEnd={trendRangeEnd}
            onPeriodChange={(p) => {
              const def = getDefaultTrendRangeForPeriod(p);
              setTrendPeriod(p);
              setTrendRangeStart(def.start);
              setTrendRangeEnd(def.end);
            }}
            onRangeChange={(start, end) => {
              setTrendRangeStart(start);
              setTrendRangeEnd(end);
            }}
          />
        </header>
        <TrendChart
          points={trendPoints}
          isLoading={trendQuery.isLoading}
          error={trendQuery.error}
          onRetry={() => queryClient.invalidateQueries({ queryKey: trendQueryKey })}
        />
      </section>

      {/* 区间分布 section */}
      <DistributionSection
        industryView={industryView}
        distributionPeriod={distributionPeriod}
        distributionTimest={distributionTimest}
        onDistributionPeriodChange={(p: PeriodType) => {
          setDistributionPeriod(p);
          setDistributionTimest(getDefaultTimestForPeriod(p));
        }}
        onDistributionTimestChange={setDistributionTimest}
        isLoading={viewQuery.isLoading}
        error={viewQuery.error}
        onRetry={() => queryClient.invalidateQueries({ queryKey: viewQueryKey })}
      />
    </div>
  );
}
