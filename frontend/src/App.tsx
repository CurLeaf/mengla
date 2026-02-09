import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { logout, setUnauthorizedHandler } from "./services/auth";
import { runPanelTask } from "./services/mengla-admin-api";
import { useCategoryState } from "./hooks/useCategoryState";
import { ADMIN_SECTIONS } from "./components/AdminCenter/AdminCenterLayout";
import { Select } from "./components/ui/select";
import { Button } from "./components/ui/button";
import { Separator } from "./components/ui/separator";
import type { Category, CategoryChild } from "./types/category";

/* ---------- 采集模式说明 ---------- */
const COLLECT_MODE_TIPS: Record<string, string> = {
  current: "当前视图 — 仅采集当前页面展示所需的数据",
  fill: "补齐 — 扫描所有缺失数据并自动补齐，已有缓存的会跳过",
  force: "全部 — 强制刷新所有数据，跳过缓存直接从数据源采集",
};

/* ---------- 常量 ---------- */
const MODES = [
  { key: "overview", path: "/", name: "行业总览", badge: "OVERVIEW" },
  { key: "high", path: "/high", name: "蓝海Top行业", badge: "HIGH" },
  { key: "hot", path: "/hot", name: "热销Top行业", badge: "HOT" },
  { key: "chance", path: "/chance", name: "潜力Top行业", badge: "CHANCE" },
] as const;

/** 通过 Outlet context 向子路由传递的数据 */
export interface LayoutContext {
  primaryCatId: string;
  /** >0 表示用户已点击采集，页面 query 才允许发起请求 */
  fetchTrigger: number;
}

/* ---------- Layout 组件 ---------- */
export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  // 是否为仪表盘页面（只有 MODES 中定义的路径才算）
  const isDashboard = useMemo(
    () => MODES.some((m) => m.path === location.pathname),
    [location.pathname],
  );

  /* ---- 管理中心折叠状态 ---- */
  const [adminExpanded, setAdminExpanded] = useState(() =>
    location.pathname.startsWith("/admin"),
  );
  // 导航到管理中心时自动展开
  useEffect(() => {
    if (location.pathname.startsWith("/admin")) {
      setAdminExpanded(true);
    }
  }, [location.pathname]);

  /* ---- SPA 路由：注册 401 回调 ---- */
  useEffect(() => {
    setUnauthorizedHandler(() => navigate("/login"));
  }, [navigate]);

  /* ---- 类目状态 ---- */
  const {
    categories,
    selectedCatId1,
    setSelectedCatId1,
    selectedCatId2,
    setSelectedCatId2,
    level2Options,
    primaryCatId,
    selectedCatLabel,
  } = useCategoryState();

  /* ---- 采集触发控制 ---- */
  const [fetchTrigger, setFetchTrigger] = useState(0);
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [collectMode, setCollectMode] = useState<"current" | "fill" | "force">("current");
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const queryClient = useQueryClient();

  // 切换页面时重置触发器，页面不会自动发起请求
  useEffect(() => {
    setFetchTrigger(0);
  }, [location.pathname]);

  // 当前路径对应的 modeKey（仅在仪表盘页面匹配）
  const currentModeKey = useMemo(() => {
    const matched = MODES.find((m) => m.path === location.pathname);
    return matched?.key ?? null;
  }, [location.pathname]);

  const triggerManualCollect = async () => {
    setTriggerLoading(true);
    try {
      if (collectMode === "force") {
        await runPanelTask("mengla_granular_force");
        queryClient.invalidateQueries({ queryKey: ["mengla"] });
        toast.success("强制采集任务已启动", { description: "将跳过所有缓存直接从数据源采集，请在终端查看进度" });
      } else if (collectMode === "fill") {
        await runPanelTask("mengla_granular");
        queryClient.invalidateQueries({ queryKey: ["mengla"] });
        toast.success("补齐采集任务已启动", { description: "将只采集缺失的数据，已有缓存的会跳过" });
      } else {
        // "当前"模式：激活页面查询（fetchTrigger > 0 时 useQuery 才 enabled）
        setFetchTrigger((prev) => prev + 1);
        queryClient.invalidateQueries({ queryKey: ["mengla"] });
      }
    } catch (e) {
      console.error("手动触发采集失败", e);
      toast.error("采集失败", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setTriggerLoading(false);
    }
  };

  /* ---- 当前页面标题 ---- */
  const currentMode = currentModeKey ? MODES.find((m) => m.key === currentModeKey) : undefined;

  return (
    <div className="h-screen bg-background text-foreground relative overflow-hidden flex flex-col">
      {/* 背景光效 */}
      <div className="pointer-events-none absolute inset-0 opacity-70">
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[900px] h-[900px] bg-primary/25 blur-[140px]" />
        <div className="absolute -left-40 top-40 w-[600px] h-[600px] bg-fuchsia-500/15 blur-[120px]" />
        <div className="absolute -right-40 bottom-0 w-[600px] h-[600px] bg-sky-500/15 blur-[120px]" />
      </div>

      <div className="relative flex flex-1 min-h-0">
        {/* ---------- 侧边栏 ---------- */}
        <aside className="w-64 shrink-0 bg-card/80 border-r border-border backdrop-blur-xl flex flex-col">
          <div className="px-5 py-5">
            <div className="text-[11px] font-mono tracking-[0.25em] text-muted-foreground uppercase">
              MengLa
            </div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-lg font-semibold bg-gradient-to-b from-foreground via-white/90 to-white/60 bg-clip-text text-transparent">
                行业智能面板
              </span>
              {isDashboard && (
                <div className="flex items-center gap-1">
                  <Select
                    value={collectMode}
                    onChange={(e) => setCollectMode(e.target.value as "current" | "fill" | "force")}
                    disabled={triggerLoading}
                    className="h-7 w-auto px-1.5 py-1 text-[10px] border-primary/40 text-primary"
                    title={COLLECT_MODE_TIPS[collectMode]}
                    aria-label="选择采集范围"
                  >
                    <option value="current">当前</option>
                    <option value="fill">补齐</option>
                    <option value="force">全部</option>
                  </Select>
                  <Button
                    variant="outline"
                    size="xs"
                    onClick={() => triggerManualCollect()}
                    disabled={triggerLoading}
                    className="text-[10px] border-primary/40 text-primary bg-primary/20 hover:bg-primary/30"
                    aria-label="开始采集数据"
                    aria-busy={triggerLoading}
                    title={COLLECT_MODE_TIPS[collectMode]}
                  >
                    {triggerLoading && (
                      <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                    )}
                    {triggerLoading ? "采集中..." : "采集"}
                  </Button>
                </div>
              )}
            </div>
          </div>

          <Separator />

          <nav className="flex-1 overflow-y-auto py-3" aria-label="主导航">
            {MODES.map((item) => (
              <NavLink
                key={item.key}
                to={item.path}
                end={item.path === "/"}
                className={({ isActive }: { isActive: boolean }) =>
                  `w-full flex items-center justify-between px-5 py-2.5 text-xs transition-colors ${
                    isActive ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50"
                  }`
                }
              >
                <span>{item.name}</span>
                <span className="text-[10px] font-mono tracking-[0.2em] text-muted-foreground">
                  {item.badge}
                </span>
              </NavLink>
            ))}
            {/* ---------- 管理中心（可折叠） ---------- */}
            <div className="mt-2">
              <button
                type="button"
                onClick={() => setAdminExpanded((prev) => !prev)}
                className={`w-full flex items-center justify-between px-5 py-2.5 text-xs transition-colors cursor-pointer ${
                  location.pathname.startsWith("/admin")
                    ? "text-foreground"
                    : "text-muted-foreground hover:bg-accent/50"
                }`}
              >
                <span>管理中心</span>
                <svg
                  className={`w-3 h-3 text-muted-foreground transition-transform duration-200 ${
                    adminExpanded ? "rotate-90" : ""
                  }`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </button>
              <div
                className="overflow-hidden transition-all duration-200 ease-in-out"
                style={{
                  maxHeight: adminExpanded ? `${ADMIN_SECTIONS.length * 36}px` : "0px",
                  opacity: adminExpanded ? 1 : 0,
                }}
              >
                {ADMIN_SECTIONS.map(({ id, path, label }) => (
                  <NavLink
                    key={id}
                    to={path}
                    className={({ isActive }: { isActive: boolean }) =>
                      `w-full flex items-center px-5 pl-8 py-2 text-xs transition-colors ${
                        isActive
                          ? "bg-accent text-foreground"
                          : "text-muted-foreground hover:bg-accent/50 hover:text-foreground/75"
                      }`
                    }
                  >
                    {label}
                  </NavLink>
                ))}
              </div>
            </div>
            <NavLink
              to="/token"
              className={({ isActive }: { isActive: boolean }) =>
                `w-full flex items-center justify-between px-5 py-2.5 text-xs transition-colors ${
                  isActive ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50"
                }`
              }
            >
              <span>Token 管理</span>
              <span className="text-[10px] font-mono tracking-[0.2em] text-muted-foreground">TOKEN</span>
            </NavLink>
          </nav>

          {/* 登出 */}
          <Separator />
          <div className="px-5 py-3">
            {!showLogoutConfirm ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowLogoutConfirm(true)}
                className="w-full justify-start px-0 text-xs text-muted-foreground hover:text-foreground/70 hover:bg-transparent"
                aria-label="退出登录"
              >
                退出登录
              </Button>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">确认退出？</span>
                <Button
                  variant="destructive"
                  size="xs"
                  onClick={() => { setShowLogoutConfirm(false); logout(); }}
                >
                  确认
                </Button>
                <Button
                  variant="outline"
                  size="xs"
                  onClick={() => setShowLogoutConfirm(false)}
                  className="text-muted-foreground"
                >
                  取消
                </Button>
              </div>
            )}
          </div>
        </aside>

        {/* ---------- 主内容区 ---------- */}
        <main className="flex-1 min-h-0 overflow-y-auto px-8 py-6">
          {isDashboard && (
            <header className="flex flex-col gap-4 mb-6">
              <div className="flex items-center justify-between flex-wrap gap-4">
                <div>
                  <p className="text-xs font-mono tracking-[0.25em] text-muted-foreground uppercase">DASHBOARD</p>
                  <h1 className="mt-2 text-2xl font-semibold bg-gradient-to-b from-foreground via-white/90 to-white/60 bg-clip-text text-transparent">
                    {currentMode?.name ?? "行业总览"}
                  </h1>
                  <p className="mt-1 text-[11px] text-muted-foreground">当前类目：{selectedCatLabel}</p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <Select
                    className="w-auto rounded-lg text-xs"
                    value={selectedCatId1 ?? ""}
                    onChange={(e) => {
                      const v = e.target.value || null;
                      setSelectedCatId1(v);
                      setSelectedCatId2(null);
                    }}
                    aria-label="一级分类"
                  >
                    {categories.map((cat: Category) => (
                      <option key={cat.catId} value={cat.catId}>
                        {cat.catNameCn || cat.catName}
                      </option>
                    ))}
                  </Select>
                  <Select
                    className="w-auto rounded-lg text-xs"
                    value={selectedCatId2 ?? ""}
                    onChange={(e) => setSelectedCatId2(e.target.value || null)}
                    aria-label="二级分类"
                  >
                    <option value="">全部</option>
                    {level2Options.map((child: CategoryChild) => (
                      <option key={child.catId} value={child.catId}>
                        {child.catNameCn || child.catName}
                      </option>
                    ))}
                  </Select>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setFetchTrigger((prev) => prev + 1);
                      queryClient.invalidateQueries({ queryKey: ["mengla"] });
                      toast.success("已刷新", { description: "数据正在重新加载" });
                    }}
                    aria-label="刷新数据"
                  >
                    刷新
                  </Button>
                </div>
              </div>
            </header>
          )}

          {/* 子路由渲染 */}
          <Outlet context={{ primaryCatId, fetchTrigger } satisfies LayoutContext} />
        </main>
      </div>
    </div>
  );
}
