import type { ReactNode } from "react";

const ADMIN_SECTIONS = [
  { id: "modules", path: "/admin/modules", label: "模块管理" },
  { id: "layout", path: "/admin/layout", label: "布局配置" },
  { id: "tasks", path: "/admin/tasks", label: "任务管理" },
  { id: "syncLogs", path: "/admin/syncLogs", label: "同步日志" },
  { id: "periodData", path: "/admin/periodData", label: "周期数据" },
] as const;

export type AdminSectionId = (typeof ADMIN_SECTIONS)[number]["id"];

interface AdminCenterLayoutProps {
  children: ReactNode;
}

export function AdminCenterLayout({ children }: AdminCenterLayoutProps) {
  return (
    <div className="flex-1 overflow-auto">{children}</div>
  );
}

export { ADMIN_SECTIONS };
