import { useEffect, useState, useCallback } from "react";
import { Loader2 } from "lucide-react";
import {
  fetchCollectHealth,
  type CollectHealthResponse,
  type ActionStat,
  type EmptyStreak,
  type RecentRecord,
  type MongoStatus,
  type RedisStatus,
  type RequestPressure,
} from "../../services/mengla-admin-api";
import { Card, CardContent } from "../ui/card";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";

/* ---------- 常量 ---------- */
const ACTION_LABELS: Record<string, string> = {
  high: "蓝海Top",
  hot: "热销Top",
  chance: "潜力Top",
  industryViewV2: "行业概览",
  industryTrendRange: "行业趋势",
};

const LEVEL_BADGE_VARIANT: Record<string, "destructive" | "warning" | "info"> = {
  critical: "destructive",
  warning: "warning",
  info: "info",
};

const LEVEL_LABELS: Record<string, string> = {
  critical: "严重",
  warning: "警告",
  info: "提示",
};

const LEVEL_TEXT_COLOR: Record<string, string> = {
  critical: "text-red-400",
  warning: "text-amber-400",
  info: "text-blue-400",
};

/* ---------- 子组件 ---------- */

const COLOR_MAP: Record<string, string> = {
  white: "text-foreground",
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
  const colorClass = COLOR_MAP[color] || "text-foreground";
  return (
    <Card>
      <CardContent className="px-4 py-3">
        <p className="text-[10px] tracking-wider text-muted-foreground uppercase">{label}</p>
        <p className={`mt-1 text-2xl font-semibold ${colorClass}`}>{value}</p>
        {sub && <p className="mt-0.5 text-[10px] text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function ActionStatRow({ action, stat }: { action: string; stat: ActionStat }) {
  const pct = stat.total > 0 ? Math.round((1 - stat.empty_rate) * 100) : 0;
  const barColor =
    pct >= 80 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500";

  return (
    <div className="flex items-center gap-3 py-2 border-b border-border/50 last:border-0">
      <span className="w-24 text-xs text-muted-foreground shrink-0">
        {ACTION_LABELS[action] || action}
      </span>
      <div className="flex-1 h-2 bg-muted/50 rounded-full overflow-hidden">
        <div
          className={`h-full ${barColor} rounded-full transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground w-12 text-right">{pct}%</span>
      <span className="text-[10px] text-muted-foreground w-20 text-right">
        {stat.has_data}/{stat.total}
      </span>
    </div>
  );
}

function EmptyStreakRow({ streak }: { streak: EmptyStreak }) {
  const variant = LEVEL_BADGE_VARIANT[streak.level] || "info";
  const textColor = LEVEL_TEXT_COLOR[streak.level] || "text-blue-400";
  return (
    <div className="flex items-center gap-2 py-1.5 border-b border-border/50 last:border-0">
      <Badge variant={variant} className="rounded text-[10px] px-1.5 py-0.5">
        {LEVEL_LABELS[streak.level] || "提示"}
      </Badge>
      <span className="text-xs text-muted-foreground">
        {ACTION_LABELS[streak.action] || streak.action}
      </span>
      <span className="text-[10px] text-muted-foreground font-mono">{streak.cat_id}</span>
      <span className="ml-auto text-xs text-muted-foreground">
        连续 <strong className={textColor}>{streak.streak}</strong> 次为空
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
    <div className="flex items-center gap-2 py-1.5 border-b border-border/50 last:border-0 text-xs">
      <span className="text-muted-foreground w-16 shrink-0 font-mono">{time}</span>
      <span className="text-muted-foreground w-20 shrink-0">
        {ACTION_LABELS[record.action] || record.action}
      </span>
      <span className="text-muted-foreground font-mono w-20 shrink-0 truncate">
        {record.cat_id || "-"}
      </span>
      <span className="text-muted-foreground w-10 shrink-0">{record.granularity}</span>
      {record.is_empty ? (
        <Badge variant="warning" className="rounded text-[10px] px-1.5 py-0.5">
          空数据
        </Badge>
      ) : (
        <Badge variant="success" className="rounded text-[10px] px-1.5 py-0.5">
          有数据
        </Badge>
      )}
      {record.empty_reason && (
        <span className="text-[10px] text-muted-foreground truncate">{record.empty_reason}</span>
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
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-2">
            <StatusDot ok={mongo.ok} />
            <h3 className="text-xs font-semibold text-foreground">MongoDB</h3>
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
                  <p className="text-[10px] text-muted-foreground mb-1">连接</p>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="bg-muted/50 rounded px-2 py-1.5">
                      <p className="text-[10px] text-muted-foreground">当前</p>
                      <p className="text-sm font-semibold text-foreground">{mongo.connections.current}</p>
                    </div>
                    <div className="bg-muted/50 rounded px-2 py-1.5">
                      <p className="text-[10px] text-muted-foreground">可用</p>
                      <p className="text-sm font-semibold text-foreground">{mongo.connections.available}</p>
                    </div>
                    <div className="bg-muted/50 rounded px-2 py-1.5">
                      <p className="text-[10px] text-muted-foreground">累计创建</p>
                      <p className="text-sm font-semibold text-muted-foreground">{mongo.connections.total_created}</p>
                    </div>
                  </div>
                </div>
              )}
              {/* 操作计数 */}
              {mongo.opcounters && (
                <div>
                  <p className="text-[10px] text-muted-foreground mb-1">操作计数</p>
                  <div className="grid grid-cols-3 gap-1">
                    {(["insert", "query", "update", "delete", "getmore", "command"] as const).map(
                      (op) => (
                        <div key={op} className="flex items-center justify-between px-2 py-1 bg-muted/50 rounded text-[10px]">
                          <span className="text-muted-foreground">{op}</span>
                          <span className="text-muted-foreground font-mono">
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
                  <span className="text-muted-foreground">
                    内存: <span className="text-foreground/70">{mongo.memory_mb.resident} MB (res)</span>
                  </span>
                  <span className="text-muted-foreground">
                    <span className="text-foreground/70">{mongo.memory_mb.virtual} MB (virt)</span>
                  </span>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Redis */}
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-2">
            <StatusDot ok={redis.ok} />
            <h3 className="text-xs font-semibold text-foreground">Redis</h3>
            {redis.version && (
              <span className="text-[10px] text-muted-foreground font-mono">v{redis.version}</span>
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
                <div className="bg-muted/50 rounded px-2 py-1.5">
                  <p className="text-[10px] text-muted-foreground">客户端</p>
                  <p className="text-sm font-semibold text-foreground">
                    {redis.connected_clients ?? 0}
                    {(redis.blocked_clients ?? 0) > 0 && (
                      <span className="text-red-400 text-[10px] ml-1">
                        ({redis.blocked_clients} blocked)
                      </span>
                    )}
                  </p>
                </div>
                <div className="bg-muted/50 rounded px-2 py-1.5">
                  <p className="text-[10px] text-muted-foreground">Key 总数</p>
                  <p className="text-sm font-semibold text-foreground">{(redis.total_keys ?? 0).toLocaleString()}</p>
                </div>
                <div className="bg-muted/50 rounded px-2 py-1.5">
                  <p className="text-[10px] text-muted-foreground">OPS/s</p>
                  <p className="text-sm font-semibold text-foreground">{redis.ops_per_sec ?? 0}</p>
                </div>
              </div>
              {/* 内存 & 命中率 */}
              <div className="grid grid-cols-3 gap-2">
                <div className="bg-muted/50 rounded px-2 py-1.5">
                  <p className="text-[10px] text-muted-foreground">内存使用</p>
                  <p className="text-xs font-semibold text-foreground">{redis.used_memory_human ?? "?"}</p>
                  <p className="text-[10px] text-muted-foreground">峰值 {redis.used_memory_peak_human ?? "?"}</p>
                </div>
                <div className="bg-muted/50 rounded px-2 py-1.5">
                  <p className="text-[10px] text-muted-foreground">命中率</p>
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
                <div className="bg-muted/50 rounded px-2 py-1.5">
                  <p className="text-[10px] text-muted-foreground">运行时间</p>
                  <p className="text-xs font-semibold text-foreground">
                    {redis.uptime_seconds ? formatUptime(redis.uptime_seconds) : "?"}
                  </p>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
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
      : "text-muted-foreground";

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className={`inline-block w-2 h-2 rounded-full shrink-0 ${
                pressure.waiting > 0
                  ? "bg-amber-400 animate-pulse"
                  : pressure.inflight > 0
                  ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]"
                  : "bg-muted-foreground/30"
              }`}
            />
            <h3 className="text-xs font-semibold text-foreground">外部采集请求</h3>
          </div>
          <span className={`text-[10px] font-medium ${statusColor}`}>{statusText}</span>
        </div>

        {/* 占用率条 */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] text-muted-foreground">
              并发占用 {pressure.inflight}/{pressure.max_inflight}
            </span>
            {pressure.waiting > 0 && (
              <span className="text-[10px] text-amber-400 animate-pulse">
                {pressure.waiting} 个请求排队等待
              </span>
            )}
          </div>
          <div className="h-2 bg-muted/50 rounded-full overflow-hidden">
            <div
              className={`h-full ${barColor} rounded-full transition-all duration-500`}
              style={{ width: `${Math.min(usage, 100)}%` }}
            />
          </div>
        </div>

        {/* 统计 */}
        <div className="grid grid-cols-4 gap-2">
          <div className="bg-muted/50 rounded px-2 py-1.5">
            <p className="text-[10px] text-muted-foreground">已发送</p>
            <p className="text-sm font-semibold text-foreground">{pressure.total_sent}</p>
          </div>
          <div className="bg-muted/50 rounded px-2 py-1.5">
            <p className="text-[10px] text-muted-foreground">已完成</p>
            <p className="text-sm font-semibold text-emerald-400">{pressure.total_completed}</p>
          </div>
          <div className="bg-muted/50 rounded px-2 py-1.5">
            <p className="text-[10px] text-muted-foreground">超时</p>
            <p className={`text-sm font-semibold ${pressure.total_timeout > 0 ? "text-amber-400" : "text-muted-foreground"}`}>
              {pressure.total_timeout}
            </p>
          </div>
          <div className="bg-muted/50 rounded px-2 py-1.5">
            <p className="text-[10px] text-muted-foreground">错误</p>
            <p className={`text-sm font-semibold ${pressure.total_error > 0 ? "text-red-400" : "text-muted-foreground"}`}>
              {pressure.total_error}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
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

  // 自动刷新（15s），标签页不可见时暂停
  useEffect(() => {
    if (!autoRefresh) return;
    let timer: ReturnType<typeof setInterval> | null = null;

    const startTimer = () => {
      if (timer) clearInterval(timer);
      timer = setInterval(load, 15000);
    };

    const handleVisibilityChange = () => {
      if (document.hidden) {
        if (timer) { clearInterval(timer); timer = null; }
      } else {
        load(); // 恢复时立即刷新一次
        startTimer();
      }
    };

    startTimer();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      if (timer) clearInterval(timer);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [autoRefresh, load]);

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
          <span className="text-xs text-muted-foreground">加载健康数据…</span>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="text-center py-20">
        <p className="text-red-400 text-sm">{error}</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={load}>
          重试
        </Button>
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
          <h2 className="text-lg font-semibold text-foreground">采集健康监控</h2>
          <p className="text-xs text-muted-foreground mt-1">
            日期: {data.date} · 自动刷新{" "}
            <Button
              variant="link"
              className={`p-0 h-auto text-xs ${autoRefresh ? "text-emerald-400" : "text-muted-foreground"}`}
              onClick={() => setAutoRefresh(!autoRefresh)}
            >
              {autoRefresh ? "开启" : "关闭"}
            </Button>
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load}>
          刷新
        </Button>
      </div>

      {/* 概览卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card>
          <CardContent className="px-4 py-3">
            <p className="text-[10px] tracking-wider text-muted-foreground uppercase">健康评分</p>
            <p className={`mt-1 text-2xl font-semibold ${scoreColor}`}>{healthScore}%</p>
            <p className="mt-0.5 text-[10px] text-muted-foreground">非空数据占比</p>
          </CardContent>
        </Card>
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
      <Card>
        <CardContent className="p-4">
          <h3 className="text-sm font-medium text-muted-foreground mb-3">各接口数据率</h3>
          {Object.entries(data.action_stats).map(([action, stat]) => (
            <ActionStatRow key={action} action={action} stat={stat} />
          ))}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 连续空数据告警 */}
        <Card>
          <CardContent className="p-4">
            <h3 className="text-sm font-medium text-muted-foreground mb-3">
              连续空数据告警
              {data.empty_streaks.length > 0 && (
                <span className="ml-2 text-[10px] text-muted-foreground">
                  ({data.empty_streaks.length} 项)
                </span>
              )}
            </h3>
            {data.empty_streaks.length === 0 ? (
              <p className="text-xs text-muted-foreground py-4 text-center">暂无告警</p>
            ) : (
              <div className="max-h-60 overflow-y-auto">
                {data.empty_streaks.map((s, i) => (
                  <EmptyStreakRow key={i} streak={s} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 最近采集记录 */}
        <Card>
          <CardContent className="p-4">
            <h3 className="text-sm font-medium text-muted-foreground mb-3">最近采集记录</h3>
            {data.recent_records.length === 0 ? (
              <p className="text-xs text-muted-foreground py-4 text-center">暂无记录</p>
            ) : (
              <div className="max-h-60 overflow-y-auto">
                {data.recent_records.map((r, i) => (
                  <RecentRecordRow key={i} record={r} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 请求压力 */}
      <RequestPressurePanel pressure={data.request_pressure} />

      {/* 基础设施状态 */}
      <InfraStatus mongo={data.mongo_status} redis={data.redis_status} />
    </div>
  );
}
