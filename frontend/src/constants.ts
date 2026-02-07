/**
 * 集中常量管理
 */

export const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export const STALE_TIMES = {
  categories: 5 * 60 * 1000, // 5 分钟
  menglaData: 2 * 60 * 1000, // 2 分钟
} as const;

export const REFETCH_INTERVALS = {
  scheduler: 5_000, // 5 秒
  syncTasks: 10_000, // 10 秒
} as const;

export const GC_TIMES = {
  default: 60 * 60 * 1000, // 1 小时
  categories: 30 * 60 * 1000, // 30 分钟
} as const;
