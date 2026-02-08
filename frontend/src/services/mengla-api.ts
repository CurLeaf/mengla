import type { MenglaQueryParams, MenglaQueryResponse } from "../types/mengla";
import { API_BASE } from "../constants";
import { authFetch } from "./auth";

/** 萌拉接口依赖采集服务 webhook，首包可能较慢，超时设为 3 分钟 */
const MENGLA_FETCH_TIMEOUT_MS = 3 * 60 * 1000;

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
