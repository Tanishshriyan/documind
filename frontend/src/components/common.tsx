import { AlertCircle, Check, CheckCircle2, FileText, Info, LoaderCircle, X } from "lucide-react";
import type { ReactNode } from "react";

import type { DocumentStatus } from "../types";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`brand ${compact ? "brand-compact" : ""}`}>
      <span className="brand-symbol" aria-hidden="true">D</span>
      {!compact && <span className="brand-name">DocuMind <strong>AI</strong></span>}
    </span>
  );
}

export function IconButton({
  label,
  children,
  className = "",
  onClick,
  type = "button",
  disabled = false,
}: {
  label: string;
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  type?: "button" | "submit";
  disabled?: boolean;
}) {
  return (
    <button type={type} className={`icon-button ${className}`} aria-label={label} title={label} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

export function StatusBadge({ status }: { status: DocumentStatus | string }) {
  const busy = status === "PENDING" || status === "PROCESSING";
  const normalized = status.toLowerCase();
  const label = status === "READY" ? "Ready" : status === "PENDING" ? "Queued" : status === "PROCESSING" ? "Indexing" : "Needs attention";
  return (
    <span className={`status-badge status-${normalized}`}>
      {status === "READY" ? <CheckCircle2 size={13} /> : busy ? <LoaderCircle className="spin" size={13} /> : <AlertCircle size={13} />}
      {label}
    </span>
  );
}

export function FileTypeIcon({ name, size = 17 }: { name: string; size?: number }) {
  const extension = name.split(".").pop()?.toLowerCase();
  return <span className={`file-type file-type-${extension ?? "file"}`} aria-hidden="true"><FileText size={size} /></span>;
}

export function LoadingRows({ count = 4 }: { count?: number }) {
  return (
    <div className="loading-rows" aria-label="Loading">
      {Array.from({ length: count }, (_, index) => (
        <div className="loading-row" key={index}>
          <span className="skeleton skeleton-icon" />
          <span className="skeleton skeleton-title" />
          <span className="skeleton skeleton-meta" />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({ icon, title, description, action }: { icon: ReactNode; title: string; description: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <span className="empty-state-icon">{icon}</span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  );
}

export function InlineNotice({ message, tone = "error" }: { message: string; tone?: "error" | "info" }) {
  return <div className={`inline-notice notice-${tone}`} role={tone === "error" ? "alert" : "status"}>{tone === "error" ? <AlertCircle size={16} /> : <Info size={16} />}<span>{message}</span></div>;
}

export type Toast = { id: number; tone: "success" | "error" | "info"; title: string; message?: string };

export function ToastStack({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div className="toast-stack" aria-live="polite">
      {toasts.map((toast) => (
        <div className={`toast toast-${toast.tone}`} key={toast.id}>
          <span className="toast-icon">{toast.tone === "success" ? <Check size={15} /> : toast.tone === "error" ? <AlertCircle size={15} /> : <Info size={15} />}</span>
          <div><strong>{toast.title}</strong>{toast.message && <p>{toast.message}</p>}</div>
          <IconButton label="Dismiss notification" className="toast-dismiss" onClick={() => onDismiss(toast.id)}><X size={15} /></IconButton>
        </div>
      ))}
    </div>
  );
}

export function formatBytes(bytes: number) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}

export function timeAgo(value: string) {
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "Unknown date";
  const diff = Math.max(0, Date.now() - timestamp);
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unknown date" : date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

