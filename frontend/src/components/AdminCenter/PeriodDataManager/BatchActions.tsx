import { Loader2 } from "lucide-react";
import { Button } from "../../ui/button";

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
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onQueryStatus}
          disabled={statusPending || !formValid}
          aria-busy={statusPending}
          aria-label="查询数据状态"
        >
          {statusPending && (
            <Loader2 className="h-3 w-3 animate-spin" />
          )}
          {statusPending ? "查询中…" : "查询数据状态"}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onFillData}
          disabled={fillPending || !formValid}
          aria-busy={fillPending}
          aria-label="补齐缺失数据"
          title="扫描选定范围内缺失的数据，并在后台自动补齐"
        >
          {fillPending && (
            <Loader2 className="h-3 w-3 animate-spin" />
          )}
          {fillPending ? "提交中…" : "补齐缺失数据"}
        </Button>
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
