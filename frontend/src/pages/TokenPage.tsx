import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { generateApiToken } from "../services/auth";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select } from "../components/ui/select";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "../components/ui/card";
import { Badge } from "../components/ui/badge";

interface GeneratedToken {
  token: string;
  label: string;
  expires_hours: number | null;
  createdAt: string;
}

export default function TokenPage() {
  const [label, setLabel] = useState("api");
  const [expiresHours, setExpiresHours] = useState<number | null>(8760); // 365 天
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tokens, setTokens] = useState<GeneratedToken[]>([]);
  const [copied, setCopied] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const handleGenerate = async (e: FormEvent) => {
    e.preventDefault();
    if (!label.trim() || label.trim().length < 2) {
      setError("标签至少需要 2 个字符");
      return;
    }
    if (label.trim().length > 50) {
      setError("标签不能超过 50 个字符");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const result = await generateApiToken(label.trim(), expiresHours);
      setTokens((prev) => [
        {
          token: result.token,
          label: result.label,
          expires_hours: result.expires_hours,
          createdAt: new Date().toLocaleString(),
        },
        ...prev,
      ]);
      toast.success("Token 已生成", { description: "请立即复制保存，离开页面后将无法再次查看" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = (tokenValue: string) => {
    if (confirmDelete === tokenValue) {
      setTokens((prev) => prev.filter((t) => t.token !== tokenValue));
      setConfirmDelete(null);
      toast.success("Token 已删除");
    } else {
      setConfirmDelete(tokenValue);
    }
  };

  const copyToClipboard = async (token: string) => {
    try {
      await navigator.clipboard.writeText(token);
      setCopied(token);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      // fallback
      const textarea = document.createElement("textarea");
      textarea.value = token;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(token);
      setTimeout(() => setCopied(null), 2000);
    }
  };

  const formatExpiry = (hours: number | null) => {
    if (hours === null) return "永久";
    if (hours >= 8760) return `${Math.round(hours / 8760)} 年`;
    return `${Math.round(hours / 24)} 天`;
  };

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-mono tracking-[0.2em] text-muted-foreground uppercase">TOKEN</p>
        <h2 className="mt-1 text-lg font-semibold text-foreground">API Token 生成</h2>
        <p className="mt-1 text-xs text-muted-foreground">生成长期 API Token，用于外部系统调用接口</p>
      </div>

      {/* 生成表单 */}
      <Card>
        <CardContent className="p-6">
          <form onSubmit={handleGenerate} className="flex flex-wrap items-end gap-4">
            <div className="flex-1 min-w-[140px]">
              <label className="block text-[11px] text-muted-foreground mb-1.5 font-medium">
                标签（用途说明）
              </label>
              <Input
                type="text"
                value={label}
                onChange={(e) => { setLabel(e.target.value); if (error) setError(""); }}
                required
                maxLength={50}
                className={
                  label.trim().length > 0 && label.trim().length < 2
                    ? "border-amber-500/40 focus-visible:border-amber-500"
                    : ""
                }
                placeholder="如：外部系统对接"
              />
              {label.trim().length > 0 && label.trim().length < 2 && (
                <p className="mt-1 text-[10px] text-amber-400">标签至少需要 2 个字符</p>
              )}
            </div>
            <div className="w-40">
              <label className="block text-[11px] text-muted-foreground mb-1.5 font-medium">
                有效期
              </label>
              <Select
                value={expiresHours === null ? "permanent" : expiresHours}
                onChange={(e) => {
                  const val = e.target.value;
                  setExpiresHours(val === "permanent" ? null : Number(val));
                }}
              >
                <option value={24}>1 天</option>
                <option value={168}>7 天</option>
                <option value={720}>30 天</option>
                <option value={2160}>90 天</option>
                <option value={8760}>1 年</option>
                <option value={87600}>10 年</option>
                <option value="permanent">永久</option>
              </Select>
            </div>
            <Button
              type="submit"
              disabled={loading}
              aria-busy={loading}
              className="gap-2"
            >
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              {loading ? "生成中…" : "生成 Token"}
            </Button>
          </form>
          {error && (
            <div className="mt-3 text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 已生成的 Token 列表 */}
      {tokens.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-start gap-2">
              <Badge variant="warning" className="shrink-0 mt-0.5">注意</Badge>
              <div>
                <CardTitle>已生成的 Token</CardTitle>
                <CardDescription className="text-amber-400/80 mt-0.5">
                  Token 仅在此页面显示一次，刷新或离开页面后将无法再次查看，请立即复制保存。
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {tokens.map((item) => (
                <div
                  key={item.token}
                  className="bg-muted border border-border rounded-xl p-4"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-primary">{item.label}</span>
                      <Badge
                        variant={item.expires_hours === null ? "success" : "secondary"}
                        className="text-[10px] px-1.5 py-0.5"
                      >
                        {item.expires_hours === null ? "永久有效" : `有效期 ${formatExpiry(item.expires_hours)}`}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-muted-foreground">{item.createdAt}</span>
                      {confirmDelete === item.token ? (
                        <div className="flex items-center gap-1">
                          <Button
                            variant="destructive"
                            size="xs"
                            onClick={() => handleDelete(item.token)}
                          >
                            确认
                          </Button>
                          <Button
                            variant="outline"
                            size="xs"
                            onClick={() => setConfirmDelete(null)}
                          >
                            取消
                          </Button>
                        </div>
                      ) : (
                        <Button
                          variant="ghost"
                          size="xs"
                          className="text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                          onClick={() => handleDelete(item.token)}
                        >
                          删除
                        </Button>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 text-[11px] text-foreground/70 bg-background/40 rounded px-3 py-2 font-mono break-all select-all">
                      {item.token}
                    </code>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => copyToClipboard(item.token)}
                    >
                      {copied === item.token ? "已复制" : "复制"}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
