import type { SyncTaskLog } from "../../../services/sync-task-api";

/**
 * 进度条组件
 */
export function ProgressBar({ progress }: { progress: SyncTaskLog["progress"] }) {
  const { total, completed, failed } = progress;
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
  const failedPercent = total > 0 ? Math.round((failed / total) * 100) : 0;

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div className="h-full flex">
          <div
            className="bg-green-500 transition-all duration-300"
            style={{ width: `${percent}%` }}
          />
          {failedPercent > 0 && (
            <div
              className="bg-red-500 transition-all duration-300"
              style={{ width: `${failedPercent}%` }}
            />
          )}
        </div>
      </div>
      <span className="text-xs text-white/60 whitespace-nowrap min-w-[80px]">
        {completed}/{total} ({percent}%)
      </span>
    </div>
  );
}
