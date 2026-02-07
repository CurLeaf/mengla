/**
 * Sync Task API - 同步任务日志相关 API
 */

import { authFetch } from "./auth";
import { API_BASE } from "../constants";

// ==============================================================================
// Types
// ==============================================================================

export interface SyncTaskProgress {
  total: number;
  completed: number;
  failed: number;
}

export interface SyncTaskLog {
  id: string;
  task_id: string;
  task_name: string;
  status: "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  progress: SyncTaskProgress;
  started_at: string;
  finished_at: string | null;
  trigger: "manual" | "scheduled";
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface CancelSyncTaskResponse {
  success: boolean;
  message: string;
}

export interface DeleteSyncTaskResponse {
  success: boolean;
  message: string;
  deleted_data_count?: number;
}

export interface TodaySyncTasksResponse {
  tasks: SyncTaskLog[];
}

// ==============================================================================
// API Functions
// ==============================================================================

/**
 * 获取当天的同步任务列表
 */
export async function fetchTodaySyncTasks(): Promise<SyncTaskLog[]> {
  const resp = await authFetch(`${API_BASE}/api/sync-tasks/today`);
  if (!resp.ok) {
    throw new Error(`Failed to fetch today sync tasks: ${resp.status}`);
  }
  const data: TodaySyncTasksResponse = await resp.json();
  return data.tasks;
}

/**
 * 获取单个同步任务的详情
 */
export async function fetchSyncTaskDetail(logId: string): Promise<SyncTaskLog> {
  const resp = await authFetch(`${API_BASE}/api/sync-tasks/${logId}`);
  if (!resp.ok) {
    throw new Error(`Failed to fetch sync task detail: ${resp.status}`);
  }
  return resp.json();
}

/**
 * 取消一个运行中的同步任务
 */
export async function cancelSyncTask(logId: string): Promise<CancelSyncTaskResponse> {
  const resp = await authFetch(`${API_BASE}/api/sync-tasks/${logId}/cancel`, {
    method: "POST",
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || `取消失败: ${resp.status}`);
  }
  return resp.json();
}

/**
 * 删除一个同步任务日志（可选：同时删除采集的数据）
 */
export async function deleteSyncTask(
  logId: string,
  deleteData: boolean = false,
): Promise<DeleteSyncTaskResponse> {
  const resp = await authFetch(`${API_BASE}/api/sync-tasks/${logId}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ delete_data: deleteData }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || `删除失败: ${resp.status}`);
  }
  return resp.json();
}
