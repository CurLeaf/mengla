/**
 * 模拟 API 服务
 * 用于前端独立开发时使用模拟数据
 */

import {
  mockCategories,
  mockPanelConfig,
  mockPanelTasks,
  generateMockStatus,
  getMockDataByAction,
} from "./mock-data";
import type { MenglaQueryParams } from "../types/mengla";

// 模拟网络延迟
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// 随机延迟 200-800ms
const randomDelay = () => delay(200 + Math.random() * 600);

/**
 * 模拟获取类目列表
 */
export async function mockFetchCategories() {
  await randomDelay();
  return mockCategories;
}

/**
 * 模拟获取面板配置
 */
export async function mockFetchPanelConfig() {
  await randomDelay();
  return mockPanelConfig;
}

/**
 * 模拟 MengLa 查询
 */
export async function mockQueryMengla(params: MenglaQueryParams) {
  await delay(500 + Math.random() * 1500); // 模拟较长的采集延迟
  
  const data = getMockDataByAction(params.action);
  if (!data) {
    throw new Error(`Unknown action: ${params.action}`);
  }
  
  return data;
}

/**
 * 模拟获取任务列表
 */
export async function mockFetchPanelTasks() {
  await randomDelay();
  return mockPanelTasks;
}

/**
 * 模拟运行任务
 */
export async function mockRunPanelTask(taskId: string) {
  await delay(1000 + Math.random() * 2000);
  return { message: "task started", task_id: taskId };
}

/**
 * 模拟获取 MengLa 数据状态
 */
export async function mockFetchMenglaStatus(body: {
  catId?: string | null;
  granularity: string;
  startDate: string;
  endDate: string;
  actions?: string[] | null;
}) {
  await randomDelay();
  return generateMockStatus(body.startDate, body.endDate, body.granularity);
}

/**
 * 模拟触发数据补齐
 */
export async function mockSubmitPanelDataFill(body: {
  granularity: string;
  startDate: string;
  endDate: string;
  actions?: string[] | null;
}) {
  await delay(500);
  return {
    message: "fill started",
    granularity: body.granularity,
    startDate: body.startDate,
    endDate: body.endDate,
    periodKeyCount: 30,
  };
}

/**
 * 模拟更新面板配置
 */
export async function mockUpdatePanelConfig(body: {
  modules?: Array<{ id: string; name?: string; enabled?: boolean; order?: number }>;
  layout?: Record<string, unknown>;
}) {
  await randomDelay();
  
  // 合并更新
  const updated = { ...mockPanelConfig };
  
  if (body.modules) {
    updated.modules = body.modules.map((m, i) => ({
      id: m.id,
      name: m.name ?? m.id,
      enabled: m.enabled ?? true,
      order: m.order ?? i,
    }));
  }
  
  if (body.layout) {
    updated.layout = { ...updated.layout, ...body.layout };
  }
  
  return updated;
}

// ============================================================================
// 是否使用模拟数据的开关
// ============================================================================
export const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

/**
 * 条件性使用模拟 API
 * 如果 VITE_USE_MOCK_DATA=true，使用模拟数据；否则调用真实 API
 */
export function withMock<T>(
  mockFn: () => Promise<T>,
  realFn: () => Promise<T>
): Promise<T> {
  if (USE_MOCK_DATA) {
    console.log("[Mock] Using mock data");
    return mockFn();
  }
  return realFn();
}
