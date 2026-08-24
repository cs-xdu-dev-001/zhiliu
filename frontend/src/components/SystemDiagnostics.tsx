import { useQuery } from "@tanstack/react-query";
import { Activity, Cable, Database, ListTodo, Radio, RefreshCw } from "lucide-react";

import { api } from "../api";
import type { SystemDiagnostics as Diagnostics } from "../types";

const hermesLabels: Record<string, string> = {
  connected: "连接正常",
  configured: "等待检测",
  demo: "演示模式",
  unconfigured: "尚未配置",
  unreachable: "无法连接",
  unauthorized: "授权失败",
  error: "检测失败",
};

function activeAge(seconds: number | null) {
  if (seconds === null) return "没有等待任务";
  if (seconds < 60) return `最早任务等待${seconds}秒`;
  return `最早任务等待${Math.floor(seconds / 60)}分钟`;
}

function shortTime(value: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) : "尚无成功写入";
}

export function SystemDiagnostics() {
  const query = useQuery({
    queryKey: ["system-diagnostics"],
    queryFn: () => api.get<Diagnostics>("/api/diagnostics"),
    refetchInterval: 30_000,
  });

  return <section className="diagnostics-section" aria-labelledby="diagnostics-title">
    <div className="diagnostics-heading">
      <h2 id="diagnostics-title">系统诊断</h2>
      {query.data && <span className={`diagnostics-state ${query.data.status}`}>{query.data.status === "ok" ? "运行正常" : "需要检查"}</span>}
      <button type="button" className="icon-button" aria-label="刷新系统诊断" onClick={() => query.refetch()} disabled={query.isFetching}><RefreshCw size={17} className={query.isFetching ? "spin" : ""} /></button>
    </div>
    {query.isPending && <div className="diagnostics-grid" aria-label="正在加载系统诊断"><i /><i /><i /><i /></div>}
    {query.isError && <div className="inline-error" role="alert">系统诊断加载失败。<button type="button" onClick={() => query.refetch()}>重新加载</button></div>}
    {query.data && <div className="diagnostics-grid">
      <article><Database size={19} /><div><strong>数据库{query.data.database.status === "ok" ? "可用" : "不可用"}</strong><span>{query.data.database.latencyMs ?? "—"}ms · 迁移{query.data.database.migrationVersion ?? "未记录"}</span></div></article>
      <article><Activity size={19} /><div><strong>{!query.data.scheduler.enabled ? "调度器已停用" : query.data.scheduler.running ? "调度器运行中" : "调度器未运行"}</strong><span>{query.data.scheduler.jobCount}个作业 · 上次回收{query.data.scheduler.lastSweepLostCount}个中断任务</span></div></article>
      <article><ListTodo size={19} /><div><strong>{query.data.queue.running}个处理中 · {query.data.queue.queued}个等待</strong><span>{activeAge(query.data.queue.oldestActiveSeconds)}</span></div></article>
      <article><Radio size={19} /><div><strong>Hermes{hermesLabels[query.data.hermes.status] ?? query.data.hermes.status}</strong><span>{query.data.hermes.configured ? "连接配置已保存" : "需要先完成连接配置"}</span></div></article>
      <article><Cable size={19} /><div><strong>{query.data.mcp.status === "verified" ? "MCP写入已验证" : query.data.mcp.status === "failed" ? "MCP最近写入失败" : "MCP等待首次写入"}</strong><span>最近成功{shortTime(query.data.mcp.lastWriteAt)}</span></div></article>
    </div>}
  </section>;
}
