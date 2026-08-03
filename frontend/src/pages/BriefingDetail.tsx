import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Copy, Download, ExternalLink, GitBranch } from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "wouter";

import { api, ApiError } from "../api";
import type { BriefingDetail as BriefingDetailType } from "../types";

const kindLabels = { news: "热点", paper: "论文", job: "招聘" };

function reportSummary(content: string) {
  const normalized = content.replace(/\s+/g, " ").trim();
  return normalized.length > 240 ? `${normalized.slice(0, 240)}…` : normalized;
}

function safeSourceUrl(value: string) {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

function markdownText(value: string) {
  return value.replace(/([\\\[\]])/g, "\\$1");
}

function reportMarkdown(report: BriefingDetailType) {
  const sources = report.sourceItems.length
    ? report.sourceItems.map((item, index) => {
        const sourceUrl = safeSourceUrl(item.url);
        const title = markdownText(item.title);
        return sourceUrl
          ? `${index + 1}. [${title}](<${sourceUrl}>) — ${item.source}`
          : `${index + 1}. ${title} — ${item.source}（原文链接不可用）`;
      }).join("\n")
    : "暂无可追溯来源";
  return `# ${report.title}\n\n- 类型：${kindLabels[report.kind]}\n- 生成时间：${new Date(report.createdAt).toLocaleString("zh-CN")}\n- 来源情报：${report.sourceItems.length}条\n\n${report.content.trim()}\n\n## 来源情报\n\n${sources}\n`;
}

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
  const [actionNotice, setActionNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
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

  async function copySummary() {
    try {
      await navigator.clipboard.writeText(`${report.title}\n\n${reportSummary(report.content)}`);
      setActionNotice({ tone: "success", text: "报告摘要已复制" });
    } catch {
      setActionNotice({ tone: "error", text: "复制失败，请检查浏览器剪贴板权限" });
    }
  }

  function downloadMarkdown() {
    try {
      const blob = new Blob([reportMarkdown(report)], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${report.title.replace(/[\\/:*?"<>|]/g, "-").slice(0, 80) || `报告-${report.id}`}.md`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      setActionNotice({ tone: "success", text: "Markdown报告已导出" });
    } catch {
      setActionNotice({ tone: "error", text: "导出失败，请稍后重试" });
    }
  }

  return (
    <article className="detail-page">
      <Link className="detail-back" href={backHref}><ArrowLeft size={17} />返回报告列表</Link>
      <div className="detail-copy">
        <div className="detail-meta">
          <span className={`kind-tag ${report.kind}`}>{kindLabels[report.kind]}</span>
          <time dateTime={report.createdAt}>{new Date(report.createdAt).toLocaleString("zh-CN")}</time>
          <span>报告收录{report.itemCount}条情报</span>
        </div>
        <h2>{report.title}</h2>
        {(report.periodStart || report.periodEnd) && (
          <p className="report-period">覆盖时间：{report.periodStart ? new Date(report.periodStart).toLocaleDateString("zh-CN") : "未指定"}—{report.periodEnd ? new Date(report.periodEnd).toLocaleDateString("zh-CN") : "未指定"}</p>
        )}
        <div className="report-actions"><button onClick={copySummary}><Copy size={17} />复制摘要</button><button onClick={downloadMarkdown}><Download size={17} />导出Markdown</button></div>
        {actionNotice && <div className={`report-action-notice ${actionNotice.tone}`} role={actionNotice.tone === "error" ? "alert" : "status"}>{actionNotice.text}</div>}
        <p className="report-body">{report.content}</p>
      </div>
      <section className="lineage-section" aria-labelledby="sources-heading">
        <div className="lineage-heading">
          <GitBranch size={19} />
          <h2 id="sources-heading">来源情报</h2>
          <span className="source-count">{report.sourceItems.length}条</span>
          {report.publication && <Link className="trace-link" href={`/traces/${report.publication.id}`}>查看生成链路</Link>}
        </div>
        {report.traceAvailable ? (
          report.sourceItems.length ? <div className="source-list">
            {report.sourceItems.map((item) => {
              const sourceUrl = safeSourceUrl(item.url);
              return <article className="source-row" key={item.id}>
                <div>
                  <Link className="source-title" href={`/items/${item.id}?from=${encodeURIComponent(`/reports/${report.id}`)}`}>{item.title}</Link>
                  <p>{item.summary}</p>
                  <span>{item.source} · {item.wasInserted ? "本次写入" : "复用已有情报"}{item.isInvalid ? " · 已标记无效" : ""}</span>
                </div>
                {sourceUrl ? <a className="source-external" href={sourceUrl} target="_blank" rel="noreferrer"><ExternalLink size={16} />打开原文（新窗口）</a> : <span className="source-unavailable">原文链接不可用</span>}
              </article>;
            })}
          </div> : <p className="trace-empty">本报告没有关联来源情报</p>
        ) : <p className="trace-empty">历史数据，暂无完整追踪信息</p>}
      </section>
    </article>
  );
}
