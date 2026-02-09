import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { fetchPanelConfig, updatePanelConfig } from "../../services/panel-config-api";
import type { PanelLayoutConfig } from "../../types/panel-config";
import { Card, CardContent } from "../ui/card";
import { Select } from "../ui/select";
import { Checkbox } from "../ui/checkbox";
import { Button } from "../ui/button";

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
        <h2 className="text-sm font-semibold text-foreground">布局配置</h2>
        <p className="mt-2 text-xs text-muted-foreground">加载中…</p>
      </section>
    );
  }
  if (error) {
    return (
      <section>
        <h2 className="text-sm font-semibold text-foreground">布局配置</h2>
        <p className="mt-2 text-xs text-red-400">{String(error)}</p>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-foreground">布局配置</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          配置各模块在面板上的默认时间周期与展示选项。
        </p>
      </div>
      <Card className="max-w-md">
        <CardContent className="p-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-foreground/80 mb-1.5">
              默认周期
            </label>
            <Select
              value={defaultPeriod}
              onChange={(e) => setDefaultPeriod(e.target.value)}
              className="text-xs"
            >
              {PERIOD_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <Checkbox
              id="showRankPeriodSelector"
              checked={showRankPeriodSelector}
              onCheckedChange={(checked) =>
                setShowRankPeriodSelector(checked === true)
              }
            />
            <label
              htmlFor="showRankPeriodSelector"
              className="text-xs text-foreground/80 cursor-pointer"
            >
              显示榜周期选择器（非总览模式）
            </label>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleSave}
            disabled={saveMutation.isPending}
            aria-busy={saveMutation.isPending}
          >
            {saveMutation.isPending && (
              <Loader2 className="h-3 w-3 animate-spin" />
            )}
            {saveMutation.isPending ? "保存中…" : "保存布局配置"}
          </Button>
        </CardContent>
      </Card>
    </section>
  );
}
