import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

interface PanelTask {
  id: string;
  name: string;
  description: string;
}

async function fetchPanelTasks(): Promise<PanelTask[]> {
  const resp = await fetch(`${API_BASE}/panel/tasks`);
  if (!resp.ok) {
    throw new Error(`Failed to load panel tasks: ${resp.status}`);
  }
  return resp.json();
}

async function runPanelTask(taskId: string): Promise<{ message: string; task_id: string }> {
  const resp = await fetch(`${API_BASE}/panel/tasks/${taskId}/run`, {
    method: "POST",
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Failed to run task: ${resp.status} ${text}`);
  }
  return resp.json();
}

export function DataSourceTaskManager() {
  const queryClient = useQueryClient();
  const { data: tasks, isLoading, error } = useQuery({
    queryKey: ["panel-tasks"],
    queryFn: fetchPanelTasks,
  });

  const runMutation = useMutation({
    mutationFn: runPanelTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["panel-tasks"] });
    },
  });

  if (isLoading) {
    return (
      <section>
        <h2 className="text-sm font-semibold text-white">任务管理</h2>
        <p className="mt-2 text-xs text-white/60">加载中…</p>
      </section>
    );
  }
  if (error) {
    return (
      <section>
        <h2 className="text-sm font-semibold text-white">任务管理</h2>
        <p className="mt-2 text-xs text-red-400">{String(error)}</p>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-white">任务管理</h2>
        <p className="mt-1 text-xs text-white/60">
          查看与手动触发行业面板相关的数据抓取/计算任务。
        </p>
      </div>
      <div className="rounded-lg border border-white/10 bg-black/20 overflow-hidden">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-white/10 text-white/60">
              <th className="px-4 py-2.5 font-medium">ID</th>
              <th className="px-4 py-2.5 font-medium">名称</th>
              <th className="px-4 py-2.5 font-medium">说明</th>
              <th className="px-4 py-2.5 font-medium w-24">操作</th>
            </tr>
          </thead>
          <tbody>
            {(tasks ?? []).map((t) => (
              <tr key={t.id} className="border-b border-white/5 hover:bg-white/5">
                <td className="px-4 py-2.5 font-mono text-white/80">{t.id}</td>
                <td className="px-4 py-2.5 text-white">{t.name}</td>
                <td className="px-4 py-2.5 text-white/60">{t.description}</td>
                <td className="px-4 py-2.5">
                  <button
                    type="button"
                    onClick={() => runMutation.mutate(t.id)}
                    disabled={runMutation.isPending}
                    className="px-2 py-1 rounded border border-white/10 text-white/80 hover:bg-white/10 disabled:opacity-50"
                  >
                    {runMutation.isPending && runMutation.variables === t.id
                      ? "执行中…"
                      : "立即执行"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {runMutation.isError && (
        <p className="text-xs text-red-400">{String(runMutation.error)}</p>
      )}
    </section>
  );
}
