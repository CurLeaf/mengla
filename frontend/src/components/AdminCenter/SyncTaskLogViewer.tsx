import { useState, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchTodaySyncTasks,
  cancelSyncTask,
  deleteSyncTask,
  type SyncTaskLog,
} from "../../services/sync-task-api";

/**
 * 格式化时间为 HH:mm:ss
 */
function formatTime(isoString: string | null): string {
  if (!isoString) return "-";
  const date = new Date(isoString);
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/**
 * 计算耗时
 */
function calcDuration(startedAt: string, finishedAt: string | null): string {
  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const diffMs = end - start;

  if (diffMs < 0) return "-";

  const seconds = Math.floor(diffMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours > 0) {
    return `${hours}h ${minutes % 60}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`;
  }
  return `${seconds}s`;
}

/**
 * 状态标签组件
 */
function StatusBadge({ status }: { status: SyncTaskLog["status"] }) {
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

/**
 * 进度条组件
 */
function ProgressBar({ progress }: { progress: SyncTaskLog["progress"] }) {
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

/**
 * 触发方式标签
 */
function TriggerBadge({ trigger }: { trigger: SyncTaskLog["trigger"] }) {
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

/**
 * 确认弹窗
 */
function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  confirmClassName,
  extra,
  loading,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  confirmClassName?: string;
  extra?: React.ReactNode;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-sm rounded-lg border border-white/10 bg-gray-900 p-5 shadow-xl">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        <p className="mt-2 text-xs text-white/60 leading-relaxed">{message}</p>
        {extra && <div className="mt-3">{extra}</div>}
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={loading}
            className="rounded px-3 py-1.5 text-xs text-white/60 hover:text-white hover:bg-white/10 transition-colors disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`rounded px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
              confirmClassName || "bg-red-600 text-white hover:bg-red-500"
            }`}
          >
            {loading ? "处理中…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

type DialogState =
  | { type: "none" }
  | { type: "cancel"; task: SyncTaskLog }
  | { type: "delete"; task: SyncTaskLog };

export function SyncTaskLogViewer() {
  const queryClient = useQueryClient();
  const {
    data: tasks,
    isLoading,
    error,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ["sync-tasks-today"],
    queryFn: fetchTodaySyncTasks,
    refetchInterval: 10000,
  });

  const [dialog, setDialog] = useState<DialogState>({ type: "none" });
  const [actionLoading, setActionLoading] = useState(false);
  const [deleteData, setDeleteData] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  const showToast = useCallback((message: string, type: "success" | "error") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  const handleCancel = useCallback(async () => {
    if (dialog.type !== "cancel") return;
    setActionLoading(true);
    try {
      await cancelSyncTask(dialog.task.id);
      showToast("任务已取消", "success");
      queryClient.invalidateQueries({ queryKey: ["sync-tasks-today"] });
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "取消失败", "error");
    } finally {
      setActionLoading(false);
      setDialog({ type: "none" });
    }
  }, [dialog, queryClient, showToast]);

  const handleDelete = useCallback(async () => {
    if (dialog.type !== "delete") return;
    setActionLoading(true);
    try {
      const result = await deleteSyncTask(dialog.task.id, deleteData);
      const msg = deleteData
        ? `任务已删除，清除了 ${result.deleted_data_count ?? 0} 条采集数据`
        : "任务已删除";
      showToast(msg, "success");
      queryClient.invalidateQueries({ queryKey: ["sync-tasks-today"] });
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "删除失败", "error");
    } finally {
      setActionLoading(false);
      setDialog({ type: "none" });
      setDeleteData(false);
    }
  }, [dialog, deleteData, queryClient, showToast]);

  if (isLoading) {
    return (
      <section>
        <h2 className="text-sm font-semibold text-white">同步日志</h2>
        <p className="mt-2 text-xs text-white/60">加载中…</p>
      </section>
    );
  }

  if (error) {
    return (
      <section>
        <h2 className="text-sm font-semibold text-white">同步日志</h2>
        <p className="mt-2 text-xs text-red-400">{String(error)}</p>
      </section>
    );
  }

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString("zh-CN")
    : "-";

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">同步日志</h2>
          <p className="mt-1 text-xs text-white/60">
            查看当天的数据采集任务执行状态。
          </p>
        </div>
        <span className="text-xs text-white/40">
          上次更新: {lastUpdated}
        </span>
      </div>

      {tasks && tasks.length > 0 ? (
        <div className="rounded-lg border border-white/10 bg-black/20 overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-white/10 text-white/60">
                <th className="px-4 py-2.5 font-medium">任务名称</th>
                <th className="px-4 py-2.5 font-medium w-20">状态</th>
                <th className="px-4 py-2.5 font-medium w-48">进度</th>
                <th className="px-4 py-2.5 font-medium w-20">开始时间</th>
                <th className="px-4 py-2.5 font-medium w-20">耗时</th>
                <th className="px-4 py-2.5 font-medium w-16">触发</th>
                <th className="px-4 py-2.5 font-medium w-24 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr
                  key={task.id}
                  className="border-b border-white/5 hover:bg-white/5"
                >
                  <td className="px-4 py-2.5 text-white">{task.task_name}</td>
                  <td className="px-4 py-2.5">
                    <StatusBadge status={task.status} />
                  </td>
                  <td className="px-4 py-2.5">
                    <ProgressBar progress={task.progress} />
                  </td>
                  <td className="px-4 py-2.5 text-white/60 font-mono">
                    {formatTime(task.started_at)}
                  </td>
                  <td className="px-4 py-2.5 text-white/60 font-mono">
                    {calcDuration(task.started_at, task.finished_at)}
                  </td>
                  <td className="px-4 py-2.5">
                    <TriggerBadge trigger={task.trigger} />
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {task.status === "RUNNING" && (
                        <button
                          onClick={() => setDialog({ type: "cancel", task })}
                          className="rounded px-2 py-1 text-xs text-yellow-400 hover:bg-yellow-500/20 transition-colors"
                          title="取消任务"
                        >
                          取消
                        </button>
                      )}
                      {task.status !== "RUNNING" && (
                        <button
                          onClick={() => {
                            setDeleteData(false);
                            setDialog({ type: "delete", task });
                          }}
                          className="rounded px-2 py-1 text-xs text-red-400 hover:bg-red-500/20 transition-colors"
                          title="删除任务"
                        >
                          删除
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-lg border border-white/10 bg-black/20 p-8 text-center">
          <p className="text-sm text-white/40">今天还没有同步任务</p>
          <p className="mt-1 text-xs text-white/30">
            可以在"任务管理"中手动触发采集任务
          </p>
        </div>
      )}

      {tasks && tasks.some((t) => t.error_message) && (
        <div className="space-y-2">
          <h3 className="text-xs font-medium text-white/60">错误信息</h3>
          {tasks
            .filter((t) => t.error_message)
            .map((task) => (
              <div
                key={task.id}
                className="rounded border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-400"
              >
                <span className="font-medium">{task.task_name}:</span>{" "}
                {task.error_message}
              </div>
            ))}
        </div>
      )}

      {/* 取消确认弹窗 */}
      <ConfirmDialog
        open={dialog.type === "cancel"}
        title="取消任务"
        message={`确定要取消正在运行的任务「${dialog.type === "cancel" ? dialog.task.task_name : ""}」吗？任务将在当前步骤完成后停止。`}
        confirmLabel="确定取消"
        confirmClassName="bg-yellow-600 text-white hover:bg-yellow-500"
        loading={actionLoading}
        onConfirm={handleCancel}
        onCancel={() => setDialog({ type: "none" })}
      />

      {/* 删除确认弹窗 */}
      <ConfirmDialog
        open={dialog.type === "delete"}
        title="删除任务"
        message={`确定要删除任务「${dialog.type === "delete" ? dialog.task.task_name : ""}」吗？`}
        confirmLabel="确定删除"
        loading={actionLoading}
        extra={
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={deleteData}
              onChange={(e) => setDeleteData(e.target.checked)}
              className="rounded border-white/20 bg-white/10 text-red-500 focus:ring-red-500/50"
            />
            <span className="text-xs text-white/60">
              同时删除该任务采集的数据
            </span>
          </label>
        }
        onConfirm={handleDelete}
        onCancel={() => {
          setDialog({ type: "none" });
          setDeleteData(false);
        }}
      />

      {/* Toast 提示 */}
      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 rounded-lg px-4 py-2.5 text-xs font-medium shadow-lg transition-all ${
            toast.type === "success"
              ? "bg-green-600 text-white"
              : "bg-red-600 text-white"
          }`}
        >
          {toast.message}
        </div>
      )}
    </section>
  );
}
