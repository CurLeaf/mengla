import { useMemo, useState } from "react";
import { ACTION_OPTIONS } from "./shared";
import type { MengLaStatusResponse } from "../../../services/mengla-admin-api";

interface DataTableProps {
  statusResult: MengLaStatusResponse | null;
  statusError: string | null;
}

export function DataTable({ statusResult, statusError }: DataTableProps) {
  const [onlyMissingColumns, setOnlyMissingColumns] = useState(false);
  const [onlyMissingRows, setOnlyMissingRows] = useState(false);

  const statusMatrix = statusResult?.status ?? {};

  const actionIds = useMemo(
    () => (statusResult ? Object.keys(statusMatrix) : []),
    [statusResult, statusMatrix]
  );

  const periodKeys = useMemo(() => {
    if (!statusResult) return [];
    const keys = new Set<string>();
    Object.values(statusMatrix).forEach((m) => {
      Object.keys(m ?? {}).forEach((k) => keys.add(k));
    });
    return [...keys].sort();
  }, [statusResult, statusMatrix]);

  const { visibleActionIds, visiblePeriodKeys, perActionMissing } = useMemo(() => {
    const perAction: Record<string, number> = {};
    const perPeriod: Record<string, number> = {};

    actionIds.forEach((actionId) => {
      const map = statusMatrix[actionId] ?? {};
      let missingCount = 0;
      periodKeys.forEach((pk) => {
        const has = map[pk];
        if (!has) {
          missingCount += 1;
          perPeriod[pk] = (perPeriod[pk] ?? 0) + 1;
        }
      });
      perAction[actionId] = missingCount;
    });

    let cols = periodKeys;
    if (onlyMissingColumns) {
      cols = cols.filter((pk) => (perPeriod[pk] ?? 0) > 0);
    }

    let rows = actionIds;
    if (onlyMissingRows) {
      rows = rows.filter((id) => (perAction[id] ?? 0) > 0);
    }

    return {
      visibleActionIds: rows,
      visiblePeriodKeys: cols,
      perActionMissing: perAction,
    };
  }, [actionIds, periodKeys, statusMatrix, onlyMissingColumns, onlyMissingRows]);

  return (
    <>
      {statusError && (
        <p className="text-xs text-red-400">{statusError}</p>
      )}

      {statusResult && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3 text-xs text-white/70">
            <span>
              共 {periodKeys.length} 个 period_key，{actionIds.length} 个接口
            </span>
            {actionIds.map((actionId) => (
              <span key={actionId} className="ml-1">
                {ACTION_OPTIONS.find((a) => a.value === actionId)?.label ?? actionId}
                ：缺失 {perActionMissing[actionId] ?? 0}
              </span>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs text-white/70">
            <span className="text-white/60">
              方块表示某接口在对应周期下是否已有 MengLa 数据：
            </span>
            <div className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded-full bg-emerald-400" />
              <span>有数据</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded-full bg-red-500" />
              <span>无数据</span>
            </div>
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="checkbox"
                checked={onlyMissingColumns}
                onChange={(e) => setOnlyMissingColumns(e.target.checked)}
                className="rounded border-white/30 bg-black/40 text-[#5E6AD2] focus:ring-[#5E6AD2]"
              />
              <span>只看有缺失的周期</span>
            </label>
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="checkbox"
                checked={onlyMissingRows}
                onChange={(e) => setOnlyMissingRows(e.target.checked)}
                className="rounded border-white/30 bg-black/40 text-[#5E6AD2] focus:ring-[#5E6AD2]"
              />
              <span>只看有缺失的接口</span>
            </label>
          </div>

          <div className="rounded-lg border border-white/10 bg-black/20 overflow-hidden overflow-x-auto max-h-80 overflow-y-auto">
            <table className="min-w-full text-left text-xs" role="table" aria-label="数据状态矩阵">
              <thead className="sticky top-0 bg-black/40 border-b border-white/10">
                <tr>
                  <th className="px-3 py-2 font-medium text-white/70 whitespace-nowrap">
                    接口 / 周期
                  </th>
                  {visiblePeriodKeys.map((pk) => (
                    <th key={pk} className="px-2 py-2 font-medium text-white/70 text-center whitespace-nowrap">
                      {pk}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleActionIds.map((actionId) => {
                  const label = ACTION_OPTIONS.find((a) => a.value === actionId)?.label ?? actionId;
                  return (
                    <tr key={actionId} className="border-b border-white/5 hover:bg-white/5">
                      <td className="px-3 py-1.5 text-white/80 whitespace-nowrap">{label}</td>
                      {visiblePeriodKeys.map((pk) => {
                        const has = statusMatrix[actionId]?.[pk];
                        const cellTitle = `${label} @ ${pk}: ${has ? "有数据" : "无数据"}`;
                        return (
                          <td key={pk} className="px-2 py-1.5 text-center align-middle" title={cellTitle}>
                            <span className={`inline-block h-3 w-3 rounded-full ${has ? "bg-emerald-400" : "bg-red-500"}`} />
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
                {visibleActionIds.length === 0 && visiblePeriodKeys.length === 0 && (
                  <tr>
                    <td colSpan={1} className="px-3 py-2 text-xs text-white/60 whitespace-nowrap">
                      当前筛选条件下没有需要展示的接口或周期。
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
