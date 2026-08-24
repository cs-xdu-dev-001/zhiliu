import { Inbox } from "lucide-react";
import type { ReactNode } from "react";

export function EmptyState({ title, description, action, compact = false, icon }: { title: string; description?: string; action?: ReactNode; compact?: boolean; icon?: ReactNode }) {
  return <div className={`empty-state${compact ? " compact" : ""}`} role="status" aria-label={title}>{icon ?? <Inbox size={compact ? 20 : 24} />}<strong>{title}</strong>{description && <p>{description}</p>}{action}</div>;
}
