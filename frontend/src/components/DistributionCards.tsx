import type { RangeItem, IndustryView } from "../types/mengla";
import type { PeriodType } from "./RankPeriodSelector";
import { RankPeriodSelector } from "./RankPeriodSelector";
import { CardSkeleton, InlineError } from "./LoadingSkeleton";

interface RangeListProps {
  title: string;
  items?: RangeItem[] | null;
}

function RangeList({ title, items }: RangeListProps) {
  return (
    <div className="bg-[#0a0a0c]/80 border border-white/8 rounded-2xl p-4 shadow-[0_0_0_1px_rgba(255,255,255,0.06),0_14px_30px_rgba(0,0,0,0.6)]">
      <h3 className="text-xs font-medium text-white mb-3">{title}</h3>
      <div className="space-y-2 max-h-64 overflow-y-auto">
        {items?.map((item, idx) => (
          <div
            key={item.id ?? idx}
            className="flex items-center justify-between text-[11px] text-white/80"
          >
            <div className="flex flex-col">
              <span>{item.title}</span>
              <span className="text-white/40">
                商品数 {item.itemCount ?? "-"} · 销量{" "}
                {item.sales ?? "-"} · 销售额 {item.gmv ?? "-"}
              </span>
            </div>
            <div className="text-right text-white/45">
              <div>占比 {item.itemCountRate ?? item.salesRate ?? item.gmvRate ?? "-"}%</div>
            </div>
          </div>
        ))}
        {!items?.length && (
          <div className="text-[11px] text-white/40 text-center py-6">
            暂无区间数据
          </div>
        )}
      </div>
    </div>
  );
}

interface DistributionSectionProps {
  industryView: IndustryView | null;
  /** 行业区间分布时间选择器：放在标题旁边 */
  distributionPeriod?: PeriodType;
  distributionTimest?: string;
  onDistributionPeriodChange?: (period: PeriodType) => void;
  onDistributionTimestChange?: (timest: string) => void;
  isLoading?: boolean;
  error?: Error | null;
  onRetry?: () => void;
}

export function DistributionSection({
  industryView,
  distributionPeriod = "update",
  distributionTimest = "",
  onDistributionPeriodChange,
  onDistributionTimestChange,
  isLoading,
  error,
  onRetry,
}: DistributionSectionProps) {
  const data = industryView?.data ?? {};
  const showSelector =
    onDistributionPeriodChange != null && onDistributionTimestChange != null;

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-mono tracking-[0.2em] text-white/50 uppercase">
            DISTRIBUTION
          </p>
          <h2 className="mt-1 text-sm font-semibold text-white">
            行业区间分布
          </h2>
        </div>
        {showSelector && (
          <RankPeriodSelector
            selectedPeriod={distributionPeriod}
            selectedTimest={distributionTimest}
            onPeriodChange={onDistributionPeriodChange}
            onTimestChange={onDistributionTimestChange}
          />
        )}
      </header>
      {error ? (
        <InlineError message="加载区间分布数据失败" onRetry={onRetry} />
      ) : isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
      ) : (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <RangeList
          title="销量区间"
          items={data.industrySalesRangeDtoList}
        />
        <RangeList
          title="GMV 区间"
          items={data.industryGmvRangeDtoList}
        />
        <RangeList
          title="价格区间"
          items={data.industryPriceRangeDtoList}
        />
        <RangeList
          title="子类目占比"
          items={data.industryBrandRateDtoList}
        />
      </div>
      )}
    </section>
  );
}
