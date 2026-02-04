import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

// 模拟数据源服务地址
const MOCK_SERVICE_URL = import.meta.env.VITE_MOCK_SERVICE_URL || "http://localhost:3001";

interface TaskRecord {
  execution_id: string;
  action: string;
  params: Record<string, unknown>;
  status: "pending" | "processing" | "completed" | "failed";
  progress: number;
  message: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
}

interface ProcessingStatus {
  current_task: TaskRecord | null;
  queue_size: number;
  stats: {
    pending: number;
    processing: number;
    completed: number;
    failed: number;
  };
  worker_running: boolean;
}

interface QueueStatus {
  queue_size: number;
  queue: TaskRecord[];
  recent_tasks: TaskRecord[];
  worker_running: boolean;
}

async function fetchProcessingStatus(): Promise<ProcessingStatus> {
  const resp = await fetch(`${MOCK_SERVICE_URL}/api/status/processing`);
  if (!resp.ok) {
    throw new Error(`Failed to fetch processing status: ${resp.status}`);
  }
  return resp.json();
}

async function fetchQueueStatus(): Promise<QueueStatus> {
  const resp = await fetch(`${MOCK_SERVICE_URL}/api/status/queue`);
  if (!resp.ok) {
    throw new Error(`Failed to fetch queue status: ${resp.status}`);
  }
  return resp.json();
}

function StatusBadge({ status }: { status: TaskRecord["status"] }) {
  const colors = {
    pending: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    processing: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    completed: "bg-green-500/20 text-green-400 border-green-500/30",
    failed: "bg-red-500/20 text-red-400 border-red-500/30",
  };
  const labels = {
    pending: "等待中",
    processing: "处理中",
    completed: "已完成",
    failed: "失败",
  };
  return (
    <span className={`px-2 py-0.5 rounded border text-xs ${colors[status]}`}>
      {labels[status]}
    </span>
  );
}

function ProgressBar({ progress, status }: { progress: number; status: TaskRecord["status"] }) {
  const bgColor = status === "failed" ? "bg-red-500" : status === "completed" ? "bg-green-500" : "bg-blue-500";
  return (
    <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
      <div
        className={`h-full ${bgColor} transition-all duration-300`}
        style={{ width: `${progress}%` }}
      />
    </div>
  );
}

function CurrentTaskCard({ task }: { task: TaskRecord }) {
  return (
    <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-white">当前处理任务</h3>
        <StatusBadge status={task.status} />
      </div>
      
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-white/60">Action:</span>
          <span className="text-white font-mono">{task.action}</span>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-white/60">Execution ID:</span>
          <span className="text-white/80 font-mono text-[10px]">{task.execution_id}</span>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-white/60">进度:</span>
          <span className="text-white">{task.progress}%</span>
        </div>
      </div>
      
      <ProgressBar progress={task.progress} status={task.status} />
      
      <div className="text-xs text-blue-300 animate-pulse">
        {task.message}
      </div>
    </div>
  );
}

function TaskHistoryTable({ tasks }: { tasks: TaskRecord[] }) {
  if (tasks.length === 0) {
    return (
      <p className="text-xs text-white/40 text-center py-4">暂无任务记录</p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-white/10 text-white/60">
            <th className="px-3 py-2 font-medium">状态</th>
            <th className="px-3 py-2 font-medium">Action</th>
            <th className="px-3 py-2 font-medium">进度</th>
            <th className="px-3 py-2 font-medium">消息</th>
            <th className="px-3 py-2 font-medium">创建时间</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <tr key={task.execution_id} className="border-b border-white/5 hover:bg-white/5">
              <td className="px-3 py-2">
                <StatusBadge status={task.status} />
              </td>
              <td className="px-3 py-2 text-white font-mono">{task.action}</td>
              <td className="px-3 py-2">
                <div className="w-20">
                  <ProgressBar progress={task.progress} status={task.status} />
                </div>
              </td>
              <td className="px-3 py-2 text-white/60 max-w-[200px] truncate">
                {task.message}
              </td>
              <td className="px-3 py-2 text-white/40 font-mono text-[10px]">
                {new Date(task.created_at).toLocaleTimeString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function MockDataSourceMonitor() {
  const [autoRefresh, setAutoRefresh] = useState(true);
  
  // 获取处理状态（高频刷新）
  const { data: processingStatus, error: processingError } = useQuery({
    queryKey: ["mock-processing-status"],
    queryFn: fetchProcessingStatus,
    refetchInterval: autoRefresh ? 1000 : false, // 1秒刷新
    retry: false,
  });

  // 获取队列状态（低频刷新）
  const { data: queueStatus, error: queueError } = useQuery({
    queryKey: ["mock-queue-status"],
    queryFn: fetchQueueStatus,
    refetchInterval: autoRefresh ? 3000 : false, // 3秒刷新
    retry: false,
  });

  const isServiceAvailable = !processingError && !queueError;

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">数据源监控</h2>
          <p className="mt-1 text-xs text-white/60">
            实时查看模拟数据源的处理状态
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-white/60 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="w-3 h-3 rounded"
            />
            自动刷新
          </label>
          <div className={`w-2 h-2 rounded-full ${isServiceAvailable ? "bg-green-500" : "bg-red-500"}`} />
          <span className="text-xs text-white/40">
            {isServiceAvailable ? "服务正常" : "服务离线"}
          </span>
        </div>
      </div>

      {!isServiceAvailable && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4">
          <p className="text-xs text-red-400">
            无法连接到模拟数据源服务 ({MOCK_SERVICE_URL})
          </p>
          <p className="text-xs text-white/40 mt-1">
            请确保已启动模拟服务: <code className="bg-black/30 px-1 rounded">python -m backend.mock_data_source</code>
          </p>
        </div>
      )}

      {isServiceAvailable && processingStatus && (
        <>
          {/* 统计概览 */}
          <div className="grid grid-cols-4 gap-3">
            <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-center">
              <div className="text-2xl font-bold text-yellow-400">
                {processingStatus.stats.pending}
              </div>
              <div className="text-xs text-white/60 mt-1">等待中</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-center">
              <div className="text-2xl font-bold text-blue-400">
                {processingStatus.stats.processing}
              </div>
              <div className="text-xs text-white/60 mt-1">处理中</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-center">
              <div className="text-2xl font-bold text-green-400">
                {processingStatus.stats.completed}
              </div>
              <div className="text-xs text-white/60 mt-1">已完成</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-center">
              <div className="text-2xl font-bold text-red-400">
                {processingStatus.stats.failed}
              </div>
              <div className="text-xs text-white/60 mt-1">失败</div>
            </div>
          </div>

          {/* 当前任务 */}
          {processingStatus.current_task ? (
            <CurrentTaskCard task={processingStatus.current_task} />
          ) : (
            <div className="rounded-lg border border-white/10 bg-black/20 p-4 text-center">
              <p className="text-xs text-white/40">当前无任务处理中</p>
              <p className="text-xs text-white/20 mt-1">
                队列中有 {processingStatus.queue_size} 个任务等待
              </p>
            </div>
          )}

          {/* 任务历史 */}
          {queueStatus && (
            <div className="rounded-lg border border-white/10 bg-black/20 overflow-hidden">
              <div className="px-4 py-2.5 border-b border-white/10">
                <h3 className="text-xs font-medium text-white/80">最近任务</h3>
              </div>
              <TaskHistoryTable tasks={queueStatus.recent_tasks} />
            </div>
          )}
        </>
      )}
    </section>
  );
}
