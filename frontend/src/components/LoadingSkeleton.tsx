/** 通用骨架屏 & 状态容器组件 */
import { Skeleton } from "./ui/skeleton";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { AlertCircle, Loader2 } from "lucide-react";

interface SkeletonProps {
  className?: string;
}

/** 脉冲闪烁条 — 模拟文字/色块占位 */
export function SkeletonBar({ className = "" }: SkeletonProps) {
  return <Skeleton className={className} />;
}

/** 图表区域骨架 — 与 TrendChart 等高 */
export function ChartSkeleton() {
  return (
    <Card className="px-4 pt-4 pb-5">
      <div className="flex items-center justify-between mb-3 px-2">
        <div className="space-y-2">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-4 w-32" />
        </div>
      </div>
      <div className="h-80 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary/50" />
          <span className="text-xs text-muted-foreground">加载趋势数据…</span>
        </div>
      </div>
    </Card>
  );
}

/** 表格骨架 — 模拟 HotIndustryTable 行 */
export function TableSkeleton({ rows = 5, title = "加载数据…" }: { rows?: number; title?: string }) {
  return (
    <Card className="overflow-hidden">
      <div className="px-6 pt-4 pb-3">
        <Skeleton className="h-3 w-16 mb-2" />
        <Skeleton className="h-4 w-28" />
      </div>
      <div className="overflow-auto max-h-[420px]">
        <table className="min-w-full text-xs">
          <thead className="bg-muted/30 border-y border-border">
            <tr>
              {["类目", "商品数", "动销率", "月销量", "月销售额", "品牌占比", "头部占比"].map((h) => (
                <th key={h} className="px-4 py-2 text-left font-normal text-muted-foreground">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: rows }).map((_, i) => (
              <tr key={i} className="border-b border-border/50">
                <td className="px-6 py-3"><Skeleton className="h-4 w-24" /></td>
                <td className="px-4 py-3"><Skeleton className="h-4 w-12 ml-auto" /></td>
                <td className="px-4 py-3"><Skeleton className="h-4 w-10 ml-auto" /></td>
                <td className="px-4 py-3"><Skeleton className="h-4 w-14 ml-auto" /></td>
                <td className="px-4 py-3"><Skeleton className="h-4 w-16 ml-auto" /></td>
                <td className="px-4 py-3"><Skeleton className="h-4 w-10 ml-auto" /></td>
                <td className="px-4 py-3"><Skeleton className="h-4 w-10 ml-auto" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-center py-4 gap-2">
        <Loader2 className="h-5 w-5 animate-spin text-primary/50" />
        <span className="text-xs text-muted-foreground">{title}</span>
      </div>
    </Card>
  );
}

/** 卡片骨架 — 模拟 DistributionSection 单张卡片 */
export function CardSkeleton() {
  return (
    <Card className="p-4">
      <Skeleton className="h-3 w-20 mb-3" />
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-center justify-between">
            <div className="space-y-1">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-2.5 w-32" />
            </div>
            <Skeleton className="h-3 w-12" />
          </div>
        ))}
      </div>
    </Card>
  );
}

/** 错误提示 — 嵌入在组件容器内（不占满整页） */
export function InlineError({ message = "加载失败", onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 gap-3">
      <div className="w-10 h-10 rounded-full bg-destructive/10 border border-destructive/20 flex items-center justify-center">
        <AlertCircle className="h-5 w-5 text-destructive" />
      </div>
      <p className="text-sm text-destructive">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          重试
        </Button>
      )}
    </div>
  );
}
