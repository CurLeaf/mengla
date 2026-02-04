import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchPanelConfig, updatePanelConfig } from "../../services/panel-config-api";
import type { PanelModuleConfig } from "../../types/panel-config";

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
    },
  });

  if (isLoading) {
    return (
      <section>
        <h2 className="text-sm font-semibold text-white">模块管理</h2>
        <p className="mt-2 text-xs text-white/60">加载中…</p>
      </section>
    );
  }
  if (error) {
    return (
      <section>
        <h2 className="text-sm font-semibold text-white">模块管理</h2>
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
        <h2 className="text-sm font-semibold text-white">模块管理</h2>
        <p className="mt-1 text-xs text-white/60">
          启用/禁用行业智能面板下的业务模块，并调整显示顺序。
        </p>
      </div>
      <div className="rounded-lg border border-white/10 bg-black/20 overflow-hidden">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-white/10 text-white/60">
              <th className="px-4 py-2.5 font-medium">顺序</th>
              <th className="px-4 py-2.5 font-medium">名称</th>
              <th className="px-4 py-2.5 font-medium">ID</th>
              <th className="px-4 py-2.5 font-medium">启用</th>
              <th className="px-4 py-2.5 font-medium w-28">操作</th>
            </tr>
          </thead>
          <tbody>
            {modules
              .slice()
              .sort((a, b) => a.order - b.order)
              .map((m, i) => (
                <tr key={m.id} className="border-b border-white/5 hover:bg-white/5">
                  <td className="px-4 py-2.5 text-white/80">{m.order + 1}</td>
                  <td className="px-4 py-2.5 text-white">{m.name}</td>
                  <td className="px-4 py-2.5 font-mono text-white/60">{m.id}</td>
                  <td className="px-4 py-2.5">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={m.enabled}
                        onChange={() => toggleEnabled(m.id)}
                        className="rounded border-white/30 bg-black/40 text-[#5E6AD2] focus:ring-[#5E6AD2]"
                      />
                      <span className="text-white/80">
                        {m.enabled ? "是" : "否"}
                      </span>
                    </label>
                  </td>
                  <td className="px-4 py-2.5 flex gap-1">
                    <button
                      type="button"
                      onClick={() => moveUp(i)}
                      disabled={i === 0}
                      className="px-2 py-1 rounded border border-white/10 text-white/80 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      上移
                    </button>
                    <button
                      type="button"
                      onClick={() => moveDown(i)}
                      disabled={i === modules.length - 1}
                      className="px-2 py-1 rounded border border-white/10 text-white/80 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      下移
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {saveMutation.isPending && (
        <p className="text-xs text-white/50">保存中…</p>
      )}
      {saveMutation.isError && (
        <p className="text-xs text-red-400">{String(saveMutation.error)}</p>
      )}
    </section>
  );
}
