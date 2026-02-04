import { useState } from "react";
import { AdminCenterLayout, type AdminSectionId } from "./AdminCenterLayout";
import { ModuleManager } from "./ModuleManager";
import { LayoutConfigManager } from "./LayoutConfigManager";
import { DataSourceTaskManager } from "./DataSourceTaskManager";
import { PeriodDataManager } from "./PeriodDataManager";
import { MockDataSourceMonitor } from "./MockDataSourceMonitor";

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
      {activeSection === "periodData" && <PeriodDataManager />}
      {activeSection === "dataSource" && <MockDataSourceMonitor />}
    </AdminCenterLayout>
  );
}
