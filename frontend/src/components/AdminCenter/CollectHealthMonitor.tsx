import { useEffect, useState, useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  fetchCollectHealth,
  cancelAllTasks,
  purgeAllData,
  type CollectHealthResponse,
  type ActionStat,
  type EmptyStreak,
  type RecentRecord,
  type MongoStatus,
  type RedisStatus,
  type RequestPressure,
} from "../../services/mengla-admin-api";

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

const COLOR_MAP: Record<string, string> = {
  white: "text-white",
  "amber-400": "text-amber-400",
  "red-400": "text-red-400",
  "emerald-400": "text-emerald-400",
};

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
  const colorClass = COLOR_MAP[color] || "text-white";
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl px-4 py-3">
      <p className="text-[10px] tracking-wider text-white/40 uppercase">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${colorClass}`}>{value}</p>
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

/* ========== 基础设施状态面板 ========== */

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full shrink-0 ${
        ok ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]" : "bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.5)]"
      }`}
    />
  );
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
}

function InfraStatus({ mongo, redis }: { mongo: MongoStatus; redis: RedisStatus }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* MongoDB */}
      <div className="rounded-lg border border-white/10 bg-black/20 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <StatusDot ok={mongo.ok} />
          <h3 className="text-xs font-semibold text-white">MongoDB</h3>
          {mongo.latency_ms != null && (
            <span
              className={`ml-auto text-[10px] font-mono ${
                mongo.latency_ms < 50
                  ? "text-emerald-400"
                  : mongo.latency_ms < 200
                  ? "text-amber-400"
                  : "text-red-400"
              }`}
            >
              {mongo.latency_ms}ms
            </span>
          )}
        </div>

        {mongo.error ? (
          <p className="text-[10px] text-red-400 bg-red-500/10 rounded px-2 py-1.5">
            {mongo.error === "timeout" ? "连接超时 — MongoDB 可能负载过高" : mongo.error}
          </p>
        ) : (
          <div className="space-y-2">
            {/* 连接 */}
            {mongo.connections && (
              <div>
                <p className="text-[10px] text-white/40 mb-1">连接</p>
                <div className="grid grid-cols-3 gap-2">
                  <div className="bg-white/5 rounded px-2 py-1.5">
                    <p className="text-[10px] text-white/40">当前</p>
                    <p className="text-sm font-semibold text-white">{mongo.connections.current}</p>
                  </div>
                  <div className="bg-white/5 rounded px-2 py-1.5">
                    <p className="text-[10px] text-white/40">可用</p>
                    <p className="text-sm font-semibold text-white">{mongo.connections.available}</p>
                  </div>
                  <div className="bg-white/5 rounded px-2 py-1.5">
                    <p className="text-[10px] text-white/40">累计创建</p>
                    <p className="text-sm font-semibold text-white/70">{mongo.connections.total_created}</p>
                  </div>
                </div>
              </div>
            )}
            {/* 操作计数 */}
            {mongo.opcounters && (
              <div>
                <p className="text-[10px] text-white/40 mb-1">操作计数</p>
                <div className="grid grid-cols-3 gap-1">
                  {(["insert", "query", "update", "delete", "getmore", "command"] as const).map(
                    (op) => (
                      <div key={op} className="flex items-center justify-between px-2 py-1 bg-white/5 rounded text-[10px]">
                        <span className="text-white/40">{op}</span>
                        <span className="text-white/70 font-mono">
                          {(mongo.opcounters![op] ?? 0).toLocaleString()}
                        </span>
                      </div>
                    )
                  )}
                </div>
              </div>
            )}
            {/* 内存 */}
            {mongo.memory_mb && (
              <div className="flex gap-3 text-[10px]">
                <span className="text-white/40">
                  内存: <span className="text-white/70">{mongo.memory_mb.resident} MB (res)</span>
                </span>
                <span className="text-white/40">
                  <span className="text-white/70">{mongo.memory_mb.virtual} MB (virt)</span>
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Redis */}
      <div className="rounded-lg border border-white/10 bg-black/20 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <StatusDot ok={redis.ok} />
          <h3 className="text-xs font-semibold text-white">Redis</h3>
          {redis.version && (
            <span className="text-[10px] text-white/30 font-mono">v{redis.version}</span>
          )}
          {redis.latency_ms != null && (
            <span
              className={`ml-auto text-[10px] font-mono ${
                redis.latency_ms < 10
                  ? "text-emerald-400"
                  : redis.latency_ms < 50
                  ? "text-amber-400"
                  : "text-red-400"
              }`}
            >
              {redis.latency_ms}ms
            </span>
          )}
        </div>

        {redis.error ? (
          <p className="text-[10px] text-red-400 bg-red-500/10 rounded px-2 py-1.5">
            {redis.error === "timeout" ? "连接超时 — Redis 可能阻塞" : redis.error}
          </p>
        ) : (
          <div className="space-y-2">
            {/* 关键指标 */}
            <div className="grid grid-cols-3 gap-2">
              <div className="bg-white/5 rounded px-2 py-1.5">
                <p className="text-[10px] text-white/40">客户端</p>
                <p className="text-sm font-semibold text-white">
                  {redis.connected_clients ?? 0}
                  {(redis.blocked_clients ?? 0) > 0 && (
                    <span className="text-red-400 text-[10px] ml-1">
                      ({redis.blocked_clients} blocked)
                    </span>
                  )}
                </p>
              </div>
              <div className="bg-white/5 rounded px-2 py-1.5">
                <p className="text-[10px] text-white/40">Key 总数</p>
                <p className="text-sm font-semibold text-white">{(redis.total_keys ?? 0).toLocaleString()}</p>
              </div>
              <div className="bg-white/5 rounded px-2 py-1.5">
                <p className="text-[10px] text-white/40">OPS/s</p>
                <p className="text-sm font-semibold text-white">{redis.ops_per_sec ?? 0}</p>
              </div>
            </div>
            {/* 内存 & 命中率 */}
            <div className="grid grid-cols-3 gap-2">
              <div className="bg-white/5 rounded px-2 py-1.5">
                <p className="text-[10px] text-white/40">内存使用</p>
                <p className="text-xs font-semibold text-white">{redis.used_memory_human ?? "?"}</p>
                <p className="text-[10px] text-white/30">峰值 {redis.used_memory_peak_human ?? "?"}</p>
              </div>
              <div className="bg-white/5 rounded px-2 py-1.5">
                <p className="text-[10px] text-white/40">命中率</p>
                <p
                  className={`text-sm font-semibold ${
                    (redis.hit_rate ?? 0) >= 90
                      ? "text-emerald-400"
                      : (redis.hit_rate ?? 0) >= 70
                      ? "text-amber-400"
                      : "text-red-400"
                  }`}
                >
                  {redis.hit_rate ?? 0}%
                </p>
              </div>
              <div className="bg-white/5 rounded px-2 py-1.5">
                <p className="text-[10px] text-white/40">运行时间</p>
                <p className="text-xs font-semibold text-white">
                  {redis.uptime_seconds ? formatUptime(redis.uptime_seconds) : "?"}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ========== 请求压力面板 ========== */
function RequestPressurePanel({ pressure }: { pressure: RequestPressure }) {
  const usage = pressure.max_inflight > 0
    ? Math.round((pressure.inflight / pressure.max_inflight) * 100)
    : 0;
  const barColor =
    usage >= 100
      ? "bg-red-500"
      : usage >= 66
      ? "bg-amber-500"
      : "bg-emerald-500";
  const statusText =
    pressure.waiting > 0
      ? "排队中"
      : pressure.inflight > 0
      ? "活跃"
      : "空闲";
  const statusColor =
    pressure.waiting > 0
      ? "text-amber-400"
      : pressure.inflight > 0
      ? "text-emerald-400"
      : "text-white/40";

  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={`inline-block w-2 h-2 rounded-full shrink-0 ${
              pressure.waiting > 0
                ? "bg-amber-400 animate-pulse"
                : pressure.inflight > 0
                ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]"
                : "bg-white/20"
            }`}
          />
          <h3 className="text-xs font-semibold text-white">外部采集请求</h3>
        </div>
        <span className={`text-[10px] font-medium ${statusColor}`}>{statusText}</span>
      </div>

      {/* 占用率条 */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] text-white/40">
            并发占用 {pressure.inflight}/{pressure.max_inflight}
          </span>
          {pressure.waiting > 0 && (
            <span className="text-[10px] text-amber-400 animate-pulse">
              {pressure.waiting} 个请求排队等待
            </span>
          )}
        </div>
        <div className="h-2 bg-white/5 rounded-full overflow-hidden">
          <div
            className={`h-full ${barColor} rounded-full transition-all duration-500`}
            style={{ width: `${Math.min(usage, 100)}%` }}
          />
        </div>
      </div>

      {/* 统计 */}
      <div className="grid grid-cols-4 gap-2">
        <div className="bg-white/5 rounded px-2 py-1.5">
          <p className="text-[10px] text-white/40">已发送</p>
          <p className="text-sm font-semibold text-white">{pressure.total_sent}</p>
        </div>
        <div className="bg-white/5 rounded px-2 py-1.5">
          <p className="text-[10px] text-white/40">已完成</p>
          <p className="text-sm font-semibold text-emerald-400">{pressure.total_completed}</p>
        </div>
        <div className="bg-white/5 rounded px-2 py-1.5">
          <p className="text-[10px] text-white/40">超时</p>
          <p className={`text-sm font-semibold ${pressure.total_timeout > 0 ? "text-amber-400" : "text-white/50"}`}>
            {pressure.total_timeout}
          </p>
        </div>
        <div className="bg-white/5 rounded px-2 py-1.5">
          <p className="text-[10px] text-white/40">错误</p>
          <p className={`text-sm font-semibold ${pressure.total_error > 0 ? "text-red-400" : "text-white/50"}`}>
            {pressure.total_error}
          </p>
        </div>
      </div>
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

      {/* 请求压力 */}
      <RequestPressurePanel pressure={data.request_pressure} />

      {/* 基础设施状态 */}
      <InfraStatus mongo={data.mongo_status} redis={data.redis_status} />

      {/* 危险操作 */}
      <DangerZone />
    </div>
  );
}
