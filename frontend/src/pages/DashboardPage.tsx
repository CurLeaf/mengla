import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
  const { primaryCatId, fetchTrigger } = useOutletContext<LayoutContext>();
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
    enabled: fetchTrigger > 0 && !!primaryCatId && !!trendRangeStart && !!trendRangeEnd,
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
    enabled: fetchTrigger > 0 && !!primaryCatId && !!distributionTimest,
    staleTime: 5 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    networkMode: "always",
    retry: 2,
  });

  /* ---- 派生数据 ---- */
  const trendPoints = useTrendPoints(pickPayload(trendQuery.data));
  const industryView = useIndustryView(pickPayload(viewQuery.data));

  /* ---- 渲染：两个 section 各自独立，互不阻塞 ---- */
  if (fetchTrigger === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-32 text-white/40 space-y-3">
        <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12 text-white/20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3" /></svg>
        <p className="text-sm">请点击左上角 <span className="text-[#5E6AD2] font-medium">「采集」</span> 按钮加载数据</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 趋势 section */}
      <section className="space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-mono tracking-[0.2em] text-white/50 uppercase">TREND</p>
            <h2 className="mt-1 text-sm font-semibold text-white">行业趋势</h2>
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
