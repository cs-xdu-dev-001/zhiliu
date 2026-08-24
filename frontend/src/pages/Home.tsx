import { useQuery } from "@tanstack/react-query";
import { Activity, Bookmark, Cable, Check, Copy, MessageSquareText, Radio, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Link } from "wouter";

import { api } from "../api";
import { BriefingCard } from "../components/BriefingCard";
import { DailyAttention } from "../components/DailyAttention";
import { ItemCard } from "../components/ItemCard";
import { TaskRunCard, taskMessage } from "../components/TaskRunCard";
import type { Dashboard, HermesConnection } from "../types";

const hermesIssueTitle: Partial<Record<HermesConnection["status"], string>> = {
  unconfigured: "Hermes尚未配置",
  unreachable: "Hermes暂时无法访问",
  unauthorized: "Hermes授权无效",
  error: "Hermes连接检查失败",
};

const firstWeChatCommand = "请检索今天AI Agent领域的重要更新，整理后写入知流，并生成一份带来源链接的简报。";

export function Home() {
  const [copyState, setCopyState] = useState<"idle" | "success" | "error">("idle");
  const query = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<Dashboard>("/api/dashboard"),
    refetchInterval: (current) => current.state.data?.recentRuns?.some((run) => run.status === "queued" || run.status === "running") ? 5000 : 60_000,
  });
  const hermesQuery = useQuery({
    queryKey: ["hermes-connection"],
    queryFn: () => api.get<HermesConnection>("/api/integrations/hermes"),
    refetchInterval: (current) => current.state.data?.status === "connected" ? 60_000 : 15_000,
  });
  if (query.isPending) return <div className="dashboard-skeleton"><i /><i /><i /><i /></div>;
  if (query.isError) return <div className="inline-error" role="alert">首页数据加载失败<button type="button" onClick={() => query.refetch()}>重新加载</button></div>;
  const data = query.data;
  const latestFailedRun = data.recentRuns?.find((run) => run.status === "failed");
  const hermesNeedsAttention = hermesQuery.isError || (hermesQuery.data && hermesQuery.data.status !== "connected");
  const hermesTemporarilyOffline = hermesQuery.isError
    || hermesQuery.data?.status === "unreachable"
    || hermesQuery.data?.status === "error";
  const showConnectionNotice = hermesNeedsAttention && !hermesTemporarilyOffline;
  const hermesTitle = hermesQuery.isError
    ? "Hermes连接检查失败"
    : hermesIssueTitle[hermesQuery.data?.status ?? "error"] ?? "Hermes连接异常";
  const hermesMessage = hermesQuery.isError
    ? "暂时无法读取连接状态，请到设置页重新检查。"
    : hermesQuery.data?.message || "请检查服务地址和API密钥。";
  const showQuickStart = data.topItems.length === 0
    && !data.latestBriefing
    && (data.recentRuns?.length ?? 0) === 0
    && hermesQuery.data?.status === "connected";
  const hasRecentRuns = (data.recentRuns?.length ?? 0) > 0;

  async function copyFirstCommand() {
    try {
      await navigator.clipboard.writeText(firstWeChatCommand);
      setCopyState("success");
    } catch {
      setCopyState("error");
    }
  }
  const metrics = [
    { label: "待阅读", value: data.unreadCount, icon: Radio, tone: "green", href: "/feed?state=unread" },
    { label: "已收藏", value: data.savedCount, icon: Bookmark, tone: "blue", href: "/feed?state=saved" },
    { label: "运行订阅", value: data.activeSubscriptions, icon: Activity, tone: "amber", href: "/settings" },
    { label: "异常任务", value: data.failedRuns, icon: TriangleAlert, tone: "coral", href: "/tasks?status=failed" },
  ];
  return (
    <div className="stack-xl home-stack">
      <section className="metric-grid" aria-label="情报概览">
        {metrics.map(({ label, value, icon: Icon, tone, href }) => <Link className={`metric ${tone}`} href={href} key={label}><Icon size={19} /><div><strong>{value}</strong><span>{label}</span></div></Link>)}
      </section>
      {data.failedRuns > 0 && <section className="home-attention" aria-label="需要处理">
        <div className="attention-list">
          {data.failedRuns > 0 && <Link className="attention-row danger" href="/tasks?status=failed" aria-label={`${data.failedRuns}个异常任务，查看异常任务`}>
            <span className="attention-icon"><TriangleAlert size={20} /></span>
            <span className="attention-copy">
              <strong>{data.failedRuns}个异常任务</strong>
              <span>{latestFailedRun ? `${latestFailedRun.topic || latestFailedRun.subscriptionName || `任务#${latestFailedRun.id}`}：${taskMessage(latestFailedRun)}` : "查看失败原因并决定是否重试。"}</span>
            </span>
            <span className="attention-action"><span className="attention-action-full">查看异常任务</span><span className="attention-action-short" aria-hidden="true">查看</span></span>
          </Link>}
        </div>
      </section>}
      {showConnectionNotice && <Link className="home-connection-note" href="/settings?view=runtime">
        <Cable size={18} />
        <span><strong>{hermesTitle}</strong><span>{hermesMessage}</span></span>
        <span className="home-connection-action">去设置</span>
      </Link>}
      {showQuickStart && <section className="quick-start" aria-labelledby="quick-start-heading">
        <span className="quick-start-icon"><MessageSquareText size={22} /></span>
        <div className="quick-start-copy">
          <h2 id="quick-start-heading">从微信发出第一条知流指令</h2>
          <p className="quick-start-command">{firstWeChatCommand}</p>
          <div className="quick-start-actions">
            <button className="primary-button" type="button" onClick={copyFirstCommand}>{copyState === "success" ? <Check size={17} /> : <Copy size={17} />}{copyState === "success" ? "已复制，去微信发送" : "复制示例指令"}</button>
            <Link className="secondary-link" href="/tasks">查看处理记录</Link>
          </div>
          {copyState === "error" && <p className="form-error" role="alert">复制失败，请长按选中上方指令后复制。</p>}
        </div>
      </section>}
      {!showQuickStart && <div className={`home-content-grid ${hasRecentRuns ? "three-columns" : "two-columns"}`}>
        <section className="home-reading">
          <div className="section-heading"><h2>优先阅读</h2><Link href="/feed">查看全部</Link></div>
          {data.topItems.length > 0
            ? <div className="home-priority">{data.topItems.slice(0, 2).map((item) => <ItemCard key={item.id} item={item} detailHref={`/items/${item.id}?from=${encodeURIComponent("/")}`} compact />)}</div>
            : <div className="dashboard-empty">没有待阅读情报，新的微信整理结果会显示在这里。<Link href="/feed">查看全部情报</Link></div>}
        </section>
        <div className="home-side-column">
          {hasRecentRuns && <section className="home-runs">
            <div className="section-heading"><h2>最近处理动态</h2><div className="section-heading-actions">{hermesTemporarilyOffline && <Link className="section-status" href="/settings?view=runtime"><Cable size={14} />Hermes离线</Link>}<Link href="/tasks">全部任务</Link></div></div>
            <div className="task-list task-list-compact">{data.recentRuns.slice(0, 2).map((run) => <TaskRunCard key={run.id} run={run} />)}</div>
          </section>}
          <section className="home-briefing">
            <div className="section-heading"><h2>最新简报</h2><div className="section-heading-actions">{hermesTemporarilyOffline && !hasRecentRuns && <Link className="section-status" href="/settings?view=runtime"><Cable size={14} />Hermes离线</Link>}<Link href="/reports">历史报告</Link></div></div>
            {data.latestBriefing
              ? <BriefingCard briefing={data.latestBriefing} detailHref={`/reports/${data.latestBriefing.id}?from=${encodeURIComponent("/")}`} />
              : <div className="dashboard-empty">还没有简报，Hermes完成整理并写入后会显示在这里。<Link href="/tasks">查看处理进度</Link></div>}
          </section>
        </div>
      </div>}
      <DailyAttention />
    </div>
  );
}
