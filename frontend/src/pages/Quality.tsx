import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, CheckCircle2, CircleAlert, Clock3, Copy, Filter, Gauge, RotateCcw, ShieldCheck, Unlink, X } from "lucide-react";
import { Link, useSearchParams } from "wouter";

import { api } from "../api";
import type { QualityAction, QualityDecision, QualityFilter, QualityPage } from "../types";

const actionNames: Record<QualityAction, string> = { accepted: "通过", inserted: "已写入", duplicate: "已去重", filtered: "已过滤" };
const filterNames: Record<QualityFilter, string> = { filtered: "待确认过滤", duplicate: "重复复用", restored: "已恢复" };

export function Quality() {
  const [params, setParams] = useSearchParams();
  const requestedAction = params.get("action") ?? "";
  const action: QualityFilter | "" = requestedAction === "filtered" || requestedAction === "duplicate" || requestedAction === "restored" ? requestedAction : "";
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["quality", action], queryFn: () => api.get<QualityPage>(`/api/quality${action ? `?action=${action}` : ""}`), refetchInterval: 60_000 });
  const restore = useMutation({
    mutationFn: (id: number) => api.post<QualityDecision>(`/api/quality/${id}/restore`),
    onSuccess: () => {
      ["quality", "items", "item-sources", "dashboard", "search", "briefing", "trace"].forEach((key) => {
        queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
  function choose(next: QualityFilter | "") { const nextParams = new URLSearchParams(); if (next) nextParams.set("action", next); setParams(nextParams); restore.reset(); }
  const data = query.data;
  const emptyMessage = action === "filtered" ? "没有待确认的过滤内容" : action === "restored" ? "还没有恢复记录" : "暂时没有质量记录";
  return <section className="quality-page">
    <div className="quality-summary"><h2>内容状态</h2><Link className="secondary-link" href="/search"><Filter size={16} />搜索历史内容</Link></div>
    {data && <nav className="quality-status-links" aria-label="内容状态概览">
      <Link href="/feed?state=stale"><Clock3 size={18} /><strong>{data.staleCount}</strong><span>可能过期</span></Link>
      <Link href="/feed?state=low"><Gauge size={18} /><strong>{data.lowImportanceCount}</strong><span>低优先级</span></Link>
      <Link href="/feed?state=source-unavailable"><Unlink size={18} /><strong>{data.sourceUnavailableCount}</strong><span>原文失效</span></Link>
    </nav>}
    <div className="quality-record-heading"><h2>处理记录</h2></div>
    {data && <div className="quality-metrics" role="group" aria-label="质量概览"><button className={action === "filtered" ? "active" : ""} aria-pressed={action === "filtered"} onClick={() => choose(action === "filtered" ? "" : "filtered")}><CircleAlert size={18} /><strong>{data.filteredCount}</strong><span>待确认过滤</span></button><button className={action === "duplicate" ? "active" : ""} aria-pressed={action === "duplicate"} onClick={() => choose(action === "duplicate" ? "" : "duplicate")}><Copy size={18} /><strong>{data.duplicateCount}</strong><span>重复复用</span></button><button className={action === "restored" ? "active" : ""} aria-pressed={action === "restored"} onClick={() => choose(action === "restored" ? "" : "restored")}><ShieldCheck size={18} /><strong>{data.restoredCount}</strong><span>已恢复</span></button></div>}
    {data && <div className="quality-scope"><span>{action ? `${filterNames[action]} · ` : "全部 · "}{data.total}条记录</span>{action && <button type="button" onClick={() => choose("")}><X size={15} />查看全部</button>}</div>}
    {restore.isSuccess && restore.data && <div className="inline-success" role="status"><CheckCircle2 size={18} />内容已恢复写入。{restore.data.itemId && <Link href={`/items/${restore.data.itemId}`}>查看情报</Link>}</div>}
    {restore.isError && <div className="inline-error" role="alert">恢复失败：{restore.error.message}<button type="button" onClick={() => restore.reset()}>关闭</button></div>}
    {query.isPending && <div className="list-skeleton"><i /><i /><i /></div>}
    {query.isError && <div className="inline-error" role="alert">质量记录加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>}
    {data?.items.length === 0 && <div className="quality-empty" role="status" aria-label={emptyMessage}><CheckCircle2 size={20} /><span>{emptyMessage}</span></div>}
    <div className="quality-list">{data?.items.map((item) => {
      const displayAction = item.restoredAt ? "restored" : item.action;
      return <article className={`quality-row ${displayAction}`} key={item.id}><div className="quality-copy"><div className="quality-meta"><span className={`quality-action ${displayAction}`}>{item.restoredAt ? "已恢复" : actionNames[item.action]}</span><span>{item.source.trim() || "来源未标注"}</span><time>{new Date(item.createdAt).toLocaleString("zh-CN")}</time></div><h3>{item.title}</h3><p>{item.reason}</p><small>{item.summary || "暂无摘要"}</small></div><div className="quality-actions">{item.itemId ? <Link href={`/items/${item.itemId}`} aria-label={`查看${item.title}`}>查看情报<ArrowUpRight size={16} /></Link> : <a href={item.url} target="_blank" rel="noreferrer">原始链接<ArrowUpRight size={16} /></a>}{item.action === "filtered" && !item.restoredAt && <button disabled={restore.isPending && restore.variables === item.id} onClick={() => restore.mutate(item.id)}><RotateCcw size={16} />{restore.isPending && restore.variables === item.id ? "正在恢复" : "恢复写入"}</button>}</div></article>;
    })}</div>
  </section>;
}
