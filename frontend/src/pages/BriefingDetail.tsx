import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams, useSearchParams } from "wouter";

import { api, ApiError } from "../api";
import type { Briefing } from "../types";

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
    queryFn: () => api.get<Briefing>(`/api/briefings/${id}`),
  });
  const backHref = safeBackHref(searchParams.get("from"));

  if (query.isPending) return <div className="detail-skeleton" aria-label="正在加载报告" />;
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
    </article>
  );
}
