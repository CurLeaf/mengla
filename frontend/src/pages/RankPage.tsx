import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
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
  const { primaryCatId } = useOutletContext<LayoutContext>();
  const queryClient = useQueryClient();

  const [period, setPeriod] = useState<PeriodType>("month");
  const [timest, setTimest] = useState(() => getDefaultTimestForPeriod("month"));

  const dateType = periodToDateType(period);
  const queryKey = ["mengla", mode, primaryCatId, dateType, timest];

  const query = useQuery({
    queryKey,
    queryFn: () => queryMengla(buildQueryParams(mode, primaryCatId, period, timest)),
    enabled: !!primaryCatId && !!timest,
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

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        {periodSelector}
        {query.isFetching && !query.isLoading && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="w-3 h-3 animate-spin text-primary" />
            <span>更新中…</span>
          </div>
        )}
      </div>
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
