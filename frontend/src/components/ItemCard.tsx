import { Bookmark, Check, ExternalLink, EyeOff } from "lucide-react";
import { Link } from "wouter";

import type { IntelligenceItem } from "../types";

const kindLabels = { news: "热点", paper: "论文", job: "招聘" };
const changeLabels = { first_appearance: "新出现", ongoing: "持续进展", important_update: "重要更新", duplicate_message: "重复消息", viewpoint_changed: "观点变化", information_invalid: "信息失效" } as const;

function importanceLabel(importance: number) {
  if (importance >= 0.8) return "高优先级";
  if (importance >= 0.55) return "中优先级";
  return "低优先级";
}

function safeExternalUrl(value: string) {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? value : null;
  } catch {
    return null;
  }
}

export function ItemCard({
  item,
  onChange,
  compact = false,
  busy = false,
  detailHref = `/items/${item.id}`,
  selectable = false,
  selected = false,
  onSelect,
}: {
  item: IntelligenceItem;
  onChange?: (patch: Partial<Pick<IntelligenceItem, "isRead" | "isSaved" | "isIgnored">>) => void;
  compact?: boolean;
  busy?: boolean;
  detailHref?: string;
  selectable?: boolean;
  selected?: boolean;
  onSelect?: (selected: boolean) => void;
}) {
  const date = item.publishedAt ?? item.createdAt;
  const effectiveImportance = item.personalizedScore ?? item.importance;
  const importance = Math.round(effectiveImportance * 100);
  const priority = importanceLabel(effectiveImportance);
  const sourceUrl = item.sourceUnavailable ? null : safeExternalUrl(item.url);
  const sourceLabel = item.source.trim() || "来源未标注";
  return (
    <article className={`item-card ${item.isRead ? "read" : ""} ${compact ? "compact" : ""} ${selectable ? "selectable" : ""} ${selected ? "selected" : ""}`}>
      {selectable && <label className="item-select-control"><input type="checkbox" checked={selected} disabled={busy} onChange={(event) => onSelect?.(event.target.checked)} aria-label={`选择${item.title}`} /><span>{selected ? "已选择" : "选择"}</span></label>}
      <Link className="item-card-link" href={detailHref}>
        <div className="item-meta">
          <span className={`kind-tag ${item.kind}`}>{kindLabels[item.kind]}</span>
          {item.mergedIntoId !== null ? <span className="invalid-tag">已合并</span> : item.isInvalid && <span className="invalid-tag">无效</span>}
          {item.isStale && !item.isInvalid && item.mergedIntoId === null && <span className="stale-tag">可能过期</span>}
          {item.sourceUnavailable && <span className="source-failed-tag">原文失效</span>}
          {item.latestChangeType && item.latestChangeType !== "duplicate_message" && <span className={`change-marker ${item.latestChangeType}`}>{changeLabels[item.latestChangeType]}</span>}
          <span>{sourceLabel}</span>
          <time dateTime={date}>{new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(new Date(date))}</time>
          {item.isRead && <span className="read-state">已读</span>}
          <span className="importance" aria-label={`${priority}，重要性${importance}分`}>{priority}</span>
        </div>
        <h2>{item.title}</h2>
        <p className="item-summary">{item.summary || item.reason || "暂无摘要"}</p>
        {effectiveImportance >= .8 && item.recommendationReasons?.[0] && <span className="recommendation-cue">推荐理由：{item.recommendationReasons[0].text}</span>}
        {!selectable && <span className="card-detail-cue">查看详情</span>}
      </Link>
      {!compact && <div className="item-footer">
          <div className="keyword-row">{item.topics?.length ? item.topics.slice(0, 3).map((topic) => <Link key={topic.id} href={`/topics/${topic.id}`}>{topic.name}</Link>) : (item.tags?.length ? item.tags : item.keywords).slice(0, 3).map((keyword) => <span className={item.tags?.length ? "item-tag" : undefined} key={keyword}>{keyword}</span>)}</div>
          <div className="item-actions">
            {onChange && <>
              <button disabled={busy} className={item.isSaved ? "selected" : ""} aria-pressed={item.isSaved} onClick={() => onChange({ isSaved: !item.isSaved })} aria-label={item.isSaved ? "取消收藏" : "收藏"} title={item.isSaved ? "取消收藏" : "收藏"}><Bookmark size={17} fill={item.isSaved ? "currentColor" : "none"} /><span className="action-text" aria-hidden="true">{item.isSaved ? "已收藏" : "收藏"}</span></button>
              <button disabled={busy} className={item.isRead ? "selected" : ""} aria-pressed={item.isRead} onClick={() => onChange({ isRead: !item.isRead })} aria-label={item.isRead ? "标记未读" : "标记已读"} title={item.isRead ? "标记未读" : "标记已读"}><Check size={17} /><span className="action-text" aria-hidden="true">已读</span></button>
              <button disabled={busy} className={item.isIgnored ? "selected" : ""} aria-pressed={item.isIgnored} onClick={() => onChange({ isIgnored: !item.isIgnored })} aria-label={item.isIgnored ? "取消忽略" : "忽略"} title={item.isIgnored ? "取消忽略" : "忽略"}><EyeOff size={17} /><span className="action-text" aria-hidden="true">{item.isIgnored ? "已忽略" : "忽略"}</span></button>
            </>}
            {sourceUrl
              ? <a href={sourceUrl} target="_blank" rel="noreferrer" aria-label="打开原文（新窗口）" title="打开原文"><ExternalLink size={17} /><span className="action-text" aria-hidden="true">原文</span></a>
              : <span className="unavailable" aria-label={item.sourceUnavailable ? "原文已标记失效" : "原文链接不可用"} title={item.sourceUnavailable ? "原文已标记失效" : "原文链接不可用"}><ExternalLink size={17} /><span className="action-text" aria-hidden="true">无原文</span></span>}
          </div>
        </div>}
    </article>
  );
}
