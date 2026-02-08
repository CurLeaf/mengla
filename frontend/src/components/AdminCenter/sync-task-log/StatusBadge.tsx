import type { SyncTaskLog } from "../../../services/sync-task-api";

/**
 * 状态标签组件
 */
export function StatusBadge({ status }: { status: SyncTaskLog["status"] }) {
  const configMap: Record<
    SyncTaskLog["status"],
    { bg: string; text: string; label: string }
  > = {
    RUNNING: {
      bg: "bg-blue-500/20",
      text: "text-blue-400",
      label: "运行中",
    },
    COMPLETED: {
      bg: "bg-green-500/20",
      text: "text-green-400",
      label: "已完成",
    },
    FAILED: {
      bg: "bg-red-500/20",
      text: "text-red-400",
      label: "失败",
    },
    CANCELLED: {
      bg: "bg-yellow-500/20",
      text: "text-yellow-400",
      label: "已取消",
    },
  };
  const fallback = { bg: "bg-gray-500/20", text: "text-gray-400", label: status };
  const config = configMap[status] ?? fallback;

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${config.bg} ${config.text}`}
    >
      {status === "RUNNING" && (
        <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
      )}
      {config.label}
    </span>
  );
}
