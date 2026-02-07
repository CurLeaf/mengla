import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchCategories } from "../services/category-api";
import { STALE_TIMES, GC_TIMES } from "../constants";
import type { Category, CategoryChild } from "../types/category";

export function useCategoryState() {
  const [selectedCatId1, setSelectedCatId1] = useState<string | null>(null);
  const [selectedCatId2, setSelectedCatId2] = useState<string | null>(null);

  const { data: categories = [] } = useQuery({
    queryKey: ["categories"],
    queryFn: fetchCategories,
    staleTime: STALE_TIMES.categories,
    gcTime: GC_TIMES.categories,
  });

  // 当 categories 首次加载完成时，自动选中第一个类目
  useEffect(() => {
    if (categories.length > 0) {
      setSelectedCatId1((prev) =>
        prev === null ? String(categories[0].catId) : prev
      );
    }
  }, [categories]);

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
