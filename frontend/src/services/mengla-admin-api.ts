import { authFetch } from "./auth";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export interface MengLaStatusRequest {
  catId?: string | null;
  granularity: string;
  startDate: string;
  endDate: string;
  actions?: string[] | null;
}

export interface MengLaStatusResponse {
  catId?: string | null;
  granularity: string;
  startDate: string;
  endDate: string;
  status: Record<string, Record<string, boolean>>;
}

export async function fetchMenglaStatus(
  body: MengLaStatusRequest
): Promise<MengLaStatusResponse> {
  const resp = await authFetch(`${API_BASE}/admin/mengla/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Failed to fetch MengLa status: ${resp.status} ${text}`);
  }
  return resp.json();
}

export interface PanelDataFillRequest {
  granularity: string;
  startDate: string;
  endDate: string;
  actions?: string[] | null;
}

export interface PanelDataFillResponse {
  message: string;
  granularity?: string;
  startDate?: string;
  endDate?: string;
  periodKeyCount?: number;
}

export async function submitPanelDataFill(
  body: PanelDataFillRequest
): Promise<PanelDataFillResponse> {
  const resp = await authFetch(`${API_BASE}/panel/data/fill`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Failed to submit panel data fill: ${resp.status} ${text}`);
  }
  return resp.json();
}

// ============================================================================
// Panel Tasks API
// ============================================================================

export interface PanelTask {
  id: string;
  name: string;
  description: string;
}

export interface TaskStartedResponse {
  message: string;
  task_id: string;
}

/**
 * 获取任务列表
 * GET /panel/tasks
 */
export async function fetchPanelTasks(): Promise<PanelTask[]> {
  const resp = await authFetch(`${API_BASE}/panel/tasks`);
  if (!resp.ok) {
    throw new Error(`Failed to load panel tasks: ${resp.status}`);
  }
  return resp.json();
}

/**
 * 执行任务
 * POST /panel/tasks/{task_id}/run
 */
export async function runPanelTask(taskId: string): Promise<TaskStartedResponse> {
  const resp = await authFetch(`${API_BASE}/panel/tasks/${taskId}/run`, {
    method: "POST",
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Failed to run task: ${resp.status} ${text}`);
  }
  return resp.json();
}

// ============================================================================
// Scheduler Control API
// ============================================================================

export interface SchedulerStatus {
  running: boolean;
  state: "stopped" | "running" | "paused" | "unknown";
  total_jobs: number;
  active_jobs: { id: string; name: string; next_run: string }[];
  paused_jobs: { id: string; name: string; next_run: string }[];
  background_tasks: number;
}

/** 获取调度器状态 */
export async function fetchSchedulerStatus(): Promise<SchedulerStatus> {
  const resp = await authFetch(`${API_BASE}/admin/scheduler/status`);
  if (!resp.ok) throw new Error(`Failed to get scheduler status: ${resp.status}`);
  return resp.json();
}

/** 暂停调度器 */
export async function pauseScheduler(): Promise<{ message: string }> {
  const resp = await authFetch(`${API_BASE}/admin/scheduler/pause`, { method: "POST" });
  if (!resp.ok) throw new Error(`Failed to pause scheduler: ${resp.status}`);
  return resp.json();
}

/** 恢复调度器 */
export async function resumeScheduler(): Promise<{ message: string }> {
  const resp = await authFetch(`${API_BASE}/admin/scheduler/resume`, { method: "POST" });
  if (!resp.ok) throw new Error(`Failed to resume scheduler: ${resp.status}`);
  return resp.json();
}

/** 取消所有后台任务 */
export async function cancelAllTasks(): Promise<{
  message: string;
  cancelled_asyncio_tasks: number;
  cancelled_sync_logs: number;
  cancelled_crawl_jobs: number;
  cancelled_crawl_subtasks: number;
}> {
  const resp = await authFetch(`${API_BASE}/admin/tasks/cancel-all`, { method: "POST" });
  if (!resp.ok) throw new Error(`Failed to cancel tasks: ${resp.status}`);
  return resp.json();
}

/** 清空所有采集数据和缓存 */
export async function purgeAllData(
  targets: string[] = ["mongodb", "redis", "l1"]
): Promise<{ message: string; results: Record<string, unknown> }> {
  const resp = await authFetch(`${API_BASE}/admin/data/purge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true, targets }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Failed to purge data: ${resp.status} ${text}`);
  }
  return resp.json();
}
