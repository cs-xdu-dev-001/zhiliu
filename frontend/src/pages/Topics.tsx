import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowRight, ArrowUpRight, Search, Tags } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link, useSearchParams } from "wouter";

import { api } from "../api";
import type { TopicPage, TopicSummary } from "../types";

const trend = {
  rising: { label: "升温", icon: ArrowUpRight },
  steady: { label: "平稳", icon: ArrowRight },
  falling: { label: "回落", icon: ArrowDownRight },
};

function TopicCard({ topic }: { topic: TopicSummary }) {
  const TrendIcon = trend[topic.trend].icon;
  return <Link className="topic-card" href={`/topics/${topic.id}`}>
    <div className="topic-card-head"><span className={`topic-trend ${topic.trend}`}><TrendIcon size={16} />{trend[topic.trend].label}</span>{topic.isPinned && <span>置顶</span>}{topic.isFollowed && <span>关注中</span>}{topic.isMuted && <span>已静音</span>}</div>
    <h2>{topic.name}</h2>
    <div className="topic-signal"><strong>{topic.itemCount7Days}</strong><span>近7天</span><strong>{topic.itemCount30Days}</strong><span>近30天</span><strong>{topic.sourceCount}</strong><span>来源</span></div>
  </Link>;
}

export function Topics() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const state = params.get("state") ?? "";
  const [draft, setDraft] = useState(q);
  const query = useQuery({ queryKey: ["topics", q, state], queryFn: () => api.get<TopicPage>(`/api/topics?${new URLSearchParams({ ...(q ? { q } : {}), ...(state ? { state } : {}) }).toString()}`) });
  function submit(event: FormEvent) { event.preventDefault(); const next = new URLSearchParams(); if (draft.trim()) next.set("q", draft.trim()); if (state) next.set("state", state); setParams(next); }
  function filter(nextState: string) { const next = new URLSearchParams(); if (q) next.set("q", q); if (nextState) next.set("state", nextState); setParams(next); }
  return <section className="topics-page">
    <div className="topic-toolbar"><form role="search" onSubmit={submit}><Search size={18} /><input aria-label="搜索主题" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="搜索主题或别名" /></form><div className="segment-control" aria-label="主题筛选"><button className={!state ? "active" : ""} onClick={() => filter("")}>全部</button><button className={state === "followed" ? "active" : ""} onClick={() => filter("followed")}>关注</button><button className={state === "pinned" ? "active" : ""} onClick={() => filter("pinned")}>置顶</button></div></div>
    {query.isPending && <div className="list-skeleton"><i /><i /><i /></div>}
    {query.isError && <div className="inline-error" role="alert">主题加载失败。<button onClick={() => query.refetch()}>重试</button></div>}
    {query.data?.items.length === 0 && <div className="empty-state"><Tags size={24} /><strong>暂无匹配主题</strong><p>Hermes写入带关键词的情报后，主题会自动出现。</p></div>}
    <div className="topic-grid">{query.data?.items.map((topic) => <TopicCard key={topic.id} topic={topic} />)}</div>
  </section>;
}
