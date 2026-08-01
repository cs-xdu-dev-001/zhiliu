import { useQuery } from "@tanstack/react-query";
import { Activity, Bookmark, Radio, TriangleAlert } from "lucide-react";
import { Link } from "wouter";

import { api } from "../api";
import { ItemCard } from "../components/ItemCard";
import type { Dashboard } from "../types";

export function Home() {
  const query = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dashboard>("/api/dashboard") });
  if (query.isPending) return <div className="dashboard-skeleton"><i /><i /><i /><i /></div>;
  if (query.isError) return <div className="inline-error">今日情报加载失败</div>;
  const data = query.data;
  const metrics = [
    { label: "待阅读", value: data.unreadCount, icon: Radio, tone: "green" },
    { label: "已收藏", value: data.savedCount, icon: Bookmark, tone: "blue" },
    { label: "运行订阅", value: data.activeSubscriptions, icon: Activity, tone: "amber" },
    { label: "异常任务", value: data.failedRuns, icon: TriangleAlert, tone: "coral" },
  ];
  return (
    <div className="stack-xl">
      <section className="metric-grid" aria-label="情报概览">
        {metrics.map(({ label, value, icon: Icon, tone }) => <div className={`metric ${tone}`} key={label}><Icon size={19} /><div><strong>{value}</strong><span>{label}</span></div></div>)}
      </section>
      <section>
        <div className="section-heading"><h2>优先阅读</h2><Link href="/feed">查看全部</Link></div>
        <div className="item-list">{data.topItems.map((item) => <ItemCard key={item.id} item={item} compact />)}</div>
      </section>
      {data.latestBriefing && <section>
        <div className="section-heading"><h2>最新简报</h2><Link href="/reports">历史报告</Link></div>
        <article className="briefing-preview"><div><span className={`kind-tag ${data.latestBriefing.kind}`}>简报</span><time>{new Date(data.latestBriefing.createdAt).toLocaleDateString("zh-CN")}</time></div><h3>{data.latestBriefing.title}</h3><p>{data.latestBriefing.content}</p></article>
      </section>}
    </div>
  );
}
