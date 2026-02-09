import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { fetchPanelConfig, updatePanelConfig } from "../../services/panel-config-api";
import type { PanelModuleConfig } from "../../types/panel-config";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "../ui/table";
import { Checkbox } from "../ui/checkbox";
import { Button } from "../ui/button";

function moveOrder<T extends { order: number }>(list: T[], index: number, delta: number): T[] {
  const next = index + delta;
  if (next < 0 || next >= list.length) return list;
  const copy = list.slice();
  const item = copy[index];
  copy[index] = copy[next];
  copy[next] = item;
  return copy.map((m, i) => ({ ...m, order: i }));
}

export function ModuleManager() {
  const queryClient = useQueryClient();
  const { data: config, isLoading, error } = useQuery({
    queryKey: ["panel-config"],
    queryFn: fetchPanelConfig,
  });

  const saveMutation = useMutation({
    mutationFn: (modules: PanelModuleConfig[]) =>
      updatePanelConfig({ modules }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["panel-config"] });
      toast.success("模块配置已保存");
    },
    onError: (e) => {
      toast.error("保存失败", { description: e instanceof Error ? e.message : String(e) });
    },
  });

  if (isLoading) {
    return (
      <section>
        <h2 className="text-sm font-semibold text-foreground">模块管理</h2>
        <p className="mt-2 text-xs text-muted-foreground">加载中…</p>
      </section>
    );
  }
  if (error) {
    return (
      <section>
        <h2 className="text-sm font-semibold text-foreground">模块管理</h2>
        <p className="mt-2 text-xs text-red-400">{String(error)}</p>
      </section>
    );
  }
  const modules = config?.modules ?? [];

  const setModules = (next: PanelModuleConfig[]) => {
    saveMutation.mutate(next);
  };

  const toggleEnabled = (id: string) => {
    const next = modules.map((m) =>
      m.id === id ? { ...m, enabled: !m.enabled } : m
    );
    setModules(next);
  };

  const moveUp = (index: number) => {
    if (index <= 0) return;
    setModules(moveOrder(modules, index, -1));
  };

  const moveDown = (index: number) => {
    if (index >= modules.length - 1) return;
    setModules(moveOrder(modules, index, 1));
  };

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-foreground">模块管理</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          启用/禁用行业智能面板下的业务模块，并调整显示顺序。
        </p>
      </div>
      <div className="rounded-lg border border-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="border-border">
              <TableHead>顺序</TableHead>
              <TableHead>名称</TableHead>
              <TableHead>ID</TableHead>
              <TableHead>启用</TableHead>
              <TableHead className="w-28">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {modules
              .slice()
              .sort((a, b) => a.order - b.order)
              .map((m, i) => (
                <TableRow key={m.id}>
                  <TableCell className="text-muted-foreground">{m.order + 1}</TableCell>
                  <TableCell className="text-foreground">{m.name}</TableCell>
                  <TableCell className="font-mono text-muted-foreground">{m.id}</TableCell>
                  <TableCell>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <Checkbox
                        checked={m.enabled}
                        onCheckedChange={() => toggleEnabled(m.id)}
                      />
                      <span className="text-foreground/80">
                        {m.enabled ? "是" : "否"}
                      </span>
                    </label>
                  </TableCell>
                  <TableCell className="flex gap-1">
                    <Button
                      variant="outline"
                      size="xs"
                      onClick={() => moveUp(i)}
                      disabled={i === 0}
                    >
                      上移
                    </Button>
                    <Button
                      variant="outline"
                      size="xs"
                      onClick={() => moveDown(i)}
                      disabled={i === modules.length - 1}
                    >
                      下移
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>
      {saveMutation.isPending && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          保存中…
        </div>
      )}
    </section>
  );
}
