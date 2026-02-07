import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import App from "./App";
import DashboardPage from "./pages/DashboardPage";
import HighPage from "./pages/HighPage";
import HotPage from "./pages/HotPage";
import ChancePage from "./pages/ChancePage";
import AdminPage from "./pages/AdminPage";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 相同品类+时间 5 分钟内不重复请求
      refetchOnWindowFocus: false,
    },
  },
});

const router = createBrowserRouter([
  {
    path: "/",
    element: (
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    ),
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "high", element: <HighPage /> },
      { path: "hot", element: <HotPage /> },
      { path: "chance", element: <ChancePage /> },
      { path: "admin", element: <AdminPage /> },
    ],
  },
]);

const root = document.getElementById("root");
if (!root) throw new Error("Root element not found");

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
