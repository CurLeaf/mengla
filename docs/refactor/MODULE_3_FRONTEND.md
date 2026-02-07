# 模块 3 — 前端重构与体验优化

> **负责角色：** 前端开发  
> **优先级：** 🟡 重要  
> **预估工时：** 5-6 天  
> **分支名：** `refactor/module-3-frontend`  

---

## 本模块管辖文件（与其他模块零交叉）

```
frontend/src/App.tsx                                    ← 修改（alert→toast、SPA 路由修复）
frontend/src/main.tsx                                   ← 修改（ErrorBoundary、代码分割）
frontend/src/pages/HighPage.tsx                         ← 修改（提取公共组件后简化）
frontend/src/pages/HotPage.tsx                          ← 修改（提取公共组件后简化）
frontend/src/pages/ChancePage.tsx                       ← 修改（提取公共组件后简化）
frontend/src/pages/DashboardPage.tsx                    ← 修改（memo 优化）
frontend/src/pages/RankPage.tsx                         ← 新建（通用排名页组件）
frontend/src/pages/LoginPage.tsx                        ← 修改（alert→toast）
frontend/src/pages/TokenPage.tsx                        ← 修改（alert→toast）
frontend/src/components/AdminCenter/PeriodDataManager.tsx       ← 修改（拆分子组件）
frontend/src/components/AdminCenter/PeriodDataManager/*.tsx     ← 新建（拆分后的子组件）
frontend/src/components/AdminCenter/DataSourceTaskManager.tsx   ← 修改（alert→toast）
frontend/src/components/AdminCenter/AdminCenterPage.tsx         ← 修改（memo）
frontend/src/components/AuthGuard.tsx                   ← 修改（SPA 路由导航）
frontend/src/components/IndustryChart.tsx               ← 删除（废弃组件）
frontend/src/components/ErrorBoundary.tsx               ← 新建
frontend/src/components/Toast.tsx                       ← 新建（或安装 sonner）
frontend/src/hooks/useCategoryState.ts                  ← 修改（改用 React Query）
frontend/src/services/sync-task-api.ts                  ← 修改（使用 authFetch）
frontend/src/services/auth.ts                           ← 修改（SPA 路由跳转）
frontend/src/constants.ts                               ← 新建（集中常量管理）
frontend/package.json                                   ← 修改（添加 sonner 依赖）
```

> **不触碰：** `backend/*`、`docker/*`、`mengla-service.ts`、`.env*`

---

## 问题清单

| # | 问题 | 文件 | 严重度 |
|---|------|------|--------|
| 1 | High/Hot/Chance 三个页面 90% 代码重复 | `pages/High\|Hot\|ChancePage.tsx` | 🟡 |
| 2 | PeriodDataManager 600+ 行过大 | `AdminCenter/PeriodDataManager.tsx` | 🟡 |
| 3 | `useCategoryState` 自建缓存，未用 React Query | `hooks/useCategoryState.ts` | 🟡 |
| 4 | `sync-task-api.ts` 未使用 `authFetch` | `services/sync-task-api.ts` | 🟡 |
| 5 | `IndustryChart.tsx` 已废弃但仍存在 | `components/IndustryChart.tsx` | 🟢 |
| 6 | 无路由级代码分割 | `main.tsx` | 🟡 |
| 7 | 常量分散在各文件 | 各处 | 🟢 |
| 8 | 全部使用 `alert()` 作为用户反馈 | 多个文件 | 🟡 |
| 9 | `window.location.href` 导航破坏 SPA | `services/auth.ts`, `AuthGuard.tsx` | 🟡 |
| 10 | 无全局 ErrorBoundary | `main.tsx` | 🟡 |
| 11 | 缺少 ARIA 无障碍标签 | 多个组件 | 🟢 |
| 12 | 缺少 React.memo 优化 | 多个组件 | 🟢 |
| 13 | 确认弹窗使用 `window.confirm()` | `DataSourceTaskManager.tsx` | 🟢 |

---

## 修复方案

### 一、组件去重（问题 #1-5, #7）

#### 1.1 提取通用 RankPage 组件
**新建：** `frontend/src/pages/RankPage.tsx`
```tsx
import React from "react";
import { useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { RankPeriodSelector } from "../components/RankPeriodSelector";
import { queryMengla, buildQueryParams } from "../services/mengla-api";
import type { LayoutContext } from "../App";

interface RankPageProps {
  title: string;
  sortField: string;  // 如 "high_score", "hot_score", "chance_score"
  columns: { key: string; label: string }[];
}

const RankPage: React.FC<RankPageProps> = ({ title, sortField, columns }) => {
  const { primaryCatId, fetchTrigger } = useOutletContext<LayoutContext>();
  const [timest, setTimest] = React.useState<string>("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["mengla", "rank", primaryCatId, timest, sortField],
    queryFn: () => queryMengla(buildQueryParams({ primaryCatId, timest, sortField })),
    enabled: fetchTrigger > 0 && !!primaryCatId && !!timest,
  });

  if (fetchTrigger === 0) {
    return (
      <div className="flex-1 p-6">
        <RankPeriodSelector value={timest} onChange={setTimest} />
        <div className="flex flex-col items-center justify-center h-64 text-gray-400">
          <p>点击左上角「采集」按钮加载数据</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 p-6">
      <h2 className="text-lg font-bold mb-4">{title}</h2>
      <RankPeriodSelector value={timest} onChange={setTimest} />
      {isLoading && <div className="animate-pulse h-64 bg-gray-100 rounded" />}
      {error && <div className="text-red-500 p-4">加载失败: {String(error)}</div>}
      {data && (
        <table className="w-full mt-4" role="table" aria-label={title}>
          <thead>
            <tr>{columns.map(c => <th key={c.key}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {/* 渲染数据行 */}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default React.memo(RankPage);
```

**修改后的页面文件示例 — `HighPage.tsx`:**
```tsx
import RankPage from "./RankPage";

const HIGH_COLUMNS = [
  { key: "name", label: "行业名称" },
  { key: "high_score", label: "蓝海指数" },
  // ...
];

export default function HighPage() {
  return <RankPage title="蓝海Top行业" sortField="high_score" columns={HIGH_COLUMNS} />;
}
```

`HotPage.tsx` 和 `ChancePage.tsx` 同理，每个文件从 ~100 行缩减到 ~15 行。

#### 1.2 PeriodDataManager 拆分
**文件：** `frontend/src/components/AdminCenter/PeriodDataManager.tsx`

拆分为 3 个子组件：
```
PeriodDataManager/
├── index.tsx           # 主容器，组合下面的子组件
├── PeriodSelector.tsx  # 周期选择 UI
├── DataTable.tsx       # 数据表格展示
└── BatchActions.tsx    # 批量操作按钮
```

#### 1.3 useCategoryState 改用 React Query
**文件：** `frontend/src/hooks/useCategoryState.ts`
```tsx
import { useQuery } from "@tanstack/react-query";
import { fetchCategories } from "../services/category-api";

export function useCategoryState() {
  const { data: categories = [], isLoading, error } = useQuery({
    queryKey: ["categories"],
    queryFn: fetchCategories,
    staleTime: 5 * 60 * 1000,      // 5 分钟缓存
    gcTime: 30 * 60 * 1000,        // 30 分钟 GC
  });

  return { categories, isLoading, error };
}
```

#### 1.4 sync-task-api 使用 authFetch
**文件：** `frontend/src/services/sync-task-api.ts`
```typescript
// 修改前
const res = await fetch(`/api/sync-tasks/...`);
// 修改后
import { authFetch } from "./auth";
const res = await authFetch(`/api/sync-tasks/...`);
```

#### 1.5 删除废弃组件
```
删除: frontend/src/components/IndustryChart.tsx
```

#### 1.6 集中常量管理
**新建：** `frontend/src/constants.ts`
```typescript
export const API_BASE = "/api";
export const REFETCH_INTERVALS = {
  scheduler: 5_000,
  syncTasks: 10_000,
} as const;
export const STALE_TIMES = {
  categories: 5 * 60 * 1000,
  menglaData: 2 * 60 * 1000,
} as const;
```

---

### 二、用户体验改进（问题 #8-13）

#### 2.1 alert() 替换为 Toast
**安装依赖：**
```bash
pnpm --filter industry-monitor-frontend add sonner
```

**使用方式（所有涉及文件统一替换）：**
```tsx
// 修改前
alert("操作成功");
// 修改后
import { toast } from "sonner";
toast.success("操作成功");

// 修改前
alert("操作失败: " + error);
// 修改后
toast.error("操作失败", { description: String(error) });
```

**在 `main.tsx` 添加 Toaster 容器：**
```tsx
import { Toaster } from "sonner";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Toaster position="top-right" richColors />
    <App />
  </React.StrictMode>
);
```

> **涉及文件：** `App.tsx`, `LoginPage.tsx`, `TokenPage.tsx`, `DataSourceTaskManager.tsx`, `PeriodDataManager.tsx`

#### 2.2 SPA 路由跳转修复
**文件：** `frontend/src/services/auth.ts`
```typescript
// 修改前
window.location.href = "/login";
// 修改后（提供回调机制）
let _onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: () => void) {
  _onUnauthorized = handler;
}

export async function authFetch(url: string, options?: RequestInit) {
  const res = await fetch(url, { ...options, headers: { ...options?.headers, Authorization: `Bearer ${getToken()}` } });
  if (res.status === 401) {
    removeToken();
    _onUnauthorized?.();
  }
  return res;
}
```

**文件：** `frontend/src/App.tsx`
```tsx
import { useNavigate } from "react-router-dom";
import { setUnauthorizedHandler } from "./services/auth";

function App() {
  const navigate = useNavigate();
  useEffect(() => {
    setUnauthorizedHandler(() => navigate("/login"));
  }, [navigate]);
  // ...
}
```

**文件：** `frontend/src/components/AuthGuard.tsx`
```tsx
import { Navigate } from "react-router-dom";
// 修改前: window.location.href = "/login"; return null;
// 修改后:
return <Navigate to="/login" replace />;
```

#### 2.3 全局 ErrorBoundary
**新建：** `frontend/src/components/ErrorBoundary.tsx`
```tsx
import React from "react";

interface State { hasError: boolean; error: Error | null }

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ReactNode },
  State
> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="flex flex-col items-center justify-center h-screen">
          <h2 className="text-xl font-bold text-red-600 mb-4">页面出现错误</h2>
          <p className="text-gray-500 mb-4">{this.state.error?.message}</p>
          <button
            className="px-4 py-2 bg-blue-500 text-white rounded"
            onClick={() => { this.setState({ hasError: false, error: null }); window.location.reload(); }}
          >
            刷新页面
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

**在 `main.tsx` 中使用：**
```tsx
import { ErrorBoundary } from "./components/ErrorBoundary";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <Toaster position="top-right" richColors />
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
```

#### 2.4 路由级代码分割
**文件：** `frontend/src/main.tsx`
```tsx
import { lazy, Suspense } from "react";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const HighPage = lazy(() => import("./pages/HighPage"));
const HotPage = lazy(() => import("./pages/HotPage"));
const ChancePage = lazy(() => import("./pages/ChancePage"));
const AdminCenterPage = lazy(() => import("./components/AdminCenter/AdminCenterPage"));

// 路由配置中
<Route path="/" element={<Suspense fallback={<PageSkeleton />}><DashboardPage /></Suspense>} />
<Route path="/high" element={<Suspense fallback={<PageSkeleton />}><HighPage /></Suspense>} />
```

#### 2.5 ARIA 无障碍标签
在所有交互元素上添加 `aria-label`：
```tsx
// 按钮
<button aria-label="开始采集数据">采集</button>
// 导航
<nav aria-label="主导航">...</nav>
// 表格
<table role="table" aria-label="蓝海行业排名">...</table>
```

#### 2.6 React.memo 优化
```tsx
// 对纯展示组件添加 memo
export const DistributionCards = React.memo(function DistributionCards(props) { ... });
export const TrendChart = React.memo(function TrendChart(props) { ... });
export const HotIndustryTable = React.memo(function HotIndustryTable(props) { ... });
```

---

## 检查清单

- [ ] High/Hot/ChancePage 每个 < 20 行，公共逻辑在 `RankPage.tsx`
- [ ] PeriodDataManager 拆分为 3+ 个子文件，主文件 < 100 行
- [ ] `useCategoryState` 使用 `useQuery`，无自建缓存逻辑
- [ ] `sync-task-api.ts` 所有请求通过 `authFetch`
- [ ] `IndustryChart.tsx` 已删除
- [ ] 代码中无 `alert()` / `window.confirm()` 调用
- [ ] `window.location.href` 导航已替换为 `navigate()` / `<Navigate />`
- [ ] `ErrorBoundary` 包裹在应用最外层
- [ ] 路由使用 `lazy()` + `Suspense` 实现代码分割
- [ ] 所有交互元素有 `aria-label`
- [ ] 纯展示组件使用 `React.memo`
- [ ] `sonner` Toaster 组件已挂载
