import { useEffect, useMemo, useState } from "react";
import { fetchCategories } from "../services/category-api";
import type { Category, CategoryChild, CategoryList } from "../types/category";

export function useCategoryState() {
  const [categories, setCategories] = useState<CategoryList>([]);
  const [selectedCatId1, setSelectedCatId1] = useState<string | null>(null);
  const [selectedCatId2, setSelectedCatId2] = useState<string | null>(null);

  const level2Options = useMemo(() => {
    if (!selectedCatId1 || !categories.length) return [];
    const first = categories.find(
      (c: Category) => String(c.catId) === selectedCatId1
    );
    return Array.isArray(first?.children) ? first!.children : [];
  }, [categories, selectedCatId1]);

  const primaryCatId = selectedCatId1 ?? "";

  const selectedCatLabel = useMemo(() => {
    if (!selectedCatId1 || !categories.length) return "全部类目";
    const first = categories.find(
      (c: Category) => String(c.catId) === selectedCatId1
    );
    const name1 = first ? first.catNameCn || first.catName || "" : "";
    if (!selectedCatId2) return name1 || "全部类目";
    const second = level2Options.find(
      (c: CategoryChild) => String(c.catId) === selectedCatId2
    );
    const name2 = second ? second.catNameCn || second.catName || "" : "";
    return name2 ? `${name1} > ${name2}` : name1;
  }, [categories, selectedCatId1, selectedCatId2, level2Options]);

  useEffect(() => {
    let cancelled = false;
    const loadCategories = async () => {
      try {
        const data = await fetchCategories();
        if (cancelled) return;
        setCategories(data || []);
        if (data?.length) {
          setSelectedCatId1((prev: string | null) =>
            prev === null ? String(data[0].catId) : prev
          );
        }
      } catch (e) {
        if (!cancelled) console.error("加载类目失败", e);
      }
    };
    loadCategories();
    return () => {
      cancelled = true;
    };
  }, []);

  return {
    categories,
    selectedCatId1,
    setSelectedCatId1,
    selectedCatId2,
    setSelectedCatId2,
    level2Options,
    primaryCatId,
    selectedCatLabel,
  };
}
