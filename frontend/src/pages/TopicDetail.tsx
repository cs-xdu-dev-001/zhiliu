import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellOff, Bookmark, Pin, Radio, TrendingDown, TrendingUp } from "lucide-react";
import { Link, useParams } from "wouter";

import { api, ApiError } from "../api";
import { ItemCard } from "../components/ItemCard";
import type { TopicDetail, TopicSummary } from "../types";

const changeLabels = { first_appearance: "新出现", ongoing: "持续进展", important_update: "重要更新", duplicate_message: "重复消息", viewpoint_changed: "观点变化", information_invalid: "信息失效" } as const;

export function TopicDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["topic", id], queryFn: () => api.get<TopicDetail>(`/api/topics/${id}`) });
  const update = useMutation({ mutationFn: (patch: Record<string, boolean>) => api.patch<TopicSummary>(`/api/topics/${id}`, patch), onSuccess: () => { client.invalidateQueries({ queryKey: ["topic", id] }); client.invalidateQueries({ queryKey: ["topics"] }); } });
  if (query.isPending) return <div className="detail-skeleton" role="status" />;
  if (query.error instanceof ApiError && query.error.status === 404) return <div className="empty-state"><strong>主题不存在</strong><Link href="/topics">返回主题</Link></div>;
  if (!query.data) return <div className="inline-error">主题加载失败。<button onClick={() => query.refetch()}>重试</button></div>;
  const topic = { ...query.data, recentChanges: query.data.recentChanges ?? [], changeSummary: query.data.changeSummary ?? "近期暂无可确认的新变化" };
  return <article className="topic-detail">
    <header className="topic-hero"><div><span className={`topic-trend ${topic.trend}`}>{topic.trend === "rising" ? <TrendingUp size={17} /> : <TrendingDown size={17} />}{topic.trend === "rising" ? "正在升温" : topic.trend === "falling" ? "热度回落" : "信号平稳"}</span><h2>{topic.name}</h2><p>{topic.aliases.filter((name) => name !== topic.name).slice(0, 4).join(" · ") || "由情报关键词自动归集"}</p></div><div className="topic-actions"><button className={topic.isFollowed ? "active" : ""} onClick={() => update.mutate({ isFollowed: !topic.isFollowed })}><Bookmark size={17} />{topic.isFollowed ? "已关注" : "关注"}</button><button className={topic.isPinned ? "active" : ""} onClick={() => update.mutate({ isPinned: !topic.isPinned })}><Pin size={17} />{topic.isPinned ? "已置顶" : "置顶"}</button><button className={topic.isMuted ? "active" : ""} onClick={() => update.mutate({ isMuted: !topic.isMuted })}><BellOff size={17} />{topic.isMuted ? "已静音" : "静音"}</button></div></header>
    <div className="topic-metrics"><div><strong>{topic.itemCount7Days}</strong><span>近7天情报</span></div><div><strong>{topic.itemCount30Days}</strong><span>近30天情报</span></div><div><strong>{topic.sourceCount}</strong><span>独立来源</span></div><div><strong>{topic.previous7DaysCount}</strong><span>此前7天</span></div></div>
    <section className="topic-section topic-changes"><h2>相较历史的新变化</h2><p className="change-summary">{topic.changeSummary}</p>{topic.recentChanges.filter((change) => change.changeType !== "duplicate_message").slice(0, 6).map((change) => <Link className="change-row" key={change.id} href={`/items/${change.itemId}`}><span className={`change-marker ${change.changeType}`}>{changeLabels[change.changeType]}</span><strong>{String(change.after.title ?? `情报#${change.itemId}`)}</strong><span>{change.basis}</span></Link>)}</section>
    <section className="topic-section"><h2>最新情报</h2>{topic.latestItems.length ? <div className="feed-list">{topic.latestItems.map((item) => <ItemCard key={item.id} item={item} compact />)}</div> : <p className="trace-empty">暂无关联情报</p>}</section>
    {(topic.relatedBriefings.length > 0 || topic.relatedRuns.length > 0) && <div className="topic-related"><section className="topic-section"><h2>相关报告</h2>{topic.relatedBriefings.map((report) => <Link className="related-row" key={report.id} href={`/reports/${report.id}`}><strong>{report.title}</strong><span>{report.itemCount}条情报</span></Link>)}</section><section className="topic-section"><h2><Radio size={18} />微信与Hermes任务</h2>{topic.relatedRuns.map((run) => <Link className="related-row" key={run.id} href={`/tasks/${run.id}`}><strong>{run.requestSummary || run.topic || `任务#${run.id}`}</strong><span>{run.status === "success" ? "已完成" : run.status}</span></Link>)}</section></div>}
  </article>;
}
