import { useMemo, useState } from "react";
import { ACTION_OPTIONS } from "./shared";
import type { MengLaStatusResponse } from "../../../services/mengla-admin-api";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "../../ui/table";
import { Card } from "../../ui/card";

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
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
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

          <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
            <span className="text-muted-foreground">
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
                className="rounded border-border bg-muted text-[#5E6AD2] focus:ring-[#5E6AD2]"
              />
              <span>只看有缺失的周期</span>
            </label>
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="checkbox"
                checked={onlyMissingRows}
                onChange={(e) => setOnlyMissingRows(e.target.checked)}
                className="rounded border-border bg-muted text-[#5E6AD2] focus:ring-[#5E6AD2]"
              />
              <span>只看有缺失的接口</span>
            </label>
          </div>

          <Card className="overflow-hidden overflow-x-auto max-h-80 overflow-y-auto">
            <Table role="table" aria-label="数据状态矩阵">
              <TableHeader className="sticky top-0 bg-muted border-b border-border">
                <TableRow>
                  <TableHead className="px-3 py-2 whitespace-nowrap">
                    接口 / 周期
                  </TableHead>
                  {visiblePeriodKeys.map((pk) => (
                    <TableHead key={pk} className="px-2 py-2 text-center whitespace-nowrap">
                      {pk}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleActionIds.map((actionId) => {
                  const label = ACTION_OPTIONS.find((a) => a.value === actionId)?.label ?? actionId;
                  return (
                    <TableRow key={actionId}>
                      <TableCell className="px-3 py-1.5 text-foreground/80 whitespace-nowrap">{label}</TableCell>
                      {visiblePeriodKeys.map((pk) => {
                        const has = statusMatrix[actionId]?.[pk];
                        const cellTitle = `${label} @ ${pk}: ${has ? "有数据" : "无数据"}`;
                        return (
                          <TableCell key={pk} className="px-2 py-1.5 text-center align-middle" title={cellTitle}>
                            <span className={`inline-block h-3 w-3 rounded-full ${has ? "bg-emerald-400" : "bg-red-500"}`} />
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  );
                })}
                {visibleActionIds.length === 0 && visiblePeriodKeys.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={1} className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                      当前筛选条件下没有需要展示的接口或周期。
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>
        </div>
      )}
    </>
  );
}
