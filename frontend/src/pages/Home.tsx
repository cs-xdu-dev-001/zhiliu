import { useQuery } from "@tanstack/react-query";
import { Activity, Bookmark, Cable, Radio, TriangleAlert } from "lucide-react";
import { Link } from "wouter";

import { api } from "../api";
import { BriefingCard } from "../components/BriefingCard";
import { ItemCard } from "../components/ItemCard";
import { TaskRunCard, taskMessage } from "../components/TaskRunCard";
import type { Dashboard, HermesConnection } from "../types";

const hermesIssueTitle: Partial<Record<HermesConnection["status"], string>> = {
  unconfigured: "Hermes尚未配置",
  unreachable: "Hermes暂时无法访问",
  unauthorized: "Hermes授权无效",
  error: "Hermes连接检查失败",
};

export function Home() {
  const query = useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dashboard>("/api/dashboard"), refetchInterval: 5000 });
  const hermesQuery = useQuery({
    queryKey: ["hermes-connection"],
    queryFn: () => api.get<HermesConnection>("/api/integrations/hermes"),
    refetchInterval: 15000,
  });
  if (query.isPending) return <div className="dashboard-skeleton"><i /><i /><i /><i /></div>;
  if (query.isError) return <div className="inline-error">首页数据加载失败<button type="button" onClick={() => query.refetch()}>重新加载</button></div>;
  const data = query.data;
  const latestFailedRun = data.recentRuns?.find((run) => run.status === "failed");
  const hermesNeedsAttention = hermesQuery.isError || (hermesQuery.data && hermesQuery.data.status !== "connected");
  const hasAttention = data.failedRuns > 0 || Boolean(hermesNeedsAttention);
  const hermesTitle = hermesQuery.isError
    ? "Hermes连接检查失败"
    : hermesIssueTitle[hermesQuery.data?.status ?? "error"] ?? "Hermes连接异常";
  const hermesMessage = hermesQuery.isError
    ? "暂时无法读取连接状态，请到设置页重新检查。"
    : hermesQuery.data?.message || "请检查服务地址和API密钥。";
  const metrics = [
    { label: "待阅读", value: data.unreadCount, icon: Radio, tone: "green", href: "/feed?state=unread" },
    { label: "已收藏", value: data.savedCount, icon: Bookmark, tone: "blue", href: "/feed?state=saved" },
    { label: "运行订阅", value: data.activeSubscriptions, icon: Activity, tone: "amber", href: "/settings" },
    { label: "异常任务", value: data.failedRuns, icon: TriangleAlert, tone: "coral", href: "/tasks?status=failed" },
  ];
  return (
    <div className="stack-xl">
      <section className="metric-grid" aria-label="情报概览">
        {metrics.map(({ label, value, icon: Icon, tone, href }) => <Link className={`metric ${tone}`} href={href} key={label}><Icon size={19} /><div><strong>{value}</strong><span>{label}</span></div></Link>)}
      </section>
      {hasAttention && <section aria-labelledby="attention-heading">
        <div className="section-heading"><h2 id="attention-heading">需要处理</h2></div>
        <div className="attention-list">
          {data.failedRuns > 0 && <Link className="attention-row danger" href="/tasks?status=failed">
            <span className="attention-icon"><TriangleAlert size={20} /></span>
            <span className="attention-copy">
              <strong>{data.failedRuns}个异常任务</strong>
              <span>{latestFailedRun ? `${latestFailedRun.topic || latestFailedRun.subscriptionName || `任务#${latestFailedRun.id}`}：${taskMessage(latestFailedRun)}` : "查看失败原因并决定是否重试。"}</span>
            </span>
            <span className="attention-action">查看异常任务</span>
          </Link>}
          {hermesNeedsAttention && <Link className="attention-row warning" href="/settings">
            <span className="attention-icon"><Cable size={20} /></span>
            <span className="attention-copy"><strong>{hermesTitle}</strong><span>{hermesMessage}</span></span>
            <span className="attention-action">检查Hermes连接</span>
          </Link>}
        </div>
      </section>}
      <section>
        <div className="section-heading"><h2>优先阅读</h2><Link href="/feed">查看全部</Link></div>
        {data.topItems.length > 0
          ? <div className="item-list">{data.topItems.map((item) => <ItemCard key={item.id} item={item} detailHref={`/items/${item.id}?from=${encodeURIComponent("/")}`} compact />)}</div>
          : <div className="dashboard-empty">没有待阅读情报，新的微信整理结果会显示在这里。<Link href="/feed">查看全部情报</Link></div>}
      </section>
      {data.recentRuns?.length > 0 && <section>
        <div className="section-heading"><h2>最近处理动态</h2><Link href="/tasks">全部任务</Link></div>
        <div className="task-list task-list-compact">{data.recentRuns.slice(0, 3).map((run) => <TaskRunCard key={run.id} run={run} />)}</div>
      </section>}
      <section>
        <div className="section-heading"><h2>最新简报</h2><Link href="/reports">历史报告</Link></div>
        {data.latestBriefing
          ? <BriefingCard briefing={data.latestBriefing} detailHref={`/reports/${data.latestBriefing.id}?from=${encodeURIComponent("/")}`} />
          : <div className="dashboard-empty">还没有简报，Hermes完成整理并写入后会显示在这里。<Link href="/tasks">查看处理进度</Link></div>}
      </section>
    </div>
  );
}
