import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  fetchPanelTasks,
  runPanelTask,
  fetchSchedulerStatus,
  pauseScheduler,
  resumeScheduler,
  cancelAllTasks,
  purgeAllData,
} from "../../services/mengla-admin-api";
import { REFETCH_INTERVALS } from "../../constants";

/* ========== 调度器控制面板 ========== */
function SchedulerControl() {
  const queryClient = useQueryClient();
  const { data: status, isLoading } = useQuery({
    queryKey: ["scheduler-status"],
    queryFn: fetchSchedulerStatus,
    refetchInterval: REFETCH_INTERVALS.scheduler,
  });

  const pauseMut = useMutation({
    mutationFn: pauseScheduler,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scheduler-status"] }),
  });
  const resumeMut = useMutation({
    mutationFn: resumeScheduler,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scheduler-status"] }),
  });

  const isPaused = status?.state === "paused";
  const stateLabel = status?.state === "running" ? "运行中" : status?.state === "paused" ? "已暂停" : status?.state === "stopped" ? "已停止" : "未知";
  const stateColor = status?.state === "running" ? "text-emerald-400" : status?.state === "paused" ? "text-amber-400" : "text-white/40";

  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xs font-semibold text-white">调度器状态</h3>
          {isLoading ? (
            <p className="text-[10px] text-white/40 mt-1">加载中…</p>
          ) : (
            <p className="text-[10px] text-white/50 mt-1">
              <span className={stateColor}>{stateLabel}</span> · 
              活跃任务 {status?.active_jobs.length ?? 0} · 
              已暂停 {status?.paused_jobs.length ?? 0} · 
              后台任务 {status?.background_tasks ?? 0}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isPaused ? (
            <button
              type="button"
              onClick={() => resumeMut.mutate()}
              disabled={resumeMut.isPending}
              className="px-3 py-1.5 text-[10px] rounded border border-emerald-500/40 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-50 transition-colors"
            >
              {resumeMut.isPending ? "恢复中…" : "恢复调度"}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => pauseMut.mutate()}
              disabled={pauseMut.isPending}
              className="px-3 py-1.5 text-[10px] rounded border border-amber-500/40 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 disabled:opacity-50 transition-colors"
            >
              {pauseMut.isPending ? "暂停中…" : "暂停调度"}
            </button>
          )}
        </div>
      </div>

      {(pauseMut.isError || resumeMut.isError) && (
        <p className="text-[10px] text-red-400">
          {String(pauseMut.error || resumeMut.error)}
        </p>
      )}

      {/* 定时任务列表 */}
      {status && status.active_jobs.length + status.paused_jobs.length > 0 && (
        <div className="mt-2 space-y-1">
          <p className="text-[10px] font-mono text-white/40">定时任务</p>
          <div className="grid gap-1">
            {[...status.active_jobs, ...status.paused_jobs].map((job) => (
              <div
                key={job.id}
                className="flex items-center justify-between px-3 py-1.5 rounded bg-white/5 text-[10px]"
              >
                <span className="text-white/70">{job.name}</span>
                <span className={job.next_run === "None" ? "text-amber-400/70" : "text-white/40"}>
                  {job.next_run === "None" ? "已暂停" : job.next_run}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ========== 危险操作面板 ========== */
function DangerZone() {
  const queryClient = useQueryClient();
  const [cancelConfirmOpen, setCancelConfirmOpen] = useState(false);
  const [purgeConfirmOpen, setPurgeConfirmOpen] = useState(false);
  const [purgeTargets, setPurgeTargets] = useState<string[]>(["mongodb", "redis", "l1"]);

  const cancelMut = useMutation({
    mutationFn: cancelAllTasks,
    onSuccess: (data) => {
      setCancelConfirmOpen(false);
      queryClient.invalidateQueries({ queryKey: ["scheduler-status"] });
      queryClient.invalidateQueries({ queryKey: ["panel-tasks"] });
      toast.success("已取消任务", {
        description: `异步任务: ${data.cancelled_asyncio_tasks}, 同步日志: ${data.cancelled_sync_logs}, 爬虫任务: ${data.cancelled_crawl_jobs}, 子任务: ${data.cancelled_crawl_subtasks}`,
      });
    },
  });

  const purgeMut = useMutation({
    mutationFn: (targets: string[]) => purgeAllData(targets),
    onSuccess: (data) => {
      setPurgeConfirmOpen(false);
      queryClient.invalidateQueries();
      toast.success("清空完成", {
        description: JSON.stringify(data.results, null, 2),
      });
    },
  });

  const toggleTarget = (target: string) => {
    setPurgeTargets((prev) =>
      prev.includes(target) ? prev.filter((t) => t !== target) : [...prev, target]
    );
  };

  return (
    <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4 space-y-4">
      <div>
        <h3 className="text-xs font-semibold text-red-400">危险操作</h3>
        <p className="text-[10px] text-white/40 mt-1">以下操作不可逆，请谨慎执行。</p>
      </div>

      {/* 取消所有任务 */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-white/80">取消所有运行中的任务</p>
          <p className="text-[10px] text-white/40">
            终止后台 asyncio 任务，标记 MongoDB 中运行中的同步日志和爬虫任务为失败/取消
          </p>
        </div>
        {!cancelConfirmOpen ? (
          <button
            type="button"
            onClick={() => setCancelConfirmOpen(true)}
            disabled={cancelMut.isPending}
            className="shrink-0 px-3 py-1.5 text-[10px] rounded border border-red-500/40 bg-red-500/10 text-red-400 hover:bg-red-500/20 disabled:opacity-50 transition-colors"
            aria-label="取消所有任务"
          >
            {cancelMut.isPending ? "取消中…" : "取消全部"}
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-red-300">确定取消全部？</span>
            <button
              type="button"
              onClick={() => cancelMut.mutate()}
              disabled={cancelMut.isPending}
              className="px-3 py-1 text-[10px] rounded bg-red-600 hover:bg-red-700 text-white font-medium disabled:opacity-50 transition-colors"
            >
              {cancelMut.isPending ? "取消中…" : "确认"}
            </button>
            <button
              type="button"
              onClick={() => setCancelConfirmOpen(false)}
              className="px-3 py-1 text-[10px] rounded border border-white/20 text-white/50 hover:bg-white/5 transition-colors"
            >
              取消
            </button>
          </div>
        )}
      </div>

      {cancelMut.isError && (
        <p className="text-[10px] text-red-400">{String(cancelMut.error)}</p>
      )}

      <hr className="border-white/10" />

      {/* 清空数据 */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-white/80">清空采集数据和缓存</p>
            <p className="text-[10px] text-white/40">
              删除 MongoDB 集合数据、Redis 缓存 key、L1 内存缓存
            </p>
          </div>
          {!purgeConfirmOpen ? (
            <button
              type="button"
              onClick={() => setPurgeConfirmOpen(true)}
              className="shrink-0 px-3 py-1.5 text-[10px] rounded border border-red-500/40 bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
            >
              清空数据…
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setPurgeConfirmOpen(false)}
              className="shrink-0 px-3 py-1.5 text-[10px] rounded border border-white/20 text-white/50 hover:bg-white/5 transition-colors"
            >
              取消
            </button>
          )}
        </div>

        {purgeConfirmOpen && (
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
                    onChange={() => toggleTarget(t.key)}
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
                if (purgeTargets.length === 0) {
                  toast.warning("请至少选择一个清空目标");
                  return;
                }
                purgeMut.mutate(purgeTargets);
              }}
              disabled={purgeMut.isPending}
              className="px-4 py-1.5 text-[10px] rounded bg-red-600 hover:bg-red-700 text-white font-medium disabled:opacity-50 transition-colors"
              aria-label="确认清空数据"
            >
              {purgeMut.isPending ? "清空中…" : "确认清空"}
            </button>
            {purgeMut.isError && (
              <p className="text-[10px] text-red-400">{String(purgeMut.error)}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ========== 主组件 ========== */
export function DataSourceTaskManager() {
  const queryClient = useQueryClient();
  const { data: tasks, isLoading, error } = useQuery({
    queryKey: ["panel-tasks"],
    queryFn: fetchPanelTasks,
  });

  const runMutation = useMutation({
    mutationFn: runPanelTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["panel-tasks"] });
    },
  });

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-sm font-semibold text-white">任务管理</h2>
        <p className="mt-1 text-xs text-white/60">
          查看与手动触发行业面板相关的数据抓取/计算任务，控制调度器和管理数据。
        </p>
      </div>

      {/* 调度器控制 */}
      <SchedulerControl />

      {/* 任务列表 */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold text-white/80">手动任务</h3>
        {isLoading ? (
          <p className="text-xs text-white/40">加载中…</p>
        ) : error ? (
          <p className="text-xs text-red-400">{String(error)}</p>
        ) : (
          <div className="rounded-lg border border-white/10 bg-black/20 overflow-hidden">
            <table className="w-full text-left text-xs" role="table" aria-label="手动任务列表">
              <thead>
                <tr className="border-b border-white/10 text-white/60">
                  <th className="px-4 py-2.5 font-medium">ID</th>
                  <th className="px-4 py-2.5 font-medium">名称</th>
                  <th className="px-4 py-2.5 font-medium">说明</th>
                  <th className="px-4 py-2.5 font-medium w-24">操作</th>
                </tr>
              </thead>
              <tbody>
                {(tasks ?? []).map((t) => (
                  <tr key={t.id} className="border-b border-white/5 hover:bg-white/5">
                    <td className="px-4 py-2.5 font-mono text-white/80">{t.id}</td>
                    <td className="px-4 py-2.5 text-white">{t.name}</td>
                    <td className="px-4 py-2.5 text-white/60">{t.description}</td>
                    <td className="px-4 py-2.5">
                      <button
                        type="button"
                        onClick={() => runMutation.mutate(t.id)}
                        disabled={runMutation.isPending}
                        className="px-2 py-1 rounded border border-white/10 text-white/80 hover:bg-white/10 disabled:opacity-50"
                      >
                        {runMutation.isPending && runMutation.variables === t.id
                          ? "执行中…"
                          : "立即执行"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {runMutation.isError && (
          <p className="text-xs text-red-400">{String(runMutation.error)}</p>
        )}
      </div>

      {/* 危险操作 */}
      <DangerZone />
    </section>
  );
}
