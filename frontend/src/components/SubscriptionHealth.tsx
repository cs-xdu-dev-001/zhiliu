import { useQuery } from "@tanstack/react-query";
import { Activity, CheckCircle2, Clock3, TriangleAlert } from "lucide-react";

import { api } from "../api";
import type { IntelligenceKind, SubscriptionHealthPage } from "../types";

const kindNames: Record<IntelligenceKind, string> = { news: "热点", paper: "论文", job: "招聘" };
const formatDate = (value: string | null) => value ? new Date(value).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) : "暂无";

export function SubscriptionHealth() {
  const query = useQuery({ queryKey: ["subscription-health"], queryFn: () => api.get<SubscriptionHealthPage>("/api/subscription-health"), refetchInterval: 15000 });
  const items = query.data?.items ?? [];
  return <section className="health-section" aria-labelledby="health-title">
    <div className="health-heading"><div><h2 id="health-title">订阅健康</h2><p>近30天运行质量；网络或超时失败会自动重试2次。</p></div><Activity size={21} aria-hidden="true" /></div>
    {query.isPending && <div className="list-skeleton"><i /><i /></div>}
    {query.isError && <div className="inline-error" role="alert">订阅健康加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>}
    {query.data && items.length === 0 && <div className="preference-empty"><Activity size={21} /><span>还没有可统计的订阅。</span></div>}
    {items.length > 0 && <div className="health-list">{items.map((item) => {
      const rate = item.successRate === null ? "暂无数据" : `${Math.round(item.successRate * 100)}%成功`;
      const unhealthy = item.consecutiveFailures > 0;
      return <article className={`health-row ${unhealthy ? "unhealthy" : ""}`} key={item.subscriptionId}>
        <div className="health-main"><div className="health-title"><strong>{item.name}</strong><span>{kindNames[item.kind]}</span>{!item.enabled && <em>已暂停</em>}</div><p><Clock3 size={14} />下次{formatDate(item.nextRunAt)} · 最近成功{formatDate(item.lastSuccessAt)}</p></div>
        <div className="health-facts"><span className={unhealthy ? "danger" : "success"}>{unhealthy ? <TriangleAlert size={15} /> : <CheckCircle2 size={15} />}{unhealthy ? `连续失败${item.consecutiveFailures}次` : rate}</span><span>{item.producedItemCount}条产出</span><span>{item.averageDurationMs ? `${Math.round(item.averageDurationMs / 1000)}秒平均耗时` : "暂无耗时"}</span></div>
      </article>;
    })}</div>}
  </section>;
}
