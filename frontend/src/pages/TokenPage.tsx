import { useState, type FormEvent } from "react";
import { generateApiToken } from "../services/auth";

interface GeneratedToken {
  token: string;
  label: string;
  expires_hours: number;
  createdAt: string;
}

export default function TokenPage() {
  const [label, setLabel] = useState("api");
  const [expiresHours, setExpiresHours] = useState(8760); // 365 天
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tokens, setTokens] = useState<GeneratedToken[]>([]);
  const [copied, setCopied] = useState<string | null>(null);

  const handleGenerate = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await generateApiToken(label, expiresHours);
      setTokens((prev) => [
        {
          token: result.token,
          label: result.label,
          expires_hours: result.expires_hours,
          createdAt: new Date().toLocaleString(),
        },
        ...prev,
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
    } finally {
      setLoading(false);
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
              onChange={(e) => setLabel(e.target.value)}
              required
              className="w-full bg-[#0F0F12] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/25 focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 focus:border-[#5E6AD2]"
              placeholder="如：外部系统对接"
            />
          </div>
          <div className="w-40">
            <label className="block text-[11px] text-white/50 mb-1.5 font-medium">
              有效期
            </label>
            <select
              value={expiresHours}
              onChange={(e) => setExpiresHours(Number(e.target.value))}
              className="w-full bg-[#0F0F12] border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-[#5E6AD2]/50 focus:border-[#5E6AD2]"
            >
              <option value={24}>1 天</option>
              <option value={168}>7 天</option>
              <option value={720}>30 天</option>
              <option value={2160}>90 天</option>
              <option value={8760}>1 年</option>
              <option value={87600}>10 年</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={loading}
            className="px-5 py-2 bg-[#5E6AD2] hover:bg-[#6E7AE2] text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
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
          <h3 className="text-sm font-semibold text-white mb-4">
            已生成的 Token（仅显示一次，请妥善保存）
          </h3>
          <div className="space-y-3">
            {tokens.map((item, idx) => (
              <div
                key={idx}
                className="bg-[#0F0F12] border border-white/10 rounded-xl p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-[#5E6AD2]">{item.label}</span>
                    <span className="text-[10px] text-white/30">
                      有效期 {item.expires_hours >= 8760 ? `${Math.round(item.expires_hours / 8760)} 年` : `${Math.round(item.expires_hours / 24)} 天`}
                    </span>
                  </div>
                  <span className="text-[10px] text-white/30">{item.createdAt}</span>
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
