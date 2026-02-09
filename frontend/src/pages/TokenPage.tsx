import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { generateApiToken } from "../services/auth";

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
        <p className="text-xs font-mono tracking-[0.2em] text-white/50 uppercase">TOKEN</p>
        <h2 className="mt-1 text-lg font-semibold text-white">API Token 生成</h2>
        <p className="mt-1 text-xs text-white/40">生成长期 API Token，用于外部系统调用接口</p>
      </div>

      {/* 生成表单 */}
      <div className="bg-[#0a0a0c]/80 border border-white/10 rounded-2xl p-6 shadow-[0_0_0_1px_rgba(255,255,255,0.06),0_14px_30px_rgba(0,0,0,0.6)]">
        <form onSubmit={handleGenerate} className="flex flex-wrap items-end gap-4">
          <div className="flex-1 min-w-[140px]">
            <label className="block text-[11px] text-white/50 mb-1.5 font-medium">
              标签（用途说明）
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => { setLabel(e.target.value); if (error) setError(""); }}
              required
              maxLength={50}
              className={`w-full bg-[#0F0F12] border rounded-lg px-3 py-2 text-sm text-white placeholder-white/25 focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 transition-colors ${
                label.trim().length > 0 && label.trim().length < 2
                  ? "border-amber-500/40 focus:border-amber-500"
                  : "border-white/10 focus:border-[#5E6AD2]"
              }`}
              placeholder="如：外部系统对接"
            />
            {label.trim().length > 0 && label.trim().length < 2 && (
              <p className="mt-1 text-[10px] text-amber-400">标签至少需要 2 个字符</p>
            )}
          </div>
          <div className="w-40">
            <label className="block text-[11px] text-white/50 mb-1.5 font-medium">
              有效期
            </label>
            <select
              value={expiresHours === null ? "permanent" : expiresHours}
              onChange={(e) => {
                const val = e.target.value;
                setExpiresHours(val === "permanent" ? null : Number(val));
              }}
              className="w-full bg-[#0F0F12] border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 focus:border-[#5E6AD2]"
            >
              <option value={24}>1 天</option>
              <option value={168}>7 天</option>
              <option value={720}>30 天</option>
              <option value={2160}>90 天</option>
              <option value={8760}>1 年</option>
              <option value={87600}>10 年</option>
              <option value="permanent">永久</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={loading}
            aria-busy={loading}
            className="px-5 py-2 bg-[#5E6AD2] hover:bg-[#6E7AE2] text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading && (
              <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            )}
            {loading ? "生成中…" : "生成 Token"}
          </button>
        </form>
        {error && (
          <div className="mt-3 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
            {error}
          </div>
        )}
      </div>

      {/* 已生成的 Token 列表 */}
      {tokens.length > 0 && (
        <div className="bg-[#0a0a0c]/80 border border-white/10 rounded-2xl p-6 shadow-[0_0_0_1px_rgba(255,255,255,0.06),0_14px_30px_rgba(0,0,0,0.6)]">
          <div className="flex items-start gap-2 mb-4">
            <span className="shrink-0 mt-0.5 px-1.5 py-0.5 text-[10px] font-medium rounded bg-amber-500/20 text-amber-400">注意</span>
            <div>
              <h3 className="text-sm font-semibold text-white">
                已生成的 Token
              </h3>
              <p className="text-[11px] text-amber-400/80 mt-0.5">
                Token 仅在此页面显示一次，刷新或离开页面后将无法再次查看，请立即复制保存。
              </p>
            </div>
          </div>
          <div className="space-y-3">
            {tokens.map((item) => (
              <div
                key={item.token}
                className="bg-[#0F0F12] border border-white/10 rounded-xl p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-[#5E6AD2]">{item.label}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                      item.expires_hours === null
                        ? "bg-emerald-500/15 text-emerald-400"
                        : "text-white/30"
                    }`}>
                      {item.expires_hours === null ? "永久有效" : `有效期 ${formatExpiry(item.expires_hours)}`}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-white/30">{item.createdAt}</span>
                    {confirmDelete === item.token ? (
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => handleDelete(item.token)}
                          className="px-2 py-1 text-[11px] rounded bg-red-600 hover:bg-red-700 text-white transition-colors"
                        >
                          确认
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmDelete(null)}
                          className="px-2 py-1 text-[11px] rounded border border-white/20 text-white/50 hover:bg-white/5 transition-colors"
                        >
                          取消
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleDelete(item.token)}
                        className="px-2 py-1 text-[11px] rounded bg-white/5 hover:bg-red-500/10 border border-white/10 text-white/40 hover:text-red-400 hover:border-red-500/20 transition-colors"
                      >
                        删除
                      </button>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-[11px] text-white/70 bg-black/40 rounded px-3 py-2 font-mono break-all select-all">
                    {item.token}
                  </code>
                  <button
                    type="button"
                    onClick={() => copyToClipboard(item.token)}
                    className="shrink-0 px-3 py-2 text-[11px] bg-white/5 hover:bg-white/10 border border-white/10 rounded text-white/60 hover:text-white transition-colors"
                  >
                    {copied === item.token ? "已复制" : "复制"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
