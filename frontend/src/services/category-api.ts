import type { CategoryList } from "../types/category";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function fetchCategories(): Promise<CategoryList> {
  const resp = await fetch(`${API_BASE}/api/categories`);
  if (!resp.ok) {
    throw new Error(`Failed to load categories: ${resp.status}`);
  }
  return resp.json();
}
