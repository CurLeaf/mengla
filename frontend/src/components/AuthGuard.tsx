import { useState, useEffect } from "react";
import { Navigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { isAuthenticated } from "../services/auth";

/**
 * 路由守卫：未登录则重定向到 /login
 * 初始加载时显示短暂的 loading 状态，避免闪烁
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const [checking, setChecking] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    const result = isAuthenticated();
    setAuthenticated(result);
    setChecking(false);
  }, []);

  if (checking) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
          <span className="text-xs text-muted-foreground">验证身份中…</span>
        </div>
      </div>
    );
  }

  if (!authenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
