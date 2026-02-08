import { useEffect, useState, useCallback } from "react";
import {
  fetchCollectHealth,
  type CollectHealthResponse,
  type ActionStat,
  type EmptyStreak,
  type RecentRecord,
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
    </div>
  );
}
