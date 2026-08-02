import { Bookmark, Check, ExternalLink, EyeOff } from "lucide-react";
import { Link } from "wouter";

import type { IntelligenceItem } from "../types";

const kindLabels = { news: "热点", paper: "论文", job: "招聘" };

function importanceLabel(importance: number) {
  if (importance >= 0.8) return "高优先级";
  if (importance >= 0.55) return "中优先级";
  return "低优先级";
}

export function ItemCard({
  item,
  onChange,
  compact = false,
  busy = false,
  detailHref = `/items/${item.id}`,
}: {
  item: IntelligenceItem;
  onChange?: (patch: Partial<Pick<IntelligenceItem, "isRead" | "isSaved" | "isIgnored">>) => void;
  compact?: boolean;
  busy?: boolean;
  detailHref?: string;
}) {
  const date = item.publishedAt ?? item.createdAt;
  const importance = Math.round(item.importance * 100);
  const priority = importanceLabel(item.importance);
  return (
    <article className={`item-card ${item.isRead ? "read" : ""} ${compact ? "compact" : ""}`}>
      <Link className="item-card-link" href={detailHref}>
        <div className="item-meta">
          <span className={`kind-tag ${item.kind}`}>{kindLabels[item.kind]}</span>
          <span>{item.source}</span>
          <time dateTime={date}>{new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(new Date(date))}</time>
          {item.isRead && <span className="read-state">已读</span>}
          <span className="importance" aria-label={`${priority}，重要性${importance}分`}>{priority}</span>
        </div>
        <h2>{item.title}</h2>
        <p className="item-summary">{item.summary || item.reason || "暂无摘要"}</p>
        <span className="card-detail-cue">查看详情</span>
      </Link>
      <div className="item-footer">
        <div className="keyword-row">{item.keywords.slice(0, 3).map((keyword) => <span key={keyword}>{keyword}</span>)}</div>
        <div className="item-actions">
          {onChange && <>
            <button disabled={busy} className={item.isSaved ? "selected" : ""} onClick={() => onChange({ isSaved: !item.isSaved })} aria-label={item.isSaved ? "取消收藏" : "收藏"} title={item.isSaved ? "取消收藏" : "收藏"}><Bookmark size={17} fill={item.isSaved ? "currentColor" : "none"} /></button>
            <button disabled={busy} onClick={() => onChange({ isRead: !item.isRead })} aria-label={item.isRead ? "标记未读" : "标记已读"} title={item.isRead ? "标记未读" : "标记已读"}><Check size={17} /></button>
            <button disabled={busy} onClick={() => onChange({ isIgnored: true })} aria-label="忽略" title="忽略"><EyeOff size={17} /></button>
          </>}
          <a href={item.url} target="_blank" rel="noreferrer" aria-label="打开原文（新窗口）" title="打开原文"><ExternalLink size={17} /></a>
        </div>
      </div>
    </article>
  );
}
