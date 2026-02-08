import type { CategoryList } from "../types/category";
import { API_BASE } from "../constants";
import { authFetch } from "./auth";

export async function fetchCategories(): Promise<CategoryList> {
  const resp = await authFetch(`${API_BASE}/api/categories`);
  if (!resp.ok) {
    throw new Error(`Failed to load categories: ${resp.status}`);
  }
  return resp.json();
}
