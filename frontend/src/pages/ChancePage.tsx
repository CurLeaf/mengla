import { useState } from "react";
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

export default function ChancePage() {
  const { primaryCatId } = useOutletContext<LayoutContext>();
  const queryClient = useQueryClient();

  const [period, setPeriod] = useState<PeriodType>("month");
  const [timest, setTimest] = useState(() => getDefaultTimestForPeriod("month"));

  const dateType = periodToDateType(period);
  const queryKey = ["mengla", "chance", primaryCatId, dateType, timest];

  const query = useQuery({
    queryKey,
    queryFn: () => queryMengla(buildQueryParams("chance", primaryCatId, period, timest)),
    enabled: !!primaryCatId && !!timest,
    staleTime: 5 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    networkMode: "always",
    retry: 2,
  });

  const list = useRankList(pickPayload(query.data), "chanceList");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <RankPeriodSelector
          selectedPeriod={period}
          selectedTimest={timest}
          onPeriodChange={(p) => { setPeriod(p); setTimest(getDefaultTimestForPeriod(p)); }}
          onTimestChange={setTimest}
        />
      </div>
      <HotIndustryTable
        data={list}
        title="潜力Top行业数据"
        isLoading={query.isLoading}
        error={query.error}
        onRetry={() => queryClient.invalidateQueries({ queryKey })}
      />
    </div>
  );
}
