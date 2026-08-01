import { Inbox } from "lucide-react";

export function EmptyState({ title }: { title: string }) {
  return <div className="empty-state"><Inbox size={24} /><p>{title}</p></div>;
}

