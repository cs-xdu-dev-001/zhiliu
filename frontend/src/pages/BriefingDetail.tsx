import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CheckCircle2, Copy, Download, ExternalLink, GitBranch, RefreshCw, X } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "wouter";

import { api, ApiError } from "../api";
import type { BriefingDetail as BriefingDetailType, TaskRun } from "../types";
import { useModalDialog } from "../useModalDialog";

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

function reportContent(content: string, sourceCount: number) {
  return content.split(/(\[\d+])/g).map((part, index) => {
    const match = /^\[(\d+)]$/.exec(part);
    if (!match) return part;
    const citation = Number(match[1]);
    return citation >= 1 && citation <= sourceCount
      ? <a aria-label={`查看来源${citation}`} className="inline-citation" href={`#source-${citation}`} key={`${part}-${index}`}>{part}</a>
      : part;
  });
}

function reportMarkdown(report: BriefingDetailType) {
  const sources = report.sourceItems.length
    ? report.sourceItems.map((item, index) => {
        const sourceUrl = item.evidenceStatus === "traceable" || item.evidenceStatus === "unreferenced" ? safeSourceUrl(item.url) : null;
        const source = item.source.trim() || "来源未标注";
        const title = markdownText(item.title);
        return sourceUrl
          ? `${index + 1}. [${title}](<${sourceUrl}>) — ${source}`
          : `${index + 1}. ${title} — ${source}（${item.evidenceMessage}）`;
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
  const [, navigate] = useLocation();
  const { id = "" } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const [actionNotice, setActionNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [regenerateOpen, setRegenerateOpen] = useState(false);
  const [regenerateInstruction, setRegenerateInstruction] = useState("");
  const [regenerateChangesOnly, setRegenerateChangesOnly] = useState(false);
  const regenerateRequestIdRef = useRef("");
  const query = useQuery({
    queryKey: ["briefing", id],
    queryFn: () => api.get<BriefingDetailType>(`/api/briefings/${id}`),
  });
  const backHref = safeBackHref(searchParams.get("from"));
  const regenerate = useMutation({
    mutationFn: () => api.post<TaskRun>(`/api/briefings/${id}/regenerate`, {
      instruction: regenerateInstruction.trim(),
      requestId: regenerateRequestIdRef.current ||= crypto.randomUUID(),
      ...(regenerateChangesOnly ? { changesOnly: true } : {}),
    }),
    onSuccess: (task) => {
      regenerateRequestIdRef.current = "";
      setRegenerateChangesOnly(false);
      navigate(`/tasks/${task.id}`);
    },
  });
  function closeRegenerateDialog() {
    if (regenerate.isPending) return;
    regenerateRequestIdRef.current = "";
    setRegenerateChangesOnly(false);
    setRegenerateInstruction("");
    setRegenerateOpen(false);
    regenerate.reset();
  }
  const { dialogRef: regenerateDialogRef, rememberTrigger: rememberRegenerateTrigger } = useModalDialog<HTMLElement>(regenerateOpen, closeRegenerateDialog, regenerate.isPending);

  function openRegenerateDialog(trigger: HTMLElement) {
    regenerateRequestIdRef.current = crypto.randomUUID();
    regenerate.reset();
    rememberRegenerateTrigger(trigger);
    setRegenerateOpen(true);
  }

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
          {report.seriesId && <span>v{report.versionNumber ?? 1}</span>}
        </div>
        <h2>{report.title}</h2>
        {(report.periodStart || report.periodEnd) && (
          <p className="report-period">覆盖时间：{report.periodStart ? new Date(report.periodStart).toLocaleDateString("zh-CN") : "未指定"}—{report.periodEnd ? new Date(report.periodEnd).toLocaleDateString("zh-CN") : "未指定"}</p>
        )}
        <div className="report-actions"><button onClick={copySummary}><Copy size={17} />复制摘要</button><button aria-label="导出Markdown" onClick={downloadMarkdown}><Download size={17} /><span className="report-action-full">导出Markdown</span><span className="report-action-short">导出MD</span></button>{report.traceAvailable && <><Link className="report-add-sources" href={`/feed?report=${report.id}`}>补充来源</Link><button className="report-regenerate" onClick={(event) => openRegenerateDialog(event.currentTarget)}><RefreshCw size={17} />重新生成</button></>}</div>
        {actionNotice && <div className={`report-action-notice ${actionNotice.tone}`} role={actionNotice.tone === "error" ? "alert" : "status"}>{actionNotice.text}</div>}
        {report.citationStatus === "valid" && <div className="citation-state valid"><CheckCircle2 size={17} />引用编号完整且可追溯，不代表事实已外部核验</div>}
        {report.citationStatus === "warning" && <details className="citation-warning-details"><summary><AlertTriangle size={17} />有{report.citationWarnings?.length ?? 0}条来源未在正文中引用</summary><ul>{report.citationWarnings?.map((warning) => <li key={warning}>{warning}</li>)}</ul></details>}
        <p className="report-body">{reportContent(report.content, report.sourceItems.length)}</p>
      </div>
      {(report.versions?.length ?? 0) > 1 && <nav className="report-versions" aria-label="报告版本"><span>版本</span>{report.versions?.map((version) => version.id === report.id ? <strong key={version.id}>v{version.versionNumber ?? 1}</strong> : <Link key={version.id} href={`/reports/${version.id}`}>v{version.versionNumber ?? 1}</Link>)}</nav>}
      {report.versionDiff && <section className="version-diff" aria-labelledby="version-diff-heading">
        <div className="version-diff-heading"><h2 id="version-diff-heading">相较v{report.versionDiff.previousVersionNumber}</h2><Link href={`/reports/${report.versionDiff.previousVersionId}`}>查看上一版</Link></div>
        <div className="version-diff-facts">
          {report.versionDiff.titleChanged && <span>标题已调整</span>}
          {report.versionDiff.instructionChanged && <span>整理要求已调整</span>}
          <span>新增{report.versionDiff.addedSegmentCount}段</span>
          <span>删去{report.versionDiff.removedSegmentCount}段</span>
          <span>来源+{report.versionDiff.addedSourceIds.length}/-{report.versionDiff.removedSourceIds.length}</span>
        </div>
        {report.versionDiff.instructionChanged && <div className="instruction-diff"><p><span>上一版</span>{report.versionDiff.previousInstruction || "默认整理要求"}</p><p><span>当前版</span>{report.versionDiff.currentInstruction || "默认整理要求"}</p></div>}
        {(report.versionDiff.addedSources.length > 0 || report.versionDiff.removedSources.length > 0) && <div className="source-diff-list">
          {report.versionDiff.addedSources.map((source) => <p className="added" key={`added-${source.id}`}><span>新增来源</span><Link href={`/items/${source.id}?from=${encodeURIComponent(`/reports/${report.id}`)}`}>{source.title}</Link></p>)}
          {report.versionDiff.removedSources.map((source) => <p className="removed" key={`removed-${source.id}`}><span>移除来源</span><Link href={`/items/${source.id}?from=${encodeURIComponent(`/reports/${report.id}`)}`}>{source.title}</Link></p>)}
        </div>}
        {report.versionDiff.changes.length > 0 && <details><summary>查看正文变化</summary><div className="version-change-list">{report.versionDiff.changes.map((change, index) => <p className={change.kind} key={`${change.kind}-${index}`}><span>{change.kind === "added" ? "+" : "−"}</span>{change.text}</p>)}</div>{report.versionDiff.condensed && <p className="version-diff-note">长报告仅展示前8处变化，统计包含全部段落。</p>}</details>}
      </section>}
      <section className="lineage-section" aria-labelledby="sources-heading">
        <div className="lineage-heading">
          <GitBranch size={19} />
          <h2 id="sources-heading">来源情报</h2>
          <span className="source-count">{report.sourceItems.length}条</span>
          {report.publication && <Link className="trace-link" href={`/traces/${report.publication.id}?from=${encodeURIComponent(`/reports/${report.id}`)}`}>查看生成链路</Link>}
        </div>
        {report.traceAvailable ? (
          report.sourceItems.length ? <div className="source-list">
            {report.sourceItems.map((item) => {
              const sourceUrl = item.evidenceStatus === "traceable" || item.evidenceStatus === "unreferenced" ? safeSourceUrl(item.url) : null;
              const evidenceLabel = {
                traceable: "可追溯",
                unreferenced: "未引用",
                "source-unavailable": "来源失效",
                invalid: "情报无效",
                "unsafe-link": "链接停用",
              }[item.evidenceStatus];
              return <article className="source-row" id={`source-${item.ordinal + 1}`} key={item.id}>
                <div>
                  <Link aria-label={item.title} className="source-title" href={`/items/${item.id}?from=${encodeURIComponent(`/reports/${report.id}`)}`}><span aria-hidden="true" className="citation-index">[{item.ordinal + 1}]</span>{item.title}</Link>
                  <p>{item.summary || "暂无摘要"}</p>
                  <span>{item.source.trim() || "来源未标注"} · {item.wasInserted ? "本次写入" : "复用已有情报"}</span>
                  <span className={`evidence-state ${item.evidenceStatus}`} title={item.evidenceMessage}>{evidenceLabel} · {item.evidenceMessage}</span>
                </div>
                {sourceUrl ? <a className="source-external" href={sourceUrl} target="_blank" rel="noreferrer" aria-label="打开原文（新窗口）"><ExternalLink size={16} aria-hidden="true" />打开原文（新窗口）</a> : <span className="source-unavailable">原文不可用</span>}
              </article>;
            })}
          </div> : <p className="trace-empty">本报告没有关联来源情报</p>
        ) : <p className="trace-empty">历史数据，暂无完整追踪信息</p>}
      </section>
      {regenerateOpen && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeRegenerateDialog(); }}>
        <section ref={regenerateDialogRef} className="dialog-panel report-create-dialog" role="dialog" aria-modal="true" aria-labelledby="report-regenerate-title" aria-describedby="report-regenerate-description">
          <div className="dialog-heading"><h2 id="report-regenerate-title">重新生成v{(report.versionNumber ?? 1) + 1}</h2><button aria-label="关闭" disabled={regenerate.isPending} onClick={closeRegenerateDialog}><X size={18} /></button></div>
          <label id="report-regenerate-description">调整要求<textarea data-autofocus maxLength={1000} rows={4} value={regenerateInstruction} onChange={(event) => setRegenerateInstruction(event.target.value)} placeholder="例如：压缩背景说明，重点比较分歧；留空则按默认方式重写。" /></label>
          <label className="report-change-only"><input type="checkbox" checked={regenerateChangesOnly} onChange={(event) => setRegenerateChangesOnly(event.target.checked)} />只写相较上一版的新变化</label>
          {regenerate.isError && <p className="dialog-error" role="alert">任务创建失败：{regenerate.error instanceof ApiError ? regenerate.error.message : "服务暂时不可用"}。调整要求已保留，可直接重试。</p>}
          <div className="dialog-actions"><button className="secondary-button" disabled={regenerate.isPending} onClick={closeRegenerateDialog}>取消</button><button className="primary-button" disabled={regenerate.isPending} onClick={() => regenerate.mutate()}>{regenerate.isPending ? "正在创建" : regenerate.isError ? "重试生成" : "开始生成"}</button></div>
        </section>
      </div>}
    </article>
  );
}
