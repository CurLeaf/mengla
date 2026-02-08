import React from "react";
import { useParams } from "react-router-dom";
import { AdminCenterLayout, type AdminSectionId } from "./AdminCenterLayout";
import { ModuleManager } from "./ModuleManager";
import { LayoutConfigManager } from "./LayoutConfigManager";
import { SyncTaskLogViewer } from "./SyncTaskLogViewer";
import { PeriodDataManager } from "./PeriodDataManager";
import { CollectHealthMonitor } from "./CollectHealthMonitor";

const VALID_SECTIONS: AdminSectionId[] = ["modules", "layout", "syncLogs", "periodData", "health"];

export const AdminCenterPage = React.memo(function AdminCenterPage() {
  const { section } = useParams<{ section?: string }>();
  const activeSection: AdminSectionId = VALID_SECTIONS.includes(section as AdminSectionId)
    ? (section as AdminSectionId)
    : "modules";

  return (
    <AdminCenterLayout>
      {activeSection === "modules" && <ModuleManager />}
      {activeSection === "layout" && <LayoutConfigManager />}
      {activeSection === "syncLogs" && <SyncTaskLogViewer />}
      {activeSection === "periodData" && <PeriodDataManager />}
      {activeSection === "health" && <CollectHealthMonitor />}
    </AdminCenterLayout>
  );
});
