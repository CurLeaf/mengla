import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast as sonnerToast } from "sonner";
import {
  fetchTodaySyncTasks,
  cancelSyncTask,
  deleteSyncTask,
  type SyncTaskLog,
} from "../../services/sync-task-api";
import {
  fetchSchedulerStatus,
  pauseScheduler,
  resumeScheduler,
  cancelAllTasks,
  runPanelTask,
  purgeAllData,
} from "../../services/mengla-admin-api";
import { StatusBadge } from "./sync-task-log/StatusBadge";
import { ProgressBar } from "./sync-task-log/ProgressBar";
import { TriggerBadge } from "./sync-task-log/TriggerBadge";
import { ConfirmDialog } from "./sync-task-log/ConfirmDialog";

/**
 * 将后端返回的 UTC 时间字符串解析为 Date 对象。
 * 后端使用 datetime.utcnow() 存储，序列化时不带 'Z' 后缀，
 * 需要手动补充以确保被正确解析为 UTC 时间。
 */
function parseUTC(isoString: string): Date {
  // 如果已有时区信息（Z 或 ±HH:MM）则直接解析，否则追加 Z
  if (/[Zz]$/.test(isoString) || /[+-]\d{2}:\d{2}$/.test(isoString)) {
    return new Date(isoString);
  }
  return new Date(isoString + "Z");
}

/**
 * 格式化时间为 HH:mm:ss（本地时区）
 */
function formatTime(isoString: string | null): string {
  if (!isoString) return "-";
  const date = parseUTC(isoString);
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
  const start = parseUTC(startedAt).getTime();
  const end = finishedAt ? parseUTC(finishedAt).getTime() : Date.now();
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
  const [cancelAllConfirm, setCancelAllConfirm] = useState(false);
  const [retryConfirm, setRetryConfirm] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const showToast = useCallback((message: string, type: "success" | "error") => {
    if (type === "success") {
      sonnerToast.success(message);
    } else {
      sonnerToast.error(message);
    }
  }, []);

  // 调度器状态
  const { data: schedulerStatus, isLoading: schedulerLoading } = useQuery({
    queryKey: ["scheduler-status"],
    queryFn: fetchSchedulerStatus,
    refetchInterval: 5000,
  });

  const pauseMut = useMutation({
    mutationFn: pauseScheduler,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scheduler-status"] });
      showToast("调度器已暂停", "success");
    },
    onError: (e) => showToast(e instanceof Error ? e.message : "暂停失败", "error"),
  });

  const resumeMut = useMutation({
    mutationFn: resumeScheduler,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scheduler-status"] });
      showToast("调度器已恢复", "success");
    },
    onError: (e) => showToast(e instanceof Error ? e.message : "恢复失败", "error"),
  });

  const cancelAllMut = useMutation({
    mutationFn: cancelAllTasks,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["sync-tasks-today"] });
      queryClient.invalidateQueries({ queryKey: ["scheduler-status"] });
      showToast(
        `已取消: 异步任务 ${data.cancelled_asyncio_tasks}, 同步日志 ${data.cancelled_sync_logs}, 爬虫 ${data.cancelled_crawl_jobs}`,
        "success",
      );
    },
    onError: (e) => showToast(e instanceof Error ? e.message : "取消失败", "error"),
  });

  const retryMut = useMutation({
    mutationFn: (taskId: string) => runPanelTask(taskId),
    onSuccess: (_data, taskId) => {
      queryClient.invalidateQueries({ queryKey: ["sync-tasks-today"] });
      showToast(`任务 ${taskId} 已重新启动`, "success");
    },
    onError: (e) => showToast(e instanceof Error ? e.message : "重新执行失败", "error"),
  });

  const [purgeOpen, setPurgeOpen] = useState(false);
  const [purgeTargets, setPurgeTargets] = useState<string[]>(["mongodb", "redis", "l1"]);
  const purgeMut = useMutation({
    mutationFn: (targets: string[]) => purgeAllData(targets),
    onSuccess: (data) => {
      setPurgeOpen(false);
      queryClient.invalidateQueries();
      showToast(`清空完成: ${JSON.stringify(data.results)}`, "success");
    },
    onError: (e) => showToast(e instanceof Error ? e.message : "清空失败", "error"),
  });
  const togglePurgeTarget = (target: string) => {
    setPurgeTargets((prev) =>
      prev.includes(target) ? prev.filter((t) => t !== target) : [...prev, target],
    );
  };

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
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-sm font-semibold text-white">同步日志</h2>
          <p className="mt-1 text-xs text-white/60">
            查看当天的数据采集任务执行状态。
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-[#0F0F12] border border-white/10 rounded-lg px-2 py-1 text-xs text-white focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50"
            aria-label="按状态筛选"
          >
            <option value="all">全部状态</option>
            <option value="RUNNING">运行中</option>
            <option value="COMPLETED">已完成</option>
            <option value="FAILED">失败</option>
            <option value="CANCELLED">已取消</option>
          </select>
          <span className="text-xs text-white/40">
            更新: {lastUpdated}
          </span>
        </div>
      </div>

      {/* ---- 调度器控制栏 ---- */}
      <div className="rounded-lg border border-white/10 bg-black/20 px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
        {/* 左：调度器状态 */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span
              className={`inline-block w-2 h-2 rounded-full shrink-0 ${
                schedulerStatus?.state === "running"
                  ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]"
                  : schedulerStatus?.state === "paused"
                  ? "bg-amber-400 animate-pulse"
                  : "bg-white/20"
              }`}
            />
            <span className="text-xs text-white/70">调度器</span>
            {schedulerLoading ? (
              <span className="text-[10px] text-white/40">加载中…</span>
            ) : (
              <span
                className={`text-xs font-medium ${
                  schedulerStatus?.state === "running"
                    ? "text-emerald-400"
                    : schedulerStatus?.state === "paused"
                    ? "text-amber-400"
                    : "text-white/40"
                }`}
              >
                {schedulerStatus?.state === "running"
                  ? "运行中"
                  : schedulerStatus?.state === "paused"
                  ? "已暂停"
                  : schedulerStatus?.state === "stopped"
                  ? "已停止"
                  : "未知"}
              </span>
            )}
          </div>
          {schedulerStatus && (
            <span className="text-[10px] text-white/40">
              活跃 {schedulerStatus.active_jobs.length} · 暂停 {schedulerStatus.paused_jobs.length} · 后台 {schedulerStatus.background_tasks}
            </span>
          )}
        </div>

        {/* 中：提示 */}
        {schedulerStatus?.state === "paused" && (
          <span className="text-[10px] text-amber-400/80">
            已暂停：不会触发新的定时任务，已在运行的任务不受影响
          </span>
        )}

        {/* 右：操作按钮 */}
        <div className="flex items-center gap-2">
          {schedulerStatus?.state === "paused" ? (
            <button
              type="button"
              onClick={() => resumeMut.mutate()}
              disabled={resumeMut.isPending}
              className="px-3 py-1.5 text-xs rounded border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-50 transition-colors"
              title="恢复定时任务调度（每日采集、补数检查等将恢复自动触发）"
            >
              {resumeMut.isPending ? "恢复中…" : "恢复调度"}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => pauseMut.mutate()}
              disabled={pauseMut.isPending || schedulerStatus?.state === "stopped"}
              className="px-3 py-1.5 text-xs rounded border border-amber-500/40 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 disabled:opacity-50 transition-colors"
              title="暂停定时任务调度（阻止新定时任务触发，不影响正在运行的任务）"
            >
              {pauseMut.isPending ? "暂停中…" : "暂停调度"}
            </button>
          )}

          {!cancelAllConfirm ? (
            <button
              type="button"
              onClick={() => setCancelAllConfirm(true)}
              disabled={cancelAllMut.isPending}
              className="px-3 py-1.5 text-xs rounded border border-red-500/40 bg-red-500/10 text-red-400 hover:bg-red-500/20 disabled:opacity-50 transition-colors"
              title="立即终止所有正在运行的后台采集任务"
            >
              取消全部任务
            </button>
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-red-300">确定？</span>
              <button
                type="button"
                onClick={() => {
                  cancelAllMut.mutate();
                  setCancelAllConfirm(false);
                }}
                disabled={cancelAllMut.isPending}
                className="px-2.5 py-1 text-xs rounded bg-red-600 hover:bg-red-700 text-white font-medium disabled:opacity-50 transition-colors"
              >
                {cancelAllMut.isPending ? "取消中…" : "确认"}
              </button>
              <button
                type="button"
                onClick={() => setCancelAllConfirm(false)}
                className="px-2.5 py-1 text-xs rounded border border-white/20 text-white/50 hover:bg-white/5 transition-colors"
              >
                算了
              </button>
            </div>
          )}
        </div>
      </div>

      {tasks && tasks.length > 0 ? (() => {
        const filteredTasks = statusFilter === "all"
          ? tasks
          : tasks.filter((t) => t.status === statusFilter);
        return filteredTasks.length > 0 ? (
        <div className="rounded-lg border border-white/10 bg-black/20 overflow-hidden">
          <table className="w-full text-left text-xs" role="table" aria-label="同步任务列表">
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
              {filteredTasks.map((task) => (
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
                      {(task.status === "FAILED" || task.status === "CANCELLED") && (
                        retryConfirm === task.task_id ? (
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => { retryMut.mutate(task.task_id); setRetryConfirm(null); }}
                              disabled={retryMut.isPending}
                              className="rounded px-2 py-1 text-xs bg-emerald-600 hover:bg-emerald-700 text-white disabled:opacity-50 transition-colors"
                            >
                              {retryMut.isPending ? "启动中…" : "确认"}
                            </button>
                            <button
                              onClick={() => setRetryConfirm(null)}
                              className="rounded px-2 py-1 text-xs text-white/50 hover:bg-white/5 transition-colors"
                            >
                              取消
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setRetryConfirm(task.task_id)}
                            disabled={retryMut.isPending}
                            className="rounded px-2 py-1 text-xs text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-50 transition-colors"
                            title="重新执行此任务"
                          >
                            重新执行
                          </button>
                        )
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
          <p className="text-sm text-white/40">
            {statusFilter === "all" ? "没有符合条件的任务" : `没有"${statusFilter}"状态的任务`}
          </p>
          {statusFilter !== "all" && (
            <button
              type="button"
              onClick={() => setStatusFilter("all")}
              className="mt-2 text-xs text-[#5E6AD2] hover:underline"
            >
              查看全部任务
            </button>
          )}
        </div>
        );
      })() : (
        <div className="rounded-lg border border-white/10 bg-black/20 p-8 text-center">
          <p className="text-sm text-white/40">今天还没有同步任务</p>
          <p className="mt-1 text-xs text-white/30">
            可以在"采集监控"中查看调度器状态或手动触发操作
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

      {/* ---- 清空采集数据 ---- */}
      <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-xs font-semibold text-red-400">清空采集数据和缓存</h3>
            <p className="text-[10px] text-white/40 mt-0.5">
              删除 MongoDB 集合数据、Redis 缓存 key、L1 内存缓存（不可逆）
            </p>
          </div>
          {!purgeOpen ? (
            <button
              type="button"
              onClick={() => setPurgeOpen(true)}
              className="shrink-0 px-3 py-1.5 text-xs rounded border border-red-500/40 bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
            >
              清空数据…
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setPurgeOpen(false)}
              className="shrink-0 px-3 py-1.5 text-xs rounded border border-white/20 text-white/50 hover:bg-white/5 transition-colors"
            >
              取消
            </button>
          )}
        </div>

        {purgeOpen && (
          <div className="rounded border border-red-500/30 bg-black/30 p-3 space-y-3">
            <p className="text-[10px] text-red-300 font-medium">选择要清空的目标：</p>
            <div className="flex flex-wrap gap-3">
              {[
                { key: "mongodb", label: "MongoDB 数据", desc: "mengla_data, crawl_jobs, crawl_subtasks, sync_task_logs" },
                { key: "redis", label: "Redis 缓存", desc: "所有 mengla:* 前缀的 key" },
                { key: "l1", label: "L1 内存缓存", desc: "进程内 LRU 缓存" },
              ].map((t) => (
                <label
                  key={t.key}
                  className={`flex items-start gap-2 px-3 py-2 rounded border cursor-pointer transition-colors ${
                    purgeTargets.includes(t.key)
                      ? "border-red-500/50 bg-red-500/10"
                      : "border-white/10 bg-white/5"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={purgeTargets.includes(t.key)}
                    onChange={() => togglePurgeTarget(t.key)}
                    className="mt-0.5 accent-red-500"
                  />
                  <div>
                    <p className="text-[10px] text-white/80">{t.label}</p>
                    <p className="text-[10px] text-white/40">{t.desc}</p>
                  </div>
                </label>
              ))}
            </div>
            <button
              type="button"
              onClick={() => {
                if (purgeTargets.length === 0) return;
                purgeMut.mutate(purgeTargets);
              }}
              disabled={purgeMut.isPending || purgeTargets.length === 0}
              className="px-4 py-1.5 text-xs rounded bg-red-600 hover:bg-red-700 text-white font-medium disabled:opacity-50 transition-colors"
            >
              {purgeMut.isPending ? "清空中…" : "确认清空"}
            </button>
          </div>
        )}
      </div>

      {/* Toast 通过 sonner 全局渲染，无需本地 UI */}
    </section>
  );
}
