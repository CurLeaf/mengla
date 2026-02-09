import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { toast } from "sonner";
import { fetchPanelConfig, updatePanelConfig } from "../../services/panel-config-api";
import type { PanelLayoutConfig } from "../../types/panel-config";

const PERIOD_OPTIONS = [
  { value: "update", label: "更新日期" },
  { value: "month", label: "月榜" },
  { value: "quarter", label: "季榜" },
  { value: "year", label: "年榜" },
];

export function LayoutConfigManager() {
  const queryClient = useQueryClient();
  const { data: config, isLoading, error } = useQuery({
    queryKey: ["panel-config"],
    queryFn: fetchPanelConfig,
  });

  const [defaultPeriod, setDefaultPeriod] = useState("month");
  const [showRankPeriodSelector, setShowRankPeriodSelector] = useState(true);

  useEffect(() => {
    if (config?.layout) {
      setDefaultPeriod(
        (config.layout.defaultPeriod as string) ?? "month"
      );
      setShowRankPeriodSelector(
        config.layout.showRankPeriodSelector !== false
      );
    }
  }, [config?.layout]);

  const saveMutation = useMutation({
    mutationFn: (layout: PanelLayoutConfig) =>
      updatePanelConfig({ layout }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["panel-config"] });
      toast.success("布局配置已保存");
    },
    onError: (e) => {
      toast.error("保存失败", { description: e instanceof Error ? e.message : String(e) });
    },
  });

  const handleSave = () => {
    saveMutation.mutate({
      defaultPeriod,
      showRankPeriodSelector,
    });
  };

  if (isLoading) {
    return (
      <section>
        <h2 className="text-sm font-semibold text-white">布局配置</h2>
        <p className="mt-2 text-xs text-white/60">加载中…</p>
      </section>
    );
  }
  if (error) {
    return (
      <section>
        <h2 className="text-sm font-semibold text-white">布局配置</h2>
        <p className="mt-2 text-xs text-red-400">{String(error)}</p>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-white">布局配置</h2>
        <p className="mt-1 text-xs text-white/60">
          配置各模块在面板上的默认时间周期与展示选项。
        </p>
      </div>
      <div className="rounded-lg border border-white/10 bg-black/20 p-4 space-y-4 max-w-md">
        <div>
          <label className="block text-xs font-medium text-white/80 mb-1.5">
            默认周期
          </label>
          <select
            value={defaultPeriod}
            onChange={(e) => setDefaultPeriod(e.target.value)}
            className="w-full bg-[#0F0F12] border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50"
          >
            {PERIOD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="showRankPeriodSelector"
            checked={showRankPeriodSelector}
            onChange={(e) => setShowRankPeriodSelector(e.target.checked)}
            className="rounded border-white/30 bg-black/40 text-[#5E6AD2] focus:ring-[#5E6AD2]"
          />
          <label
            htmlFor="showRankPeriodSelector"
            className="text-xs text-white/80 cursor-pointer"
          >
            显示榜周期选择器（非总览模式）
          </label>
        </div>
        <button
          type="button"
          onClick={handleSave}
          disabled={saveMutation.isPending}
          aria-busy={saveMutation.isPending}
          className="px-4 py-2 rounded-lg border border-white/10 text-xs text-white hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 disabled:opacity-50 flex items-center gap-2"
        >
          {saveMutation.isPending && (
            <span className="inline-block w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" />
          )}
          {saveMutation.isPending ? "保存中…" : "保存布局配置"}
        </button>
      </div>
    </section>
  );
}
