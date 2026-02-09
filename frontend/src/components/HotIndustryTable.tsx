import React from "react";
import type { HighListRow } from "../types/mengla";
import { TableSkeleton, InlineError } from "./LoadingSkeleton";
import { Card, CardHeader, CardContent } from "./ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "./ui/table";
import { Badge } from "./ui/badge";

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
    <Card className="overflow-hidden">
      <CardHeader className="px-6 pt-4 pb-3 flex-row items-center justify-between space-y-0">
        <div>
          <p className="text-xs font-mono tracking-[0.2em] text-muted-foreground uppercase">
            BLUE SEA
          </p>
          <h2 className="text-sm font-semibold text-foreground mt-1">{title}</h2>
        </div>
      </CardHeader>
      {error ? (
        <InlineError message={`加载${title}失败`} onRetry={onRetry} />
      ) : (
        <CardContent className="p-0">
          <div className="overflow-auto max-h-[420px]">
            <Table aria-label={title}>
              <TableHeader className="bg-muted/30">
                <TableRow className="border-border/50">
                  <TableHead className="px-6">类目</TableHead>
                  <TableHead className="px-4 text-right">商品数</TableHead>
                  <TableHead className="px-4 text-right">动销率</TableHead>
                  <TableHead className="px-4 text-right">月销量</TableHead>
                  <TableHead className="px-4 text-right">月销售额</TableHead>
                  <TableHead className="px-4 text-right">品牌占比</TableHead>
                  <TableHead className="px-4 text-right">头部占比</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((row, idx) => (
                  <TableRow
                    key={row.catId3 ?? row.catId2 ?? row.catId1 ?? idx}
                  >
                    <TableCell className="px-6 py-3 align-top">
                      <div className="flex flex-col gap-0.5">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-foreground">
                            {row.catNameCn || row.catName || "-"}
                          </span>
                          {row.catTag === 2 && (
                            <Badge variant="default" className="text-[10px] px-2 py-0.5">
                              热销
                            </Badge>
                          )}
                        </div>
                        <span className="text-[11px] text-muted-foreground/70">
                          {row.catName}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="px-4 py-3 text-right whitespace-nowrap">
                      <div className="flex flex-col items-end gap-0.5">
                        <span>{row.skuNum ?? "-"}</span>
                        <span className="text-[11px] text-muted-foreground/70">
                          有销：{row.saleSkuNum ?? "-"}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="px-4 py-3 text-right whitespace-nowrap">
                      <span>{row.saleRatio != null ? `${row.saleRatio}%` : "-"}</span>
                    </TableCell>
                    <TableCell className="px-4 py-3 text-right whitespace-nowrap">
                      <div className="flex flex-col items-end gap-0.5">
                        <span>{row.monthSales ?? "-"}</span>
                        <span className="text-[11px] text-muted-foreground/70">
                          占比：{row.monthSalesRating ?? "-"}%
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="px-4 py-3 text-right whitespace-nowrap">
                      <div className="flex flex-col items-end gap-0.5">
                        <span>{row.monthGmvRmb ?? row.monthGmv ?? "-"}</span>
                        <span className="text-[11px] text-muted-foreground/70">
                          占比：{row.monthGmvRating ?? "-"}%
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="px-4 py-3 text-right whitespace-nowrap">
                      <span>{row.brandGmvRating != null ? `${row.brandGmvRating}%` : "-"}</span>
                    </TableCell>
                    <TableCell className="px-4 py-3 text-right whitespace-nowrap">
                      <span>{row.topGmvRating != null ? `${row.topGmvRating}%` : "-"}</span>
                    </TableCell>
                  </TableRow>
                ))}
                {data.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="px-6 py-12 text-center">
                      <p className="text-sm text-muted-foreground/60">暂无数据</p>
                      <p className="mt-1 text-xs text-muted-foreground/40">
                        请点击顶部"采集"按钮获取数据，或尝试切换类目和时间周期
                      </p>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      )}
    </Card>
  );
});
