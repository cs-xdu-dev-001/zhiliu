import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, CircleDashed, Clock3, XCircle } from "lucide-react";
import { Link } from "wouter";

import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import type { Subscription, TaskRunPage } from "../types";

const statusMeta = {
  queued: { label: "已排队", icon: CircleDashed }, running: { label: "执行中", icon: Clock3 }, success: { label: "已完成", icon: CheckCircle2 }, failed: { label: "失败", icon: XCircle },
};

export function Tasks() {
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api.get<TaskRunPage>("/api/runs"), refetchInterval: 5000 });
  const subscriptions = useQuery({ queryKey: ["subscriptions"], queryFn: () => api.get<Subscription[]>("/api/subscriptions") });
  const names = new Map(subscriptions.data?.map((item) => [item.id, item.name]));
  return <section className="stack-lg">
    <div className="settings-toolbar"><Link className="secondary-link" href="/settings"><ArrowLeft size={17} />返回订阅</Link><span className="auto-refresh">每5秒更新</span></div>
    {runs.isPending && <div className="list-skeleton"><i /><i /><i /></div>}
    {runs.data?.items.length === 0 && <EmptyState title="还没有任务记录" />}
    <div className="task-list">{runs.data?.items.map((run) => { const meta = statusMeta[run.status]; const Icon = meta.icon; return <article className={`task-row ${run.status}`} key={run.id}><Icon size={19} /><div><strong>{names.get(run.subscriptionId) ?? `订阅 #${run.subscriptionId}`}</strong><span>{new Date(run.startedAt).toLocaleString("zh-CN")} {run.durationMs !== null && `· ${(run.durationMs / 1000).toFixed(1)}s`}</span>{run.errorMessage && <p>{run.errorMessage}</p>}</div><span className="task-status">{meta.label}</span></article>; })}</div>
  </section>;
}
