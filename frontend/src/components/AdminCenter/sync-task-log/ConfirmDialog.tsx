import type React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../../ui/dialog";
import { Button } from "../../ui/button";

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
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="leading-relaxed">
            {message}
          </DialogDescription>
        </DialogHeader>
        {extra && <div>{extra}</div>}
        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={loading}>
            取消
          </Button>
          <Button
            size="sm"
            variant="destructive"
            className={confirmClassName}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? "处理中…" : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
