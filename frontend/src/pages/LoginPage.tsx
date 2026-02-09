import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../services/auth";

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    // 前端验证
    if (username.trim().length < 2) {
      setError("用户名至少需要 2 个字符");
      return;
    }
    if (password.length < 4) {
      setError("密码至少需要 4 个字符");
      return;
    }
    setError("");
    setLoading(true);
    try {
      await login(username.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof Error) {
        const msg = err.message;
        if (msg.includes("429") || msg.includes("频繁")) {
          setError("登录尝试过于频繁，请 1 分钟后再试");
        } else if (msg.includes("401") || msg.includes("密码") || msg.includes("用户名")) {
          setError("用户名或密码错误，请检查后重试");
        } else if (msg.includes("fetch") || msg.includes("network") || msg.includes("Network")) {
          setError("网络连接失败，请检查网络后重试");
        } else {
          setError(msg);
        }
      } else {
        setError("登录失败，请稍后重试");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#050506] text-white relative overflow-hidden flex items-center justify-center">
      {/* 背景光效 */}
      <div className="pointer-events-none absolute inset-0 opacity-70">
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[900px] h-[900px] bg-[#5E6AD2]/25 blur-[140px]" />
        <div className="absolute -left-40 top-40 w-[600px] h-[600px] bg-fuchsia-500/15 blur-[120px]" />
        <div className="absolute -right-40 bottom-0 w-[600px] h-[600px] bg-sky-500/15 blur-[120px]" />
      </div>

      <div className="relative w-full max-w-sm mx-4">
        <div className="bg-black/50 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-[0_0_0_1px_rgba(255,255,255,0.06),0_24px_60px_rgba(0,0,0,0.8)]">
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="text-[11px] font-mono tracking-[0.25em] text-white/40 uppercase">
              MengLa
            </div>
            <h1 className="mt-2 text-xl font-semibold bg-gradient-to-b from-white via-white/90 to-white/60 bg-clip-text text-transparent">
              行业智能面板
            </h1>
            <p className="mt-1 text-xs text-white/40">请登录以继续</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-[11px] text-white/50 mb-1.5 font-medium">
                用户名
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => { setUsername(e.target.value); if (error) setError(""); }}
                required
                autoFocus
                autoComplete="username"
                className="w-full bg-[#0F0F12] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/25 focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 focus:border-[#5E6AD2] transition-colors"
                placeholder="输入用户名"
              />
            </div>

            <div>
              <label className="block text-[11px] text-white/50 mb-1.5 font-medium">
                密码
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => { setPassword(e.target.value); if (error) setError(""); }}
                required
                autoComplete="current-password"
                className="w-full bg-[#0F0F12] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/25 focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 focus:border-[#5E6AD2] transition-colors"
                placeholder="输入密码"
              />
            </div>

            {error && (
              <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              aria-busy={loading}
              className="w-full py-2.5 bg-[#5E6AD2] hover:bg-[#6E7AE2] text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 focus:ring-offset-2 focus:ring-offset-[#050506] flex items-center justify-center gap-2"
            >
              {loading && (
                <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              )}
              {loading ? "登录中…" : "登 录"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
