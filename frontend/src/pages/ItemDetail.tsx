import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bookmark, Check, ExternalLink, EyeOff } from "lucide-react";
import { Link, useParams, useSearchParams } from "wouter";

import { api, ApiError } from "../api";
import type { IntelligenceItem } from "../types";

const kindLabels = { news: "热点", paper: "论文", job: "招聘" };

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

export function ItemDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["item", id],
    queryFn: () => api.get<IntelligenceItem>(`/api/items/${id}`),
  });
  const update = useMutation({
    mutationFn: (patch: Partial<Pick<IntelligenceItem, "isRead" | "isSaved" | "isIgnored">>) =>
      api.patch<IntelligenceItem>(`/api/items/${id}`, patch),
    onSuccess: (item) => {
      queryClient.setQueryData(["item", id], item);
      queryClient.invalidateQueries({ queryKey: ["items"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  const backHref = safeBackHref(searchParams.get("from"));

  if (query.isPending) return <div className="detail-skeleton" role="status" aria-label="正在加载情报" />;
  if (query.error instanceof ApiError && query.error.status === 404) {
    return <div className="empty-state"><p>情报不存在或已删除</p><Link className="secondary-link" href={backHref}>返回情报列表</Link></div>;
  }
  if (query.isError) return <div className="inline-error" role="alert">情报加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>;

  const item = query.data;
  const date = item.publishedAt ?? item.createdAt;
  const busy = update.isPending;

  return (
    <article className="detail-page">
      <Link className="detail-back" href={backHref}><ArrowLeft size={17} />返回情报列表</Link>
      <div className="detail-copy">
        <div className="detail-meta">
          <span className={`kind-tag ${item.kind}`}>{kindLabels[item.kind]}</span>
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
      {update.isError && <div className="action-notice error" role="alert">操作未完成，请重试</div>}
      <div className="detail-actions">
        <button disabled={busy} onClick={() => update.mutate({ isSaved: !item.isSaved })}><Bookmark size={17} fill={item.isSaved ? "currentColor" : "none"} />{item.isSaved ? "取消收藏" : "收藏"}</button>
        <button disabled={busy} onClick={() => update.mutate({ isRead: !item.isRead })}><Check size={17} />{item.isRead ? "标记未读" : "标记已读"}</button>
        <button disabled={busy} onClick={() => update.mutate({ isIgnored: true })}><EyeOff size={17} />忽略</button>
        <a className="primary-compact" href={item.url} target="_blank" rel="noreferrer"><ExternalLink size={17} />打开原文（新窗口）</a>
      </div>
    </article>
  );
}
