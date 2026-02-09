import type { SyncTaskLog } from "../../../services/sync-task-api";
import { Badge } from "../../ui/badge";

const STATUS_CONFIG: Record<
  SyncTaskLog["status"],
  { variant: "info" | "success" | "destructive" | "warning"; label: string }
> = {
  RUNNING: { variant: "info", label: "运行中" },
  COMPLETED: { variant: "success", label: "已完成" },
  FAILED: { variant: "destructive", label: "失败" },
  CANCELLED: { variant: "warning", label: "已取消" },
};

export function StatusBadge({ status }: { status: SyncTaskLog["status"] }) {
  const config = STATUS_CONFIG[status] ?? { variant: "secondary" as const, label: status };

  return (
    <Badge variant={config.variant} className="gap-1.5">
      {status === "RUNNING" && (
        <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
      )}
      {config.label}
    </Badge>
  );
}
