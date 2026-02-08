import type { PanelConfig } from "../types/panel-config";
import { API_BASE } from "../constants";
import { authFetch } from "./auth";

export async function fetchPanelConfig(): Promise<PanelConfig> {
  const resp = await authFetch(`${API_BASE}/api/panel/config`);
  if (!resp.ok) {
    throw new Error(`Failed to load panel config: ${resp.status}`);
  }
  return resp.json();
}

export async function updatePanelConfig(payload: {
  modules?: PanelConfig["modules"];
  layout?: PanelConfig["layout"];
}): Promise<PanelConfig> {
  const resp = await authFetch(`${API_BASE}/api/panel/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Failed to update panel config: ${resp.status} ${text}`);
  }
  return resp.json();
}
