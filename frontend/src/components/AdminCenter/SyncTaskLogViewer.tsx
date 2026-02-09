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
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "../ui/table";
import { Select } from "../ui/select";
import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import { Card } from "../ui/card";

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
        <h2 className="text-sm font-semibold text-foreground">同步日志</h2>
        <p className="mt-2 text-xs text-muted-foreground">加载中…</p>
      </section>
    );
  }

  if (error) {
    return (
      <section>
        <h2 className="text-sm font-semibold text-foreground">同步日志</h2>
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
          <h2 className="text-sm font-semibold text-foreground">同步日志</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            查看当天的数据采集任务执行状态。
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-auto text-xs"
            aria-label="按状态筛选"
          >
            <option value="all">全部状态</option>
            <option value="RUNNING">运行中</option>
            <option value="COMPLETED">已完成</option>
            <option value="FAILED">失败</option>
            <option value="CANCELLED">已取消</option>
          </Select>
          <span className="text-xs text-muted-foreground">
            更新: {lastUpdated}
          </span>
        </div>
      </div>

      {/* ---- 调度器控制栏 ---- */}
      <Card className="px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
        {/* 左：调度器状态 */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span
              className={`inline-block w-2 h-2 rounded-full shrink-0 ${
                schedulerStatus?.state === "running"
                  ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]"
                  : schedulerStatus?.state === "paused"
                  ? "bg-amber-400 animate-pulse"
                  : "bg-muted-foreground/30"
              }`}
            />
            <span className="text-xs text-muted-foreground">调度器</span>
            {schedulerLoading ? (
              <span className="text-[10px] text-muted-foreground">加载中…</span>
            ) : (
              <span
                className={`text-xs font-medium ${
                  schedulerStatus?.state === "running"
                    ? "text-emerald-400"
                    : schedulerStatus?.state === "paused"
                    ? "text-amber-400"
                    : "text-muted-foreground"
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
            <span className="text-[10px] text-muted-foreground">
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
            <Button
              type="button"
              variant="outline"
              size="xs"
              onClick={() => resumeMut.mutate()}
              disabled={resumeMut.isPending}
              className="border-emerald-500/40 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 hover:text-emerald-400"
              title="恢复定时任务调度（每日采集、补数检查等将恢复自动触发）"
            >
              {resumeMut.isPending ? "恢复中…" : "恢复调度"}
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="xs"
              onClick={() => pauseMut.mutate()}
              disabled={pauseMut.isPending || schedulerStatus?.state === "stopped"}
              className="border-amber-500/40 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 hover:text-amber-400"
              title="暂停定时任务调度（阻止新定时任务触发，不影响正在运行的任务）"
            >
              {pauseMut.isPending ? "暂停中…" : "暂停调度"}
            </Button>
          )}

          {!cancelAllConfirm ? (
            <Button
              type="button"
              variant="outline"
              size="xs"
              onClick={() => setCancelAllConfirm(true)}
              disabled={cancelAllMut.isPending}
              className="border-red-500/40 bg-red-500/10 text-red-400 hover:bg-red-500/20 hover:text-red-400"
              title="立即终止所有正在运行的后台采集任务"
            >
              取消全部任务
            </Button>
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-red-300">确定？</span>
              <Button
                type="button"
                variant="destructive"
                size="xs"
                onClick={() => {
                  cancelAllMut.mutate();
                  setCancelAllConfirm(false);
                }}
                disabled={cancelAllMut.isPending}
                className="font-medium"
              >
                {cancelAllMut.isPending ? "取消中…" : "确认"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="xs"
                onClick={() => setCancelAllConfirm(false)}
                className="text-muted-foreground"
              >
                算了
              </Button>
            </div>
          )}
        </div>
      </Card>

      {tasks && tasks.length > 0 ? (() => {
        const filteredTasks = statusFilter === "all"
          ? tasks
          : tasks.filter((t) => t.status === statusFilter);
        return filteredTasks.length > 0 ? (
        <Card className="overflow-hidden">
          <Table role="table" aria-label="同步任务列表">
            <TableHeader>
              <TableRow>
                <TableHead>任务名称</TableHead>
                <TableHead className="w-20">状态</TableHead>
                <TableHead className="w-48">进度</TableHead>
                <TableHead className="w-20">开始时间</TableHead>
                <TableHead className="w-20">耗时</TableHead>
                <TableHead className="w-16">触发</TableHead>
                <TableHead className="w-24 text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredTasks.map((task) => (
                <TableRow key={task.id}>
                  <TableCell className="text-foreground">{task.task_name}</TableCell>
                  <TableCell>
                    <StatusBadge status={task.status} />
                  </TableCell>
                  <TableCell>
                    <ProgressBar progress={task.progress} />
                  </TableCell>
                  <TableCell className="text-muted-foreground font-mono">
                    {formatTime(task.started_at)}
                  </TableCell>
                  <TableCell className="text-muted-foreground font-mono">
                    {calcDuration(task.started_at, task.finished_at)}
                  </TableCell>
                  <TableCell>
                    <TriggerBadge trigger={task.trigger} />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      {task.status === "RUNNING" && (
                        <Button
                          variant="ghost"
                          size="xs"
                          onClick={() => setDialog({ type: "cancel", task })}
                          className="text-yellow-400 hover:text-yellow-400 hover:bg-yellow-500/20"
                          title="取消任务"
                        >
                          取消
                        </Button>
                      )}
                      {(task.status === "FAILED" || task.status === "CANCELLED") && (
                        retryConfirm === task.task_id ? (
                          <div className="flex items-center gap-1">
                            <Button
                              variant="default"
                              size="xs"
                              onClick={() => { retryMut.mutate(task.task_id); setRetryConfirm(null); }}
                              disabled={retryMut.isPending}
                              className="bg-emerald-600 hover:bg-emerald-700 text-white"
                            >
                              {retryMut.isPending ? "启动中…" : "确认"}
                            </Button>
                            <Button
                              variant="ghost"
                              size="xs"
                              onClick={() => setRetryConfirm(null)}
                              className="text-muted-foreground"
                            >
                              取消
                            </Button>
                          </div>
                        ) : (
                          <Button
                            variant="ghost"
                            size="xs"
                            onClick={() => setRetryConfirm(task.task_id)}
                            disabled={retryMut.isPending}
                            className="text-emerald-400 hover:text-emerald-400 hover:bg-emerald-500/20"
                            title="重新执行此任务"
                          >
                            重新执行
                          </Button>
                        )
                      )}
                      {task.status !== "RUNNING" && (
                        <Button
                          variant="ghost"
                          size="xs"
                          onClick={() => {
                            setDeleteData(false);
                            setDialog({ type: "delete", task });
                          }}
                          className="text-red-400 hover:text-red-400 hover:bg-red-500/20"
                          title="删除任务"
                        >
                          删除
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
        ) : (
        <Card className="p-8 text-center">
          <p className="text-sm text-muted-foreground">
            {statusFilter === "all" ? "没有符合条件的任务" : `没有"${statusFilter}"状态的任务`}
          </p>
          {statusFilter !== "all" && (
            <Button
              type="button"
              variant="link"
              size="sm"
              onClick={() => setStatusFilter("all")}
              className="mt-2"
            >
              查看全部任务
            </Button>
          )}
        </Card>
        );
      })() : (
        <Card className="p-8 text-center">
          <p className="text-sm text-muted-foreground">今天还没有同步任务</p>
          <p className="mt-1 text-xs text-muted-foreground/70">
            可以在"采集监控"中查看调度器状态或手动触发操作
          </p>
        </Card>
      )}

      {tasks && tasks.some((t) => t.error_message) && (
        <div className="space-y-2">
          <h3 className="text-xs font-medium text-muted-foreground">错误信息</h3>
          {tasks
            .filter((t) => t.error_message)
            .map((task) => (
              <div
                key={task.id}
                className="rounded border border-destructive/20 bg-destructive/10 p-3 text-xs text-red-400"
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
          <div className="flex items-center gap-2">
            <Checkbox
              id="delete-data-check"
              checked={deleteData}
              onCheckedChange={(checked) => setDeleteData(checked === true)}
            />
            <label htmlFor="delete-data-check" className="text-xs text-muted-foreground cursor-pointer">
              同时删除该任务采集的数据
            </label>
          </div>
        }
        onConfirm={handleDelete}
        onCancel={() => {
          setDialog({ type: "none" });
          setDeleteData(false);
        }}
      />

      {/* ---- 清空采集数据 ---- */}
      <Card className="border-destructive/20 bg-destructive/5 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-xs font-semibold text-red-400">清空采集数据和缓存</h3>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              删除 MongoDB 集合数据、Redis 缓存 key、L1 内存缓存（不可逆）
            </p>
          </div>
          {!purgeOpen ? (
            <Button
              type="button"
              variant="outline"
              size="xs"
              onClick={() => setPurgeOpen(true)}
              className="shrink-0 border-red-500/40 bg-red-500/10 text-red-400 hover:bg-red-500/20 hover:text-red-400"
            >
              清空数据…
            </Button>
          ) : (
            <Button
              type="button"
              variant="ghost"
              size="xs"
              onClick={() => setPurgeOpen(false)}
              className="shrink-0 text-muted-foreground"
            >
              取消
            </Button>
          )}
        </div>

        {purgeOpen && (
          <div className="rounded border border-red-500/30 bg-card p-3 space-y-3">
            <p className="text-[10px] text-red-300 font-medium">选择要清空的目标：</p>
            <div className="flex flex-wrap gap-3">
              {[
                { key: "mongodb", label: "MongoDB 数据", desc: "mengla_data, crawl_jobs, crawl_subtasks, sync_task_logs" },
                { key: "redis", label: "Redis 缓存", desc: "所有 mengla:* 前缀的 key" },
                { key: "l1", label: "L1 内存缓存", desc: "进程内 LRU 缓存" },
              ].map((t) => (
                <label
                  key={t.key}
                  htmlFor={`purge-${t.key}`}
                  className={`flex items-start gap-2 px-3 py-2 rounded border cursor-pointer transition-colors ${
                    purgeTargets.includes(t.key)
                      ? "border-red-500/50 bg-red-500/10"
                      : "border-border bg-muted/50"
                  }`}
                >
                  <Checkbox
                    id={`purge-${t.key}`}
                    checked={purgeTargets.includes(t.key)}
                    onCheckedChange={() => togglePurgeTarget(t.key)}
                    className="mt-0.5"
                  />
                  <div>
                    <p className="text-[10px] text-foreground/80">{t.label}</p>
                    <p className="text-[10px] text-muted-foreground">{t.desc}</p>
                  </div>
                </label>
              ))}
            </div>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={() => {
                if (purgeTargets.length === 0) return;
                purgeMut.mutate(purgeTargets);
              }}
              disabled={purgeMut.isPending || purgeTargets.length === 0}
              className="font-medium"
            >
              {purgeMut.isPending ? "清空中…" : "确认清空"}
            </Button>
          </div>
        )}
      </Card>

      {/* Toast 通过 sonner 全局渲染，无需本地 UI */}
    </section>
  );
}
