import type { ReactNode } from "react";

const ADMIN_SECTIONS = [
  { id: "modules", label: "模块管理" },
  { id: "layout", label: "布局配置" },
  { id: "tasks", label: "任务管理" },
  { id: "periodData", label: "周期数据" },
] as const;

export type AdminSectionId = (typeof ADMIN_SECTIONS)[number]["id"];

interface AdminCenterLayoutProps {
  activeSection: AdminSectionId;
  onSectionChange: (id: AdminSectionId) => void;
  children: ReactNode;
}

export function AdminCenterLayout({
  activeSection,
  onSectionChange,
  children,
}: AdminCenterLayoutProps) {
  return (
    <div className="flex min-h-0 flex-1">
      <nav className="w-52 shrink-0 border-r border-white/10 bg-black/20 py-4">
        <div className="px-4 text-[11px] font-mono tracking-wider text-white/40 uppercase">
          Admin
        </div>
        <ul className="mt-3 space-y-0.5">
          {ADMIN_SECTIONS.map(({ id, label }) => (
            <li key={id}>
              <button
                type="button"
                className={`w-full px-4 py-2 text-left text-xs transition-colors ${
                  activeSection === id
                    ? "bg-white/10 text-white"
                    : "text-white/65 hover:bg-white/5 hover:text-white/85"
                }`}
                onClick={() => onSectionChange(id)}
              >
                {label}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <div className="flex-1 overflow-auto px-6 py-4">{children}</div>
    </div>
  );
}

export { ADMIN_SECTIONS };
