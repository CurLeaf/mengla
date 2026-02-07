import type { CategoryList } from "../types/category";
import { authFetch } from "./auth";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export async function fetchCategories(): Promise<CategoryList> {
  const resp = await authFetch(`${API_BASE}/api/categories`);
  if (!resp.ok) {
    throw new Error(`Failed to load categories: ${resp.status}`);
  }
  return resp.json();
}
