/** 通用骨架屏 & 状态容器组件 */

interface SkeletonProps {
  className?: string;
}

/** 脉冲闪烁条 —— 模拟文字/色块占位 */
export function SkeletonBar({ className = "" }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse rounded bg-white/[0.06] ${className}`}
    />
  );
}

/** 图表区域骨架 —— 与 TrendChart 等高 */
export function ChartSkeleton() {
  return (
    <div className="bg-[#0a0a0c]/80 border border-white/8 rounded-2xl px-4 pt-4 pb-5 shadow-[0_0_0_1px_rgba(255,255,255,0.06),0_18px_40px_rgba(0,0,0,0.7)]">
      <div className="flex items-center justify-between mb-3 px-2">
        <div className="space-y-2">
          <SkeletonBar className="h-3 w-16" />
          <SkeletonBar className="h-4 w-32" />
        </div>
      </div>
      <div className="h-80 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-[#5E6AD2]/30 border-t-[#5E6AD2] rounded-full animate-spin" />
          <span className="text-xs text-white/40">加载趋势数据…</span>
        </div>
      </div>
    </div>
  );
}

/** 表格骨架 —— 模拟 HotIndustryTable 行 */
export function TableSkeleton({ rows = 5, title = "加载数据…" }: { rows?: number; title?: string }) {
  return (
    <section className="bg-[#0a0a0c]/80 border border-white/10 rounded-2xl shadow-[0_0_0_1px_rgba(255,255,255,0.06),0_18px_45px_rgba(0,0,0,0.7)] overflow-hidden">
      <div className="px-6 pt-4 pb-3">
        <SkeletonBar className="h-3 w-16 mb-2" />
        <SkeletonBar className="h-4 w-28" />
      </div>
      <div className="overflow-auto max-h-[420px]">
        <table className="min-w-full text-xs">
          <thead className="bg-white/[0.03] border-y border-white/[0.08]">
            <tr>
              {["类目", "商品数", "动销率", "月销量", "月销售额", "品牌占比", "头部占比"].map((h) => (
                <th key={h} className="px-4 py-2 text-left font-normal text-white/60">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: rows }).map((_, i) => (
              <tr key={i} className="border-b border-white/[0.06]">
                <td className="px-6 py-3"><SkeletonBar className="h-4 w-24" /></td>
                <td className="px-4 py-3"><SkeletonBar className="h-4 w-12 ml-auto" /></td>
                <td className="px-4 py-3"><SkeletonBar className="h-4 w-10 ml-auto" /></td>
                <td className="px-4 py-3"><SkeletonBar className="h-4 w-14 ml-auto" /></td>
                <td className="px-4 py-3"><SkeletonBar className="h-4 w-16 ml-auto" /></td>
                <td className="px-4 py-3"><SkeletonBar className="h-4 w-10 ml-auto" /></td>
                <td className="px-4 py-3"><SkeletonBar className="h-4 w-10 ml-auto" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-center py-4 gap-2">
        <div className="w-5 h-5 border-2 border-[#5E6AD2]/30 border-t-[#5E6AD2] rounded-full animate-spin" />
        <span className="text-xs text-white/40">{title}</span>
      </div>
    </section>
  );
}

/** 卡片骨架 —— 模拟 DistributionSection 单张卡片 */
export function CardSkeleton() {
  return (
    <div className="bg-[#0a0a0c]/80 border border-white/8 rounded-2xl p-4 shadow-[0_0_0_1px_rgba(255,255,255,0.06),0_14px_30px_rgba(0,0,0,0.6)]">
      <SkeletonBar className="h-3 w-20 mb-3" />
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-center justify-between">
            <div className="space-y-1">
              <SkeletonBar className="h-3 w-24" />
              <SkeletonBar className="h-2.5 w-32" />
            </div>
            <SkeletonBar className="h-3 w-12" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** 错误提示 —— 嵌入在组件容器内（不占满整页） */
export function InlineError({ message = "加载失败", onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 gap-3">
      <div className="w-10 h-10 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center">
        <span className="text-red-400 text-lg">!</span>
      </div>
      <p className="text-sm text-red-400">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="px-3 py-1 text-xs bg-white/5 hover:bg-white/10 border border-white/10 rounded text-white/70 transition-colors"
        >
          重试
        </button>
      )}
    </div>
  );
}
