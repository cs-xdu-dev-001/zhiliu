import { useQuery } from "@tanstack/react-query";
import { BookOpenText, FileSearch, Search, X } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "wouter";

import { api } from "../api";
import type { IntelligenceKind, SearchResponse } from "../types";

const kindNames: Record<IntelligenceKind, string> = { news: "热点", paper: "论文", job: "招聘" };

function summary(value: string) {
  const plain = value.replace(/[#*_>`-]/g, " ").replace(/\s+/g, " ").trim();
  return plain.length > 180 ? `${plain.slice(0, 180)}…` : plain;
}

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryText = searchParams.get("q")?.trim() ?? "";
  const kind = (searchParams.get("kind") ?? "") as IntelligenceKind | "";
  const days = searchParams.get("days") ?? "";
  const returnHref = `/search${searchParams.toString() ? `?${searchParams.toString()}` : ""}`;
  const [draft, setDraft] = useState(queryText);

  useEffect(() => setDraft(queryText), [queryText]);

  const query = useQuery({
    queryKey: ["search", queryText, kind, days],
    queryFn: () => api.get<SearchResponse>(`/api/search?${new URLSearchParams({ q: queryText, ...(kind ? { kind } : {}), ...(days ? { days } : {}) }).toString()}`),
    enabled: queryText.length >= 2,
  });

  function changeFilters(nextKind: string, nextDays: string) {
    if (queryText.length < 2) return;
    const params = new URLSearchParams({ q: queryText });
    if (nextKind) params.set("kind", nextKind);
    if (nextDays) params.set("days", nextDays);
    setSearchParams(params);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = draft.trim();
    if (value.length < 2) return;
    const params = new URLSearchParams({ q: value });
    if (kind) params.set("kind", kind);
    if (days) params.set("days", days);
    setSearchParams(params);
  }

  const total = (query.data?.itemTotal ?? 0) + (query.data?.briefingTotal ?? 0);
  return (
    <section className="search-page">
      <form className="global-search" role="search" onSubmit={submit}>
        <Search size={20} />
        <input autoFocus aria-label="搜索情报和报告" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="例如：过去30天Agent框架有哪些重要更新" />
        {draft && <button type="button" aria-label="清除搜索" onClick={() => setDraft("")}><X size={18} /></button>}
        <button className="primary-button" type="submit" disabled={draft.trim().length < 2}>搜索</button>
      </form>

      {queryText.length >= 2 && <div className="search-filter-row">
        <div>
          <select aria-label="内容类型" value={kind} onChange={(event) => changeFilters(event.target.value, days)}><option value="">全部类型</option><option value="news">热点</option><option value="paper">论文</option><option value="job">招聘</option></select>
          <select aria-label="时间范围" value={days} onChange={(event) => changeFilters(kind, event.target.value)}><option value="">全部时间</option><option value="7">最近7天</option><option value="30">最近30天</option><option value="90">最近90天</option><option value="365">最近一年</option></select>
        </div>
        {!query.isPending && !query.isError && <span>{total}条结果</span>}
      </div>}

      {!queryText && <div className="search-start"><FileSearch size={28} /><p>用一句话搜索Hermes写入的情报和报告。</p></div>}
      {queryText.length === 1 && <p className="inline-error">请至少输入2个字符。</p>}
      {queryText.length >= 2 && query.isPending && <div className="list-skeleton" aria-label="正在搜索"><i /><i /></div>}
      {query.isError && <div className="inline-error" role="alert">搜索失败。<button onClick={() => query.refetch()}>重新搜索</button></div>}
      {query.data && total === 0 && <div className="empty-state"><FileSearch size={24} /><strong>没有找到“{query.data.query}”</strong><p>换个说法，或扩大时间范围再试。</p></div>}

      {query.data && query.data.items.length > 0 && <section className="search-group">
        <h2>情报 <span>{query.data.itemTotal}</span></h2>
        <div className="search-results">{query.data.items.map((item) => <Link key={item.id} href={`/items/${item.id}?from=${encodeURIComponent(returnHref)}`} className="search-result">
          <div className="search-result-meta"><span>{kindNames[item.kind]}</span><span>{item.source || "未知来源"}</span><time>{new Date(item.createdAt).toLocaleDateString("zh-CN")}</time></div>
          <h3>{item.title}</h3><p>{summary(item.summary)}</p>
        </Link>)}</div>
      </section>}

      {query.data && query.data.briefings.length > 0 && <section className="search-group">
        <h2><BookOpenText size={18} />报告 <span>{query.data.briefingTotal}</span></h2>
        <div className="search-results">{query.data.briefings.map((report) => <Link key={report.id} href={`/reports/${report.id}?from=${encodeURIComponent(returnHref)}`} className="search-result">
          <div className="search-result-meta"><span>{kindNames[report.kind]}</span><span>{report.itemCount}条来源情报</span><time>{new Date(report.createdAt).toLocaleDateString("zh-CN")}</time></div>
          <h3>{report.title}</h3><p>{summary(report.summary)}</p>
        </Link>)}</div>
      </section>}
    </section>
  );
}
