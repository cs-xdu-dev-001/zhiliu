import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bookmark, Check, CircleX, ExternalLink, FileText, GitBranch, History, Merge, Pencil, RefreshCw, X } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link, useParams, useSearchParams } from "wouter";

import { api, ApiError } from "../api";
import type { IntelligenceItem, IntelligenceItemDetail, IntelligenceKind, ItemRevision, MergeCandidate } from "../types";

const kindLabels = { news: "热点", paper: "论文", job: "招聘" };
const revisionLabels: Record<ItemRevision["action"], string> = {
  edited: "编辑内容",
  invalidated: "标记无效",
  restored: "恢复有效",
  merged: "合并到其他情报",
  merge_target: "接收重复情报",
};

function safeBackHref(value: string | null) {
  if (!value?.startsWith("/")) return "/feed";
  try {
    const target = new URL(value, window.location.origin);
    return target.origin === window.location.origin
      ? `${target.pathname}${target.search}${target.hash}`
      : "/feed";
  } catch {
    return "/feed";
  }
}

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : "操作未完成，请重试";
}

function revisionChanges(revision: ItemRevision) {
  if (revision.action === "invalidated") return "该情报已从正常列表移除";
  if (revision.action === "restored") return "该情报已恢复到正常列表";
  if (revision.action === "merged") return `保留记录：情报#${String(revision.after?.mergedIntoId ?? "-")}`;
  if (revision.action === "merge_target") return `并入情报#${String(revision.after?.absorbedItemId ?? "-")}`;
  const labels: Record<string, string> = { title: "标题", summary: "摘要", kind: "分类" };
  return Object.keys(labels)
    .filter((key) => revision.before?.[key] !== revision.after?.[key])
    .map((key) => `${labels[key]}：${String(revision.before?.[key] ?? "")} → ${String(revision.after?.[key] ?? "")}`)
    .join("；") || "内容已更新";
}

export function ItemDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeTargetId, setMergeTargetId] = useState<number | null>(null);
  const [form, setForm] = useState({ title: "", summary: "", kind: "news" as IntelligenceKind });
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  const query = useQuery({
    queryKey: ["item", id],
    queryFn: () => api.get<IntelligenceItemDetail>(`/api/items/${id}`),
  });
  const candidates = useQuery({
    queryKey: ["item", id, "merge-candidates"],
    queryFn: () => api.get<MergeCandidate[]>(`/api/items/${id}/merge-candidates`),
    enabled: mergeOpen,
  });
  const refreshItem = () => {
    queryClient.invalidateQueries({ queryKey: ["item", id] });
    queryClient.invalidateQueries({ queryKey: ["items"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    queryClient.invalidateQueries({ queryKey: ["briefings"] });
    queryClient.invalidateQueries({ queryKey: ["traces"] });
  };
  const update = useMutation({
    mutationFn: (patch: Partial<Pick<IntelligenceItem, "isRead" | "isSaved" | "isIgnored">>) =>
      api.patch<IntelligenceItem>(`/api/items/${id}`, patch),
    onSuccess: (item) => {
      queryClient.setQueryData<IntelligenceItemDetail>(["item", id], (current) => current ? { ...current, ...item } : current);
      queryClient.invalidateQueries({ queryKey: ["items"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  const edit = useMutation({
    mutationFn: () => api.patch<IntelligenceItem>(`/api/items/${id}/content`, form),
    onSuccess: () => {
      setEditOpen(false);
      setNotice({ tone: "success", text: "内容已更新，修改记录已保留" });
      refreshItem();
    },
  });
  const validity = useMutation({
    mutationFn: (invalid: boolean) => api.put<IntelligenceItem>(`/api/items/${id}/validity`, { invalid }),
    onSuccess: (next) => {
      setNotice({ tone: "success", text: next.isInvalid ? "已标记无效" : "已恢复有效" });
      refreshItem();
    },
  });
  const merge = useMutation({
    mutationFn: (targetId: number) => api.post(`/api/items/${id}/merge`, { targetId }),
    onSuccess: () => {
      setMergeOpen(false);
      setMergeTargetId(null);
      setNotice({ tone: "success", text: "重复情报已合并，引用关系已转移" });
      refreshItem();
    },
  });
  const rerun = useMutation({
    mutationFn: (subscriptionId: number) => api.post(`/api/subscriptions/${subscriptionId}/run`),
    onSuccess: () => setNotice({ tone: "success", text: "已交给Hermes重新整理，可在任务记录查看进度" }),
  });
  const backHref = safeBackHref(searchParams.get("from"));

  if (query.isPending) return <div className="detail-skeleton" role="status" aria-label="正在加载情报" />;
  if (query.error instanceof ApiError && query.error.status === 404) {
    return <div className="empty-state"><p>情报不存在或已删除</p><Link className="secondary-link" href={backHref}>返回情报列表</Link></div>;
  }
  if (query.isError) return <div className="inline-error" role="alert">情报加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>;

  const item = query.data;
  const date = item.publishedAt ?? item.createdAt;
  const merged = item.mergedIntoId !== null;
  const subscriptionOrigin = item.publications.some((publication) => publication.origin === "subscription-hermes");
  const busy = update.isPending || edit.isPending || validity.isPending || merge.isPending || rerun.isPending;

  function openEditor() {
    setForm({ title: item.title, summary: item.summary, kind: item.kind });
    edit.reset();
    setEditOpen(true);
  }

  function submitEdit(event: FormEvent) {
    event.preventDefault();
    edit.mutate();
  }

  return (
    <article className="detail-page">
      <Link className="detail-back" href={backHref}><ArrowLeft size={17} />返回情报列表</Link>
      {(item.isInvalid || item.mergedInto) && (
        <div className={`correction-banner ${item.mergedInto ? "merged" : "invalid"}`} role="status">
          {item.mergedInto
            ? <>这条情报已并入<Link href={`/items/${item.mergedInto.id}`}>{item.mergedInto.title}</Link>，当前页面仅保留审计记录。</>
            : "这条情报已标记无效，不再进入正常情报列表和统计。"}
        </div>
      )}
      <div className="detail-copy">
        <div className="detail-meta">
          <span className={`kind-tag ${item.kind}`}>{kindLabels[item.kind]}</span>
          {item.isInvalid && <span className="invalid-tag">无效</span>}
          <span>{item.source}</span>
          <time dateTime={date}>{new Date(date).toLocaleString("zh-CN")}</time>
          <span>{Math.round(item.importance * 100)}分</span>
        </div>
        <h2>{item.title}</h2>
        <p className="detail-summary">{item.summary || "暂无摘要"}</p>
        <section className="detail-reason" aria-labelledby="reason-heading">
          <h3 id="reason-heading">值得关注</h3>
          <p>{item.reason || "暂无补充判断"}</p>
        </section>
        <div className="keyword-row">{item.keywords.map((keyword) => <span key={keyword}>{keyword}</span>)}</div>
      </div>

      <section className="maintenance-section" aria-labelledby="maintenance-heading">
        <div className="lineage-heading"><Pencil size={19} /><h2 id="maintenance-heading">内容维护</h2></div>
        <div className="maintenance-actions">
          <button disabled={busy || merged} onClick={openEditor}><Pencil size={17} />编辑内容</button>
          <button disabled={busy || merged} onClick={() => validity.mutate(!item.isInvalid)}><CircleX size={17} />{item.isInvalid ? "恢复有效" : "标记无效"}</button>
          <button disabled={busy || merged} onClick={() => { setMergeTargetId(null); merge.reset(); setMergeOpen(true); }}><Merge size={17} />合并重复</button>
          {subscriptionOrigin && item.subscriptionId > 0 && <button disabled={busy || merged} onClick={() => rerun.mutate(item.subscriptionId)}><RefreshCw size={17} />重新整理</button>}
        </div>
        {!subscriptionOrigin && !merged && <p className="maintenance-guidance">微信Hermes内容需回到微信重新发起，避免知流重复调用Hermes。</p>}
      </section>

      <section className="lineage-section" aria-labelledby="lineage-heading">
        <div className="lineage-heading"><GitBranch size={19} /><h2 id="lineage-heading">写入记录</h2></div>
        {item.traceAvailable ? (
          <div className="publication-list">
            {item.publications.map((publication, index) => (
              <div className="publication-row" key={publication.id}>
                <div className="publication-row-main">
                  <strong>{publication.requestSummary}</strong>
                  <div className="lineage-meta">
                    <span>{index === 0 && publication.wasInserted ? "首次写入" : "再次引用"}</span>
                    <span>{publication.origin === "weixin-hermes" ? "微信Hermes" : "定时订阅"}</span>
                    <time dateTime={publication.createdAt}>{new Date(publication.createdAt).toLocaleString("zh-CN")}</time>
                  </div>
                </div>
                <div className="lineage-links">
                  {publication.briefingId && publication.briefingTitle && <Link href={`/reports/${publication.briefingId}`}><FileText size={16} />{publication.briefingTitle}</Link>}
                  <Link href={`/traces/${publication.id}`}>查看完整链路</Link>
                </div>
              </div>
            ))}
          </div>
        ) : <p className="trace-empty">历史数据，暂无完整追踪信息</p>}
      </section>

      <section className="lineage-section" aria-labelledby="revision-heading">
        <div className="lineage-heading"><History size={19} /><h2 id="revision-heading">修改记录</h2></div>
        {item.revisions.length > 0 ? (
          <div className="revision-list">
            {item.revisions.map((revision) => (
              <div className="revision-row" key={revision.id}>
                <strong>{revisionLabels[revision.action] ?? revision.action}</strong>
                <p>{revisionChanges(revision)}</p>
                <time dateTime={revision.createdAt}>{new Date(revision.createdAt).toLocaleString("zh-CN")}</time>
              </div>
            ))}
          </div>
        ) : <p className="trace-empty">尚未人工修改</p>}
      </section>

      {(notice || update.isError || validity.isError || rerun.isError) && (
        <div className={`action-notice ${notice?.tone ?? "error"}`} role={notice?.tone === "success" ? "status" : "alert"}>
          {notice?.text ?? errorText(update.error ?? validity.error ?? rerun.error)}
        </div>
      )}
      <div className="detail-actions">
        <button disabled={busy || merged} onClick={() => update.mutate({ isSaved: !item.isSaved })}><Bookmark size={17} fill={item.isSaved ? "currentColor" : "none"} />{item.isSaved ? "取消收藏" : "收藏"}</button>
        <button disabled={busy || merged} onClick={() => update.mutate({ isRead: !item.isRead })}><Check size={17} />{item.isRead ? "标记未读" : "标记已读"}</button>
        <button disabled={busy || merged} onClick={() => update.mutate({ isIgnored: true })}><CircleX size={17} />忽略</button>
        <a className="primary-compact" href={item.url} target="_blank" rel="noreferrer"><ExternalLink size={17} />打开原文（新窗口）</a>
      </div>

      {editOpen && (
        <div className="dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setEditOpen(false)}>
          <section className="dialog-panel" role="dialog" aria-modal="true" aria-labelledby="edit-dialog-title" onKeyDown={(event) => event.key === "Escape" && setEditOpen(false)}>
            <div className="dialog-heading"><h2 id="edit-dialog-title">编辑情报</h2><button className="icon-button" aria-label="关闭" onClick={() => setEditOpen(false)}><X size={20} /></button></div>
            <form className="correction-form" onSubmit={submitEdit}>
              <label className="form-field"><span>标题</span><input autoFocus required maxLength={300} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
              <label className="form-field"><span>摘要</span><textarea required maxLength={5000} rows={7} value={form.summary} onChange={(event) => setForm({ ...form, summary: event.target.value })} /></label>
              <label className="form-field"><span>分类</span><select value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as IntelligenceKind })}><option value="news">热点</option><option value="paper">论文</option><option value="job">招聘</option></select></label>
              {edit.isError && <div className="action-notice error" role="alert">{errorText(edit.error)}</div>}
              <div className="dialog-actions"><button type="button" className="secondary-button" onClick={() => setEditOpen(false)}>取消</button><button className="primary-button" disabled={edit.isPending}>{edit.isPending ? "正在保存" : "保存修改"}</button></div>
            </form>
          </section>
        </div>
      )}

      {mergeOpen && (
        <div className="dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setMergeOpen(false)}>
          <section className="dialog-panel" role="dialog" aria-modal="true" aria-labelledby="merge-dialog-title" onKeyDown={(event) => event.key === "Escape" && setMergeOpen(false)}>
            <div className="dialog-heading"><h2 id="merge-dialog-title">合并重复情报</h2><button className="icon-button" aria-label="关闭" onClick={() => setMergeOpen(false)}><X size={20} /></button></div>
            <p className="merge-guidance">选择要保留的情报。当前记录仍用于审计，报告和写入链路会转移到保留项。</p>
            {candidates.isPending && <div className="list-skeleton"><i /><i /></div>}
            {candidates.isError && <div className="inline-error" role="alert">候选情报加载失败。<button onClick={() => candidates.refetch()}>重新加载</button></div>}
            {candidates.data?.length === 0 && <div className="empty-state"><p>没有同分类的可合并情报</p></div>}
            <div className="merge-candidate-list">
              {candidates.data?.map((candidate) => (
                <label className={`merge-candidate ${mergeTargetId === candidate.id ? "selected" : ""}`} key={candidate.id}>
                  <input type="radio" name="merge-target" checked={mergeTargetId === candidate.id} onChange={() => setMergeTargetId(candidate.id)} aria-label={`${candidate.title}，${candidate.source}`} />
                  <span><strong>{candidate.title}</strong><p>{candidate.summary || "暂无摘要"}</p><small>{candidate.source} · 相似度{Math.round(candidate.similarity * 100)}%</small></span>
                </label>
              ))}
            </div>
            {merge.isError && <div className="action-notice error" role="alert">{errorText(merge.error)}</div>}
            <div className="dialog-actions"><button className="secondary-button" onClick={() => setMergeOpen(false)}>取消</button><button className="primary-button" disabled={!mergeTargetId || merge.isPending} onClick={() => mergeTargetId && merge.mutate(mergeTargetId)}>{merge.isPending ? "正在合并" : "确认合并"}</button></div>
          </section>
        </div>
      )}
    </article>
  );
}
