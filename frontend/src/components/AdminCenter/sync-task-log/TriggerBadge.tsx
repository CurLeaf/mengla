import type { SyncTaskLog } from "../../../services/sync-task-api";

/**
 * 触发方式标签
 */
export function TriggerBadge({ trigger }: { trigger: SyncTaskLog["trigger"] }) {
  const isManual = trigger === "manual";
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs ${
        isManual
          ? "bg-purple-500/20 text-purple-400"
          : "bg-gray-500/20 text-gray-400"
      }`}
    >
      {isManual ? "手动" : "定时"}
    </span>
  );
}
