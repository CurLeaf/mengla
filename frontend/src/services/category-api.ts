import type { CategoryList } from "../types/category";
import { API_BASE } from "../constants";
import { authFetch } from "./auth";

export async function fetchCategories(): Promise<CategoryList> {
  const resp = await authFetch(`${API_BASE}/api/categories`);
  if (!resp.ok) {
    throw new Error(`Failed to load categories: ${resp.status}`);
  }
  const json = await resp.json();
  // 兼容包装格式 { ok, data } 和裸数组格式
  return json.data ?? json;
}
