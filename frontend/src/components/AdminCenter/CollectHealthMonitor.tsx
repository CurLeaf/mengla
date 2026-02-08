import { useEffect, useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  fetchCollectHealth,
  fetchSchedulerStatus,
  pauseScheduler,
  resumeScheduler,
  cancelAllTasks,
  purgeAllData,
  type CollectHealthResponse,
  type ActionStat,
  type EmptyStreak,
  type RecentRecord,
} from "../../services/mengla-admin-api";
import { REFETCH_INTERVALS } from "../../constants";

/* ---------- 常量 ---------- */
const ACTION_LABELS: Record<string, string> = {
  high: "蓝海Top",
  hot: "热销Top",
  chance: "潜力Top",
  industryViewV2: "行业概览",
  industryTrendRange: "行业趋势",
};

const LEVEL_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  critical: { bg: "bg-red-500/20", text: "text-red-400", label: "严重" },
  warning: { bg: "bg-amber-500/20", text: "text-amber-400", label: "警告" },
  info: { bg: "bg-blue-500/20", text: "text-blue-400", label: "提示" },
};

/* ---------- 子组件 ---------- */

function StatCard({
  label,
  value,
  sub,
  color = "white",
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl px-4 py-3">
      <p className="text-[10px] tracking-wider text-white/40 uppercase">{label}</p>
      <p className={`mt-1 text-2xl font-semibold text-${color}`}>{value}</p>
      {sub && <p className="mt-0.5 text-[10px] text-white/40">{sub}</p>}
    </div>
  );
}

function ActionStatRow({ action, stat }: { action: string; stat: ActionStat }) {
  const pct = stat.total > 0 ? Math.round((1 - stat.empty_rate) * 100) : 0;
  const barColor =
    pct >= 80 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500";

  return (
    <div className="flex items-center gap-3 py-2 border-b border-white/5 last:border-0">
      <span className="w-24 text-xs text-white/70 shrink-0">
        {ACTION_LABELS[action] || action}
      </span>
      <div className="flex-1 h-2 bg-white/5 rounded-full overflow-hidden">
        <div
          className={`h-full ${barColor} rounded-full transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-white/50 w-12 text-right">{pct}%</span>
      <span className="text-[10px] text-white/40 w-20 text-right">
        {stat.has_data}/{stat.total}
      </span>
    </div>
  );
}

function EmptyStreakRow({ streak }: { streak: EmptyStreak }) {
  const style = LEVEL_STYLES[streak.level] || LEVEL_STYLES.info;
  return (
    <div className="flex items-center gap-2 py-1.5 border-b border-white/5 last:border-0">
      <span
        className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${style.bg} ${style.text}`}
      >
        {style.label}
      </span>
      <span className="text-xs text-white/60">
        {ACTION_LABELS[streak.action] || streak.action}
      </span>
      <span className="text-[10px] text-white/40 font-mono">{streak.cat_id}</span>
      <span className="ml-auto text-xs text-white/50">
        连续 <strong className={style.text}>{streak.streak}</strong> 次为空
      </span>
    </div>
  );
}

function RecentRecordRow({ record }: { record: RecentRecord }) {
  const time = record.updated_at
    ? new Date(record.updated_at).toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "--";

  return (
    <div className="flex items-center gap-2 py-1.5 border-b border-white/5 last:border-0 text-xs">
      <span className="text-white/40 w-16 shrink-0 font-mono">{time}</span>
      <span className="text-white/60 w-20 shrink-0">
        {ACTION_LABELS[record.action] || record.action}
      </span>
      <span className="text-white/40 font-mono w-20 shrink-0 truncate">
        {record.cat_id || "-"}
      </span>
      <span className="text-white/40 w-10 shrink-0">{record.granularity}</span>
      {record.is_empty ? (
        <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-400">
          空数据
        </span>
      ) : (
        <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400">
          有数据
        </span>
      )}
      {record.empty_reason && (
        <span className="text-[10px] text-white/30 truncate">{record.empty_reason}</span>
      )}
    </div>
  );
}

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

/* ---------- 主组件 ---------- */

export function CollectHealthMonitor() {
  const [data, setData] = useState<CollectHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const load = useCallback(async () => {
    try {
      setError(null);
      const result = await fetchCollectHealth();
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // 自动刷新（15s）
  useEffect(() => {
    if (!autoRefresh) return;
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [autoRefresh, load]);

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-pulse flex flex-col items-center gap-3">
          <div className="h-6 w-6 rounded-full border-2 border-white/20 border-t-[#5E6AD2] animate-spin" />
          <span className="text-xs text-white/40">加载健康数据…</span>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="text-center py-20">
        <p className="text-red-400 text-sm">{error}</p>
        <button
          onClick={load}
          className="mt-3 px-3 py-1.5 text-xs bg-white/10 hover:bg-white/20 rounded-lg transition-colors"
        >
          重试
        </button>
      </div>
    );
  }

  if (!data) return null;

  const healthScore = (() => {
    const stats = Object.values(data.action_stats);
    if (stats.length === 0) return 100;
    const totalAll = stats.reduce((s, a) => s + a.total, 0);
    const dataAll = stats.reduce((s, a) => s + a.has_data, 0);
    return totalAll > 0 ? Math.round((dataAll / totalAll) * 100) : 100;
  })();

  const scoreColor =
    healthScore >= 80 ? "text-emerald-400" : healthScore >= 50 ? "text-amber-400" : "text-red-400";

  return (
    <div className="space-y-6">
      {/* 标题 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">采集健康监控</h2>
          <p className="text-xs text-white/40 mt-1">
            日期: {data.date} · 自动刷新{" "}
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`underline ${autoRefresh ? "text-emerald-400" : "text-white/40"}`}
            >
              {autoRefresh ? "开启" : "关闭"}
            </button>
          </p>
        </div>
        <button
          onClick={load}
          className="px-3 py-1.5 text-xs bg-white/10 hover:bg-white/20 border border-white/10 rounded-lg transition-colors"
        >
          刷新
        </button>
      </div>

      {/* 概览卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-white/5 border border-white/10 rounded-xl px-4 py-3">
          <p className="text-[10px] tracking-wider text-white/40 uppercase">健康评分</p>
          <p className={`mt-1 text-2xl font-semibold ${scoreColor}`}>{healthScore}%</p>
          <p className="mt-0.5 text-[10px] text-white/40">非空数据占比</p>
        </div>
        <StatCard
          label="总文档数"
          value={data.total_documents.toLocaleString()}
          sub={`空数据 ${data.empty_documents}`}
        />
        <StatCard
          label="Exec Key 堆积"
          value={data.exec_key_count}
          sub="Redis 中未消费的执行结果"
          color={data.exec_key_count > 50 ? "amber-400" : "white"}
        />
        <StatCard
          label="空数据告警"
          value={data.empty_streaks.length}
          sub={`${data.empty_streaks.filter((s) => s.level === "critical").length} 个严重`}
          color={data.empty_streaks.some((s) => s.level === "critical") ? "red-400" : "white"}
        />
      </div>

      {/* Action 数据率 */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-4">
        <h3 className="text-sm font-medium text-white/80 mb-3">各接口数据率</h3>
        {Object.entries(data.action_stats).map(([action, stat]) => (
          <ActionStatRow key={action} action={action} stat={stat} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 连续空数据告警 */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-4">
          <h3 className="text-sm font-medium text-white/80 mb-3">
            连续空数据告警
            {data.empty_streaks.length > 0 && (
              <span className="ml-2 text-[10px] text-white/40">
                ({data.empty_streaks.length} 项)
              </span>
            )}
          </h3>
          {data.empty_streaks.length === 0 ? (
            <p className="text-xs text-white/30 py-4 text-center">暂无告警</p>
          ) : (
            <div className="max-h-60 overflow-y-auto">
              {data.empty_streaks.map((s, i) => (
                <EmptyStreakRow key={i} streak={s} />
              ))}
            </div>
          )}
        </div>

        {/* 最近采集记录 */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-4">
          <h3 className="text-sm font-medium text-white/80 mb-3">最近采集记录</h3>
          {data.recent_records.length === 0 ? (
            <p className="text-xs text-white/30 py-4 text-center">暂无记录</p>
          ) : (
            <div className="max-h-60 overflow-y-auto">
              {data.recent_records.map((r, i) => (
                <RecentRecordRow key={i} record={r} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 调度器控制 */}
      <SchedulerControl />

      {/* 危险操作 */}
      <DangerZone />
    </div>
  );
}
