/**
 * 认证服务 & 统一 fetch 封装
 * - token 存储在 localStorage
 * - authFetch 自动注入 Authorization header
 * - 401 时自动清除 token 并跳转登录页
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
const TOKEN_KEY = "mengla_token";

/* ---------- Token 存储 ---------- */

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

/* ---------- SPA 导航回调 ---------- */

let _onUnauthorized: (() => void) | null = null;

/**
 * 由 App 组件在挂载时注册，提供 SPA 内的路由跳转能力。
 * 避免 authFetch / logout 直接使用 window.location.href 破坏 SPA。
 */
export function setUnauthorizedHandler(handler: () => void) {
  _onUnauthorized = handler;
}

function navigateToLogin() {
  if (_onUnauthorized) {
    _onUnauthorized();
  } else {
    // fallback：回调未注册时（如应用刚加载）仍可跳转
    window.location.href = "/login";
  }
}

/* ---------- 登录 / 登出 ---------- */

export interface LoginResult {
  token: string;
  username: string;
}

export async function login(username: string, password: string): Promise<LoginResult> {
  const resp = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `登录失败: ${resp.status}`);
  }
  const data: LoginResult = await resp.json();
  setToken(data.token);
  return data;
}

export function logout(): void {
  clearToken();
  navigateToLogin();
}

/* ---------- Token 生成 ---------- */

export interface GenerateTokenResult {
  token: string;
  label: string;
  expires_hours: number | null;
}

export async function generateApiToken(
  label: string = "api",
  expiresHours: number | null = 24 * 365
): Promise<GenerateTokenResult> {
  const resp = await authFetch(`${API_BASE}/api/auth/generate-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label, expires_hours: expiresHours }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `生成 Token 失败: ${resp.status}`);
  }
  return resp.json();
}

/* ---------- 统一 fetch 封装 ---------- */

/**
 * 带认证的 fetch —— 自动注入 Bearer token
 * 401 时自动清除 token 并跳转登录页
 */
export async function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init?.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const resp = await fetch(input, { ...init, headers });

  if (resp.status === 401) {
    clearToken();
    // 避免在登录页死循环
    if (!window.location.pathname.startsWith("/login")) {
      navigateToLogin();
    }
  }

  return resp;
}
