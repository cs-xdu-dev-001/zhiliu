import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "wouter";

import { api } from "../api";
import { BriefingCard } from "../components/BriefingCard";
import { EmptyState } from "../components/EmptyState";
import type { BriefingPage, IntelligenceKind } from "../types";

const PAGE_SIZE = 20;
const kinds: { value: IntelligenceKind | ""; label: string }[] = [
  { value: "", label: "全部" },
  { value: "news", label: "热点" },
  { value: "paper", label: "论文" },
  { value: "job", label: "招聘" },
];
const allowedKinds = new Set<string>(kinds.map((kind) => kind.value));
const allowedPeriods = new Set<string>(["", "7", "30"]);

export function Reports() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawKind = searchParams.get("kind") ?? "";
  const rawPeriod = searchParams.get("days") ?? "";
  const rawPage = Number(searchParams.get("page") ?? "1");
  const kind = allowedKinds.has(rawKind) ? rawKind : "";
  const period = allowedPeriods.has(rawPeriod) ? rawPeriod : "";
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1;
  const q = (searchParams.get("q") ?? "").slice(0, 200);
  const [searchDraft, setSearchDraft] = useState(q);

  function setView(next: { kind?: string; period?: string; q?: string; page?: number }) {
    const values = {
      kind: next.kind ?? kind,
      period: next.period ?? period,
      q: next.q ?? q,
      page: next.page ?? page,
    };
    const params = new URLSearchParams();
    if (values.kind) params.set("kind", values.kind);
    if (values.period) params.set("days", values.period);
    if (values.q) params.set("q", values.q);
    if (values.page > 1) params.set("page", String(values.page));
    setSearchParams(params, { replace: true });
  }

  useEffect(() => setSearchDraft(q), [q]);
  useEffect(() => {
    const nextQ = searchDraft.trim().slice(0, 200);
    if (nextQ === q) return;
    const timer = window.setTimeout(() => setView({ q: nextQ, page: 1 }), 300);
    return () => window.clearTimeout(timer);
  }, [searchDraft, q, kind, period]);

  const requestParams = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String((page - 1) * PAGE_SIZE) });
  if (kind) requestParams.set("kind", kind);
  if (period) requestParams.set("days", period);
  if (q) requestParams.set("q", q);
  const query = useQuery({
    queryKey: ["briefings", kind, period, q, page],
    queryFn: () => api.get<BriefingPage>(`/api/briefings?${requestParams.toString()}`),
  });
  const totalPages = Math.max(1, Math.ceil((query.data?.total ?? 0) / PAGE_SIZE));
  useEffect(() => {
    if (query.data && page > totalPages) setView({ page: totalPages });
  }, [page, query.data, totalPages]);
  const returnHref = `/reports${searchParams.toString() ? `?${searchParams.toString()}` : ""}`;
  const hasFilters = Boolean(kind || period || q);

  function clearFilters() {
    setSearchDraft("");
    setView({ kind: "", period: "", q: "", page: 1 });
  }

  return <section className="stack-lg">
    <div className="report-tools">
      <label className="feed-search"><Search size={18} /><input type="search" aria-label="搜索报告" placeholder="搜索报告标题或正文" maxLength={200} value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} />{searchDraft && <button aria-label="清除报告搜索" onClick={() => setSearchDraft("")}><X size={17} /></button>}</label>
      <select aria-label="报告时间" value={period} onChange={(event) => setView({ period: event.target.value, page: 1 })}><option value="">全部时间</option><option value="7">最近7天</option><option value="30">最近30天</option></select>
    </div>
    <div className="report-filter-row">
      <div className="segmented" aria-label="报告分类">{kinds.map((item) => <button key={item.value} aria-pressed={kind === item.value} className={kind === item.value ? "active" : ""} onClick={() => setView({ kind: item.value, page: 1 })}>{item.label}</button>)}</div>
      <span>{query.data ? `${query.data.total}份报告` : "正在同步"}{q ? ` · 搜索“${q}”` : ""}</span>
    </div>
    {query.isPending && <div className="list-skeleton"><i /><i /><i /></div>}
    {query.isError && <div className="inline-error" role="alert">报告加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>}
    {query.data?.items.length === 0 && (hasFilters
      ? <EmptyState title={q ? `没有找到“${q}”相关的报告` : "当前筛选下没有报告"} description="可以调整关键词、分类或时间范围后再试。" action={<button className="text-button" onClick={clearFilters}>清除筛选</button>} />
      : <EmptyState title="还没有报告" description="在微信让Hermes将内容整理到知流并生成简报，结果会显示在这里。" action={<Link className="secondary-link" href="/">查看示例指令</Link>} />)}
    <div className="briefing-list">
      {query.data?.items.map((briefing) => <BriefingCard key={briefing.id} briefing={briefing} detailHref={`/reports/${briefing.id}?from=${encodeURIComponent(returnHref)}`} />)}
    </div>
    {query.data && query.data.total > PAGE_SIZE && <nav className="pagination" aria-label="报告分页"><button disabled={page <= 1} onClick={() => setView({ page: page - 1 })}><ChevronLeft size={17} />上一页</button><span>第{page}/{totalPages}页</span><button disabled={page >= totalPages} onClick={() => setView({ page: page + 1 })}>下一页<ChevronRight size={17} /></button></nav>}
  </section>;
}
