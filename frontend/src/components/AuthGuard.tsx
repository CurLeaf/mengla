import { Navigate } from "react-router-dom";
import { isAuthenticated } from "../services/auth";

/**
 * 路由守卫：未登录则重定向到 /login
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
