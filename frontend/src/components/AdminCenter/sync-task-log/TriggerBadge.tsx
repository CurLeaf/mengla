import type { SyncTaskLog } from "../../../services/sync-task-api";
import { Badge } from "../../ui/badge";

export function TriggerBadge({ trigger }: { trigger: SyncTaskLog["trigger"] }) {
  const isManual = trigger === "manual";
  return (
    <Badge variant={isManual ? "default" : "secondary"} className="text-xs">
      {isManual ? "手动" : "定时"}
    </Badge>
  );
}
