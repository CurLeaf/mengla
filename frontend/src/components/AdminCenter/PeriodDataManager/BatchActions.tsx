interface BatchActionsProps {
  formValid: boolean;
  hasTrend: boolean;
  hasNonTrend: boolean;
  rangeValid: boolean;
  singleTimestValid: boolean;
  statusPending: boolean;
  fillPending: boolean;
  fillSuccess: boolean;
  fillError: string | null;
  onQueryStatus: () => void;
  onFillData: () => void;
}

export function BatchActions({
  formValid,
  hasTrend,
  hasNonTrend,
  rangeValid,
  singleTimestValid,
  statusPending,
  fillPending,
  fillSuccess,
  fillError,
  onQueryStatus,
  onFillData,
}: BatchActionsProps) {
  return (
    <>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onQueryStatus}
          disabled={statusPending || !formValid}
          className="px-4 py-2 rounded-lg border border-white/10 text-xs text-white hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 disabled:opacity-50"
          aria-label="查询数据状态"
        >
          {statusPending ? "查询中…" : "查询数据状态"}
        </button>
        <button
          type="button"
          onClick={onFillData}
          disabled={fillPending || !formValid}
          className="px-4 py-2 rounded-lg border border-white/10 text-xs text-white hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 disabled:opacity-50"
          aria-label="补齐缺失数据"
        >
          {fillPending ? "提交中…" : "补齐缺失数据"}
        </button>
      </div>

      {hasTrend && !rangeValid && (
        <p className="text-xs text-amber-400">时间范围：开始不能晚于结束，请调整。</p>
      )}
      {hasNonTrend && !singleTimestValid && (
        <p className="text-xs text-amber-400">请选择单时间。</p>
      )}
      {fillSuccess && (
        <p className="text-xs text-green-400">
          已提交补齐任务，正在后台执行。可稍后再次点击「查询数据状态」查看。
        </p>
      )}
      {fillError && (
        <p className="text-xs text-red-400">{fillError}</p>
      )}
    </>
  );
}
