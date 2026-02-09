import React from "react";
import type { HighListRow } from "../types/mengla";
import { TableSkeleton, InlineError } from "./LoadingSkeleton";

interface HotIndustryTableProps {
  data: HighListRow[];
  title?: string;
  isLoading?: boolean;
  error?: Error | null;
  onRetry?: () => void;
}

export const HotIndustryTable = React.memo(function HotIndustryTable({
  data,
  title = "蓝海类目列表",
  isLoading,
  error,
  onRetry,
}: HotIndustryTableProps) {
  if (isLoading) return <TableSkeleton title={`加载${title}…`} />;

  return (
    <section className="bg-[#0a0a0c]/80 border border-white/10 rounded-2xl shadow-[0_0_0_1px_rgba(255,255,255,0.06),0_18px_45px_rgba(0,0,0,0.7)] overflow-hidden">
      <div className="px-6 pt-4 pb-3 flex items-center justify-between">
        <div>
          <p className="text-xs font-mono tracking-[0.2em] text-white/50 uppercase">
            BLUE SEA
          </p>
          <h2 className="text-sm font-semibold text-white mt-1">{title}</h2>
        </div>
      </div>
      {error ? (
        <InlineError message={`加载${title}失败`} onRetry={onRetry} />
      ) : (
      <>
      <div className="overflow-auto max-h-[420px]">
        <table className="min-w-full text-xs text-white/80" role="table" aria-label={title}>
          <thead className="bg-white/[0.03] border-y border-white/[0.08]">
            <tr>
              <th className="px-6 py-2 text-left font-normal text-white/60">
                类目
              </th>
              <th className="px-4 py-2 text-right font-normal text-white/60">
                商品数
              </th>
              <th className="px-4 py-2 text-right font-normal text-white/60">
                动销率
              </th>
              <th className="px-4 py-2 text-right font-normal text-white/60">
                月销量
              </th>
              <th className="px-4 py-2 text-right font-normal text-white/60">
                月销售额
              </th>
              <th className="px-4 py-2 text-right font-normal text-white/60">
                品牌占比
              </th>
              <th className="px-4 py-2 text-right font-normal text-white/60">
                头部占比
              </th>
            </tr>
          </thead>
          <tbody>
            {data.map((row, idx) => (
              <tr
                key={row.catId3 ?? row.catId2 ?? row.catId1 ?? idx}
                className="border-b border-white/[0.06] last:border-0 hover:bg-white/[0.03] transition-colors"
              >
                <td className="px-6 py-3 align-top">
                  <div className="flex flex-col gap-0.5">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-white">
                        {row.catNameCn || row.catName || "-"}
                      </span>
                      {row.catTag === 2 && (
                        <span className="inline-flex items-center rounded-full border border-[#5E6AD2]/40 bg-[#5E6AD2]/10 px-2 py-0.5 text-[10px] text-[#c7cffd]">
                          热销
                        </span>
                      )}
                    </div>
                    <span className="text-[11px] text-white/45">
                      {row.catName}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  <div className="flex flex-col items-end gap-0.5">
                    <span>{row.skuNum ?? "-"}</span>
                    <span className="text-[11px] text-white/45">
                      有销：{row.saleSkuNum ?? "-"}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  <span>{row.saleRatio != null ? `${row.saleRatio}%` : "-"}</span>
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  <div className="flex flex-col items-end gap-0.5">
                    <span>{row.monthSales ?? "-"}</span>
                    <span className="text-[11px] text-white/45">
                      占比：{row.monthSalesRating ?? "-"}%
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  <div className="flex flex-col items-end gap-0.5">
                    <span>{row.monthGmvRmb ?? row.monthGmv ?? "-"}</span>
                    <span className="text-[11px] text-white/45">
                      占比：{row.monthGmvRating ?? "-"}%
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  <span>{row.brandGmvRating != null ? `${row.brandGmvRating}%` : "-"}</span>
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  <span>{row.topGmvRating != null ? `${row.topGmvRating}%` : "-"}</span>
                </td>
              </tr>
            ))}
            {data.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="px-6 py-12 text-center"
                >
                  <p className="text-sm text-white/40">暂无数据</p>
                  <p className="mt-1 text-xs text-white/25">
                    请点击顶部"采集"按钮获取数据，或尝试切换类目和时间周期
                  </p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      </>
      )}
    </section>
  );
});
