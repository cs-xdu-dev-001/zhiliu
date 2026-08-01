import { Bookmark, Check, ExternalLink, EyeOff } from "lucide-react";

import type { IntelligenceItem } from "../types";

const kindLabels = { news: "热点", paper: "论文", job: "招聘" };

export function ItemCard({
  item,
  onChange,
  compact = false,
}: {
  item: IntelligenceItem;
  onChange?: (patch: Partial<Pick<IntelligenceItem, "isRead" | "isSaved" | "isIgnored">>) => void;
  compact?: boolean;
}) {
  const date = item.publishedAt ?? item.createdAt;
  return (
    <article className={`item-card ${item.isRead ? "read" : ""} ${compact ? "compact" : ""}`}>
      <div className="item-meta">
        <span className={`kind-tag ${item.kind}`}>{kindLabels[item.kind]}</span>
        <span>{item.source}</span>
        <time dateTime={date}>{new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(new Date(date))}</time>
        <span className="importance">{Math.round(item.importance * 100)}</span>
      </div>
      <h2>{item.title}</h2>
      <p className="item-summary">{item.summary}</p>
      {!compact && <p className="item-reason"><strong>值得关注：</strong>{item.reason}</p>}
      <div className="item-footer">
        <div className="keyword-row">{item.keywords.slice(0, 3).map((keyword) => <span key={keyword}>{keyword}</span>)}</div>
        <div className="item-actions">
          {onChange && <>
            <button className={item.isSaved ? "selected" : ""} onClick={() => onChange({ isSaved: !item.isSaved })} aria-label={item.isSaved ? "取消收藏" : "收藏"} title={item.isSaved ? "取消收藏" : "收藏"}><Bookmark size={17} fill={item.isSaved ? "currentColor" : "none"} /></button>
            <button onClick={() => onChange({ isRead: !item.isRead })} aria-label={item.isRead ? "标记未读" : "标记已读"} title={item.isRead ? "标记未读" : "标记已读"}><Check size={17} /></button>
            <button onClick={() => onChange({ isIgnored: true })} aria-label="忽略" title="忽略"><EyeOff size={17} /></button>
          </>}
          <a href={item.url} target="_blank" rel="noreferrer" aria-label="打开原文" title="打开原文"><ExternalLink size={17} /></a>
        </div>
      </div>
    </article>
  );
}

