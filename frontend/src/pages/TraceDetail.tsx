import { useQuery } from "@tanstack/react-query";
import { Bot, Database, FileText, MessageCircle, Radio, Workflow } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "wouter";

import { api, ApiError } from "../api";
import type { PublicationTrace } from "../types";

const TRACE_PREVIEW_COUNT = 6;

export function TraceDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const [showAllItems, setShowAllItems] = useState(false);
  const query = useQuery({
    queryKey: ["publication-trace", id],
    queryFn: () => api.get<PublicationTrace>(`/api/publications/${id}/trace`),
  });

  if (query.isPending) return <div className="detail-skeleton" role="status" aria-label="正在加载处理链路" />;
  if (query.error instanceof ApiError && query.error.status === 404) {
    return <div className="empty-state"><p>追踪记录不存在或已删除</p><Link className="secondary-link" href="/">返回首页</Link></div>;
  }
  if (query.isError) return <div className="inline-error" role="alert">处理链路加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>;

  const trace = query.data;
  const isWeixin = trace.origin === "weixin-hermes";
  const isReport = trace.origin === "web-report";
  const from = encodeURIComponent(`/traces/${trace.publicationId}`);
  const visibleItems = showAllItems ? trace.items : trace.items.slice(0, TRACE_PREVIEW_COUNT);
  const hiddenItemCount = trace.items.length - visibleItems.length;

  return (
    <article className="trace-page">
      <header className="trace-header">
        <h2>完整处理链路</h2>
        <p>追踪号：{trace.traceId ?? `回执-${trace.publicationId}`}</p>
      </header>
      <div className="trace-timeline">
        <section className="trace-step">
          <div className="trace-marker"><MessageCircle size={19} /></div>
          <div>
            <h3>{isWeixin ? "微信指令" : isReport ? "知流报告要求" : "定时订阅输入"}</h3>
            <p>{trace.requestSummary}</p>
          </div>
        </section>
        <section className="trace-step">
          <div className="trace-marker"><Bot size={19} /></div>
          <div>
            <h3>Hermes整理任务</h3>
            <p>{trace.hermesRunId ? `任务ID：${trace.hermesRunId}` : "本次网关未提供任务ID"}</p>
          </div>
        </section>
        <section className="trace-step">
          <div className="trace-marker"><Workflow size={19} /></div>
          <div>
            <h3>{isWeixin ? "MCP写入知流" : isReport ? "报告与来源写入知流" : "定时任务写入知流"}</h3>
            <p>回执#{trace.publicationId}，写入{trace.itemCount}条，复用{trace.skippedCount}条</p>
            <time dateTime={trace.createdAt}>{new Date(trace.createdAt).toLocaleString("zh-CN")}</time>
          </div>
        </section>
        <section className="trace-step">
          <div className="trace-marker"><Database size={19} /></div>
          <div>
            <h3>情报入库</h3>
            {trace.items.length ? (
              <div className="trace-item-list">
                {visibleItems.map((item) => (
                  <div key={item.id}>
                    <Link href={`/items/${item.id}?from=${from}`}>{item.title}</Link>
                    <span>{item.wasInserted ? "新写入" : "复用已有情报"} · {item.source.trim() || "来源未标注"}{item.isInvalid ? " · 已标记无效" : ""}</span>
                  </div>
                ))}
                {trace.items.length > TRACE_PREVIEW_COUNT && <button className="secondary-compact trace-items-toggle" type="button" aria-expanded={showAllItems} onClick={() => setShowAllItems((current) => !current)}>{showAllItems ? "收起来源情报" : `展开其余${hiddenItemCount}条`}</button>}
              </div>
            ) : <p>本次没有写入情报</p>}
          </div>
        </section>
        <section className="trace-step">
          <div className="trace-marker"><FileText size={19} /></div>
          <div>
            <h3>报告生成</h3>
            {trace.briefing
              ? <Link className="trace-result-link" href={`/reports/${trace.briefing.id}?from=${from}`}>{trace.briefing.title}</Link>
              : <p>本次未生成报告</p>}
          </div>
        </section>
      </div>
      <div className="trace-origin"><Radio size={16} />{isReport ? `来源情报：${trace.items.length}条` : `来源分类：${trace.subscription.name}`}</div>
    </article>
  );
}
