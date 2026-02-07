import { useState } from "react";
import { AdminCenterLayout, type AdminSectionId } from "./AdminCenterLayout";
import { ModuleManager } from "./ModuleManager";
import { LayoutConfigManager } from "./LayoutConfigManager";
import { DataSourceTaskManager } from "./DataSourceTaskManager";
import { SyncTaskLogViewer } from "./SyncTaskLogViewer";
import { PeriodDataManager } from "./PeriodDataManager";

export function AdminCenterPage() {
  const [activeSection, setActiveSection] = useState<AdminSectionId>("modules");

  return (
    <AdminCenterLayout
      activeSection={activeSection}
      onSectionChange={setActiveSection}
    >
      {activeSection === "modules" && <ModuleManager />}
      {activeSection === "layout" && <LayoutConfigManager />}
      {activeSection === "tasks" && <DataSourceTaskManager />}
      {activeSection === "syncLogs" && <SyncTaskLogViewer />}
      {activeSection === "periodData" && <PeriodDataManager />}
    </AdminCenterLayout>
  );
}
