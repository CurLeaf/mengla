const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

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
  const resp = await fetch(`${API_BASE}/admin/mengla/status`, {
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
  const resp = await fetch(`${API_BASE}/panel/data/fill`, {
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
