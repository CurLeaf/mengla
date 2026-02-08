import type React from "react";

/**
 * 确认弹窗
 */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  confirmClassName,
  extra,
  loading,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  confirmClassName?: string;
  extra?: React.ReactNode;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-sm rounded-lg border border-white/10 bg-gray-900 p-5 shadow-xl">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        <p className="mt-2 text-xs text-white/60 leading-relaxed">{message}</p>
        {extra && <div className="mt-3">{extra}</div>}
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onCancel}
            disabled={loading}
            className="rounded px-3 py-1.5 text-xs text-white/60 hover:text-white hover:bg-white/10 transition-colors disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`rounded px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
              confirmClassName || "bg-red-600 text-white hover:bg-red-500"
            }`}
          >
            {loading ? "处理中…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
