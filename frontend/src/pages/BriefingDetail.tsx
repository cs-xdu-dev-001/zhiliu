import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, GitBranch } from "lucide-react";
import { Link, useParams, useSearchParams } from "wouter";

import { api, ApiError } from "../api";
import type { BriefingDetail as BriefingDetailType } from "../types";

const kindLabels = { news: "热点", paper: "论文", job: "招聘" };

function safeBackHref(value: string | null) {
  if (!value?.startsWith("/")) return "/reports";
  try {
    const target = new URL(value, window.location.origin);
    return target.origin === window.location.origin
      ? `${target.pathname}${target.search}${target.hash}`
      : "/reports";
  } catch {
    return "/reports";
  }
}

export function BriefingDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const query = useQuery({
    queryKey: ["briefing", id],
    queryFn: () => api.get<BriefingDetailType>(`/api/briefings/${id}`),
  });
  const backHref = safeBackHref(searchParams.get("from"));

  if (query.isPending) return <div className="detail-skeleton" role="status" aria-label="正在加载报告" />;
  if (query.error instanceof ApiError && query.error.status === 404) {
    return <div className="empty-state"><p>报告不存在或已删除</p><Link className="secondary-link" href={backHref}>返回报告列表</Link></div>;
  }
  if (query.isError) return <div className="inline-error" role="alert">报告加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>;

  const report = query.data;

  return (
    <article className="detail-page">
      <Link className="detail-back" href={backHref}><ArrowLeft size={17} />返回报告列表</Link>
      <div className="detail-copy">
        <div className="detail-meta">
          <span className={`kind-tag ${report.kind}`}>{kindLabels[report.kind]}</span>
          <time dateTime={report.createdAt}>{new Date(report.createdAt).toLocaleString("zh-CN")}</time>
          <span>{report.itemCount}条情报</span>
        </div>
        <h2>{report.title}</h2>
        {(report.periodStart || report.periodEnd) && (
          <p className="report-period">覆盖时间：{report.periodStart ? new Date(report.periodStart).toLocaleDateString("zh-CN") : "未指定"}—{report.periodEnd ? new Date(report.periodEnd).toLocaleDateString("zh-CN") : "未指定"}</p>
        )}
        <p className="report-body">{report.content}</p>
      </div>
      <section className="lineage-section" aria-labelledby="sources-heading">
        <div className="lineage-heading">
          <GitBranch size={19} />
          <h2 id="sources-heading">来源情报</h2>
          {report.publication && <Link className="trace-link" href={`/traces/${report.publication.id}`}>查看生成链路</Link>}
        </div>
        {report.traceAvailable ? (
          <div className="source-list">
            {report.sourceItems.map((item) => (
              <article className="source-row" key={item.id}>
                <div>
                  <Link className="source-title" href={`/items/${item.id}?from=${encodeURIComponent(`/reports/${report.id}`)}`}>{item.title}</Link>
                  <p>{item.summary}</p>
                  <span>{item.source} · {item.wasInserted ? "本次写入" : "复用已有情报"}</span>
                </div>
                <a className="source-external" href={item.url} target="_blank" rel="noreferrer"><ExternalLink size={16} />打开原文（新窗口）</a>
              </article>
            ))}
          </div>
        ) : <p className="trace-empty">历史数据，暂无完整追踪信息</p>}
      </section>
    </article>
  );
}
