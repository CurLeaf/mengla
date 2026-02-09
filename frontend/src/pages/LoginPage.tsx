import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { login } from "../services/auth";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "../components/ui/card";

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
    <div className="min-h-screen bg-background text-foreground relative overflow-hidden flex items-center justify-center">
      {/* 背景光效 */}
      <div className="pointer-events-none absolute inset-0 opacity-70">
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[900px] h-[900px] bg-primary/25 blur-[140px]" />
        <div className="absolute -left-40 top-40 w-[600px] h-[600px] bg-fuchsia-500/15 blur-[120px]" />
        <div className="absolute -right-40 bottom-0 w-[600px] h-[600px] bg-sky-500/15 blur-[120px]" />
      </div>

      <div className="relative w-full max-w-sm mx-4">
        <Card className="bg-black/50 backdrop-blur-xl border-white/10 shadow-[0_0_0_1px_rgba(255,255,255,0.06),0_24px_60px_rgba(0,0,0,0.8)]">
          <CardHeader className="text-center pb-2">
            <div className="text-[11px] font-mono tracking-[0.25em] text-muted-foreground uppercase">
              MengLa
            </div>
            <CardTitle className="mt-2 text-xl bg-gradient-to-b from-white via-white/90 to-white/60 bg-clip-text text-transparent">
              行业智能面板
            </CardTitle>
            <CardDescription>请登录以继续</CardDescription>
          </CardHeader>

          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-[11px] text-muted-foreground mb-1.5 font-medium">
                  用户名
                </label>
                <Input
                  type="text"
                  value={username}
                  onChange={(e) => { setUsername(e.target.value); if (error) setError(""); }}
                  required
                  autoFocus
                  autoComplete="username"
                  placeholder="输入用户名"
                />
              </div>

              <div>
                <label className="block text-[11px] text-muted-foreground mb-1.5 font-medium">
                  密码
                </label>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => { setPassword(e.target.value); if (error) setError(""); }}
                  required
                  autoComplete="current-password"
                  placeholder="输入密码"
                />
              </div>

              {error && (
                <div className="text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
                  {error}
                </div>
              )}

              <Button
                type="submit"
                disabled={loading}
                aria-busy={loading}
                className="w-full"
                size="lg"
              >
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {loading ? "登录中…" : "登 录"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
