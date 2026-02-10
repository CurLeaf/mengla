import type { MenglaQueryParams, MenglaQueryResponse } from "../types/mengla";
import { API_BASE } from "../constants";
import { authFetch } from "./auth";

/** 前端已有缓存自动加载，超时缩短为 30 秒 */
const MENGLA_FETCH_TIMEOUT_MS = 30 * 1000;

export async function queryMengla(
  params: MenglaQueryParams
): Promise<MenglaQueryResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), MENGLA_FETCH_TIMEOUT_MS);

  try {
    const resp = await authFetch(`${API_BASE}/api/mengla/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(params),
      signal: controller.signal,
    });

    if (!resp.ok) {
      const text = await resp.text();
      console.error("[MengLa] 请求失败", resp.status, text);
      throw new Error(`MengLa API error: ${resp.status}`);
    }

    const data = await resp.json();
    return data;
  } finally {
    clearTimeout(timeoutId);
  }
}
