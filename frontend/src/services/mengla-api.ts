import type { MenglaQueryParams, MenglaQueryResponse } from "../types/mengla";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function queryMengla(
  params: MenglaQueryParams
): Promise<MenglaQueryResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000);

  try {
    const resp = await fetch(`${API_BASE}/api/mengla/query`, {
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
