import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { HotIndustryTable } from "../components/HotIndustryTable";
import {
  getDefaultTimestForPeriod,
  periodToDateType,
  RankPeriodSelector,
  type PeriodType,
} from "../components/RankPeriodSelector";
import { queryMengla } from "../services/mengla-api";
import { buildQueryParams, pickPayload, useRankList } from "../hooks/useMenglaQuery";
import { useOutletContext } from "react-router-dom";
import type { LayoutContext } from "../App";
import { STALE_TIMES, GC_TIMES } from "../constants";

interface RankPageProps {
  /** API action 名称，如 "high" | "hot" | "chance" */
  mode: string;
  /** 响应数据中的列表字段名 */
  listKey: "highList" | "hotList" | "chanceList";
  /** 表格标题 */
  title?: string;
}

const RankPage: React.FC<RankPageProps> = ({ mode, listKey, title }) => {
  const { primaryCatId, fetchTrigger } = useOutletContext<LayoutContext>();
  const queryClient = useQueryClient();

  const [period, setPeriod] = useState<PeriodType>("month");
  const [timest, setTimest] = useState(() => getDefaultTimestForPeriod("month"));

  const dateType = periodToDateType(period);
  const queryKey = ["mengla", mode, primaryCatId, dateType, timest];

  const query = useQuery({
    queryKey,
    queryFn: () => queryMengla(buildQueryParams(mode, primaryCatId, period, timest)),
    enabled: fetchTrigger > 0 && !!primaryCatId && !!timest,
    staleTime: STALE_TIMES.categories,
    gcTime: GC_TIMES.default,
    networkMode: "always",
    retry: 2,
  });

  const list = useRankList(pickPayload(query.data), listKey);

  const periodSelector = (
    <div className="flex flex-wrap items-center gap-3">
      <RankPeriodSelector
        selectedPeriod={period}
        selectedTimest={timest}
        onPeriodChange={(p) => {
          setPeriod(p);
          setTimest(getDefaultTimestForPeriod(p));
        }}
        onTimestChange={setTimest}
      />
    </div>
  );

  if (fetchTrigger === 0) {
    return (
      <div className="space-y-6">
        {periodSelector}
        <div className="flex flex-col items-center justify-center py-24 text-white/40 space-y-3">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12 text-white/20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3" />
          </svg>
          <p className="text-sm">
            请点击左上角 <span className="text-[#5E6AD2] font-medium">「采集」</span> 按钮加载数据
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {periodSelector}
      <HotIndustryTable
        data={list}
        title={title}
        isLoading={query.isLoading}
        error={query.error}
        onRetry={() => queryClient.invalidateQueries({ queryKey })}
      />
    </div>
  );
};

export default React.memo(RankPage);
