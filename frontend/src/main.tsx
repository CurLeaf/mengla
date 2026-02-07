import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";
import App from "./App";
import { AuthGuard } from "./components/AuthGuard";
import { ErrorBoundary } from "./components/ErrorBoundary";
import LoginPage from "./pages/LoginPage";
import { STALE_TIMES } from "./constants";
import "./index.css";

/* ---- 路由级代码分割 ---- */
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const HighPage = lazy(() => import("./pages/HighPage"));
const HotPage = lazy(() => import("./pages/HotPage"));
const ChancePage = lazy(() => import("./pages/ChancePage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));
const TokenPage = lazy(() => import("./pages/TokenPage"));

/* ---- 路由加载骨架屏 ---- */
function PageSkeleton() {
  return (
    <div className="flex items-center justify-center py-32">
      <div className="animate-pulse flex flex-col items-center gap-3">
        <div className="h-8 w-8 rounded-full border-2 border-white/20 border-t-[#5E6AD2] animate-spin" />
        <span className="text-xs text-white/40">加载中…</span>
      </div>
    </div>
  );
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: STALE_TIMES.categories,
      refetchOnWindowFocus: false,
    },
  },
});

const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/",
    element: (
      <AuthGuard>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </AuthGuard>
    ),
    children: [
      { index: true, element: <Suspense fallback={<PageSkeleton />}><DashboardPage /></Suspense> },
      { path: "high", element: <Suspense fallback={<PageSkeleton />}><HighPage /></Suspense> },
      { path: "hot", element: <Suspense fallback={<PageSkeleton />}><HotPage /></Suspense> },
      { path: "chance", element: <Suspense fallback={<PageSkeleton />}><ChancePage /></Suspense> },
      { path: "admin", element: <Suspense fallback={<PageSkeleton />}><AdminPage /></Suspense> },
      { path: "token", element: <Suspense fallback={<PageSkeleton />}><TokenPage /></Suspense> },
    ],
  },
]);

const root = document.getElementById("root");
if (!root) throw new Error("Root element not found");

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <ErrorBoundary>
      <Toaster position="top-right" richColors />
      <RouterProvider router={router} />
    </ErrorBoundary>
  </React.StrictMode>
);
