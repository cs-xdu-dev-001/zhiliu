import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bookmark, CheckCheck, ChevronLeft, ChevronRight, CircleX, EyeOff, FileText, ListChecks, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation, useSearchParams } from "wouter";

import { api, ApiError } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ItemCard } from "../components/ItemCard";
import type { BulkItemAction, IntelligenceItem, ItemBulkResult, ItemPage, TaskRun } from "../types";
import { useModalDialog } from "../useModalDialog";

const PAGE_SIZE = 20;
const categories = [
  { value: "", label: "全部" },
  { value: "news", label: "热点" },
  { value: "paper", label: "论文" },
  { value: "job", label: "招聘" },
];
const sortOptions = [
  { value: "importance", label: "综合" },
  { value: "newest", label: "最新" },
  { value: "oldest", label: "最早" },
  { value: "title", label: "标题" },
];
const allowedKinds = new Set(categories.map((category) => category.value));
const allowedStates = new Set(["", "unread", "saved", "ignored", "invalid", "stale", "low", "source-unavailable"]);
const allowedSorts = new Set(sortOptions.map((option) => option.value));
const allowedDays = new Set(["", "7", "30", "90"]);

export function Feed() {
  const [, navigate] = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const rawKind = searchParams.get("kind") ?? "";
  const rawState = searchParams.get("state") ?? "unread";
  const rawSort = searchParams.get("sort") ?? "importance";
  const rawDays = searchParams.get("days") ?? "";
  const source = (searchParams.get("source") ?? "").slice(0, 120);
  const rawPage = Number(searchParams.get("page") ?? "1");
  const kind = allowedKinds.has(rawKind) ? rawKind : "";
  const state = allowedStates.has(rawState) ? rawState : "unread";
  const sort = allowedSorts.has(rawSort) ? rawSort : "importance";
  const days = allowedDays.has(rawDays) ? rawDays : "";
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1;
  const q = (searchParams.get("q") ?? "").slice(0, 200);
  const [searchDraft, setSearchDraft] = useState(q);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string; undoIgnoredId?: number } | null>(null);
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [confirmAction, setConfirmAction] = useState<BulkItemAction | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportInstruction, setReportInstruction] = useState("");
  const reportRequestIdRef = useRef("");
  const selectAllRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  function setView(next: { kind?: string; state?: string; sort?: string; days?: string; source?: string; q?: string; page?: number }) {
    const values = {
      kind: next.kind ?? kind,
      state: next.state ?? state,
      sort: next.sort ?? sort,
      days: next.days ?? days,
      source: next.source ?? source,
      q: next.q ?? q,
      page: next.page ?? page,
    };
    const params = new URLSearchParams({ state: values.state });
    if (values.kind) params.set("kind", values.kind);
    if (values.q) params.set("q", values.q);
    if (values.sort !== "importance") params.set("sort", values.sort);
    if (values.days) params.set("days", values.days);
    if (values.source) params.set("source", values.source);
    if (values.page > 1) params.set("page", String(values.page));
    setSearchParams(params, { replace: true });
  }

  useEffect(() => setSearchDraft(q), [q]);
  useEffect(() => {
    const nextQ = searchDraft.trim().slice(0, 200);
    if (nextQ === q) return;
    const timer = window.setTimeout(() => setView({ q: nextQ, page: 1 }), 300);
    return () => window.clearTimeout(timer);
  }, [searchDraft, q, kind, state, sort, days, source]);
  useEffect(() => {
    setSelected(new Set());
    setConfirmAction(null);
    setNotice(null);
  }, [kind, state, sort, days, source, q, page]);

  const itemQuery = new URLSearchParams();
  if (state) itemQuery.set("state", state);
  itemQuery.set("sort", sort);
  itemQuery.set("limit", String(PAGE_SIZE));
  itemQuery.set("offset", String((page - 1) * PAGE_SIZE));
  if (q) itemQuery.set("q", q);
  if (kind) itemQuery.set("kind", kind);
  if (days) itemQuery.set("days", days);
  if (source) itemQuery.set("source", source);
  const returnHref = `/feed${searchParams.toString() ? `?${searchParams.toString()}` : ""}`;
  const query = useQuery({
    queryKey: ["items", kind, state, sort, days, source, q, page],
    queryFn: () => api.get<ItemPage>(`/api/items?${itemQuery.toString()}`),
  });
  const sourceQuery = useQuery({ queryKey: ["item-sources"], queryFn: () => api.get<string[]>("/api/items/sources") });
  const sourceOptions = Array.isArray(sourceQuery.data) ? sourceQuery.data : [];
  const update = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<IntelligenceItem> }) => api.patch(`/api/items/${id}`, patch),
    onMutate: () => setNotice(null),
    onSuccess: (_, { id, patch }) => {
      const text = patch.isRead !== undefined
        ? patch.isRead ? "已标记为已读" : "已恢复为未读"
        : patch.isSaved !== undefined
          ? patch.isSaved ? "已收藏" : "已取消收藏"
          : patch.isIgnored ? "已忽略，可随时撤销" : "已取消忽略";
      setNotice({ tone: "success", text, undoIgnoredId: patch.isIgnored ? id : undefined });
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
    onError: () => setNotice({ tone: "error", text: "操作未完成，请重试" }),
  });
  const bulk = useMutation({
    mutationFn: (action: BulkItemAction) => api.post<ItemBulkResult>("/api/items/bulk", { ids: [...selected], action }),
    onMutate: () => setNotice(null),
    onSuccess: (result) => {
      setConfirmAction(null);
      setSelected(new Set(result.skipped.map((item) => item.id).filter((id) => selected.has(id))));
      setNotice({
        tone: "success",
        text: result.skipped.length
          ? `已处理${result.updated}条，${result.skipped.length}条未修改`
          : `已处理${result.updated}条`,
      });
      queryClient.invalidateQueries({ queryKey: ["items"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: () => setNotice({ tone: "error", text: "批量操作未完成，所选情报已保留，请重试" }),
  });
  const generateReport = useMutation({
    mutationFn: () => api.post<TaskRun>("/api/briefings/generate", {
      itemIds: [...selected],
      instruction: reportInstruction.trim(),
      requestId: reportRequestIdRef.current ||= crypto.randomUUID(),
    }),
    onSuccess: (task) => {
      reportRequestIdRef.current = "";
      setReportOpen(false);
      setReportInstruction("");
      setSelected(new Set());
      navigate(`/tasks/${task.id}`);
    },
  });
  function closeReportDialog() {
    if (generateReport.isPending) return;
    reportRequestIdRef.current = "";
    setReportInstruction("");
    setReportOpen(false);
    generateReport.reset();
  }
  const { dialogRef: reportDialogRef, rememberTrigger: rememberReportTrigger } = useModalDialog<HTMLElement>(reportOpen, closeReportDialog, generateReport.isPending);

  function openReportDialog(trigger: HTMLElement) {
    reportRequestIdRef.current = crypto.randomUUID();
    generateReport.reset();
    rememberReportTrigger(trigger);
    setReportOpen(true);
  }

  const pageItems = query.data?.items ?? [];
  const pageIds = pageItems.map((item) => item.id);
  const selectedOnPage = pageIds.filter((id) => selected.has(id)).length;
  const allSelected = pageIds.length > 0 && selectedOnPage === pageIds.length;
  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = selectedOnPage > 0 && !allSelected;
  }, [selectedOnPage, allSelected]);
  const totalPages = Math.max(1, Math.ceil((query.data?.total ?? 0) / PAGE_SIZE));
  useEffect(() => {
    if (query.data && page > totalPages) setView({ page: totalPages });
  }, [query.data, page, totalPages]);
  const savedAction: BulkItemAction = state === "saved" ? "unsave" : "save";
  const ignoredAction: BulkItemAction = state === "ignored" ? "unignore" : "ignore";
  const invalidAction: BulkItemAction = state === "invalid" ? "restore" : "invalidate";

  function toggleAll(checked: boolean) {
    setSelected((current) => {
      const next = new Set(current);
      pageIds.forEach((id) => checked ? next.add(id) : next.delete(id));
      return next;
    });
  }

  function clearFilters() {
    setSearchDraft("");
    setView({ kind: "", state: "unread", sort: "importance", days: "", source: "", q: "", page: 1 });
  }

  function requestProtectedAction(action: BulkItemAction) {
    if (selected.size === 0) return;
    setConfirmAction(action);
  }

  const confirmCopy = confirmAction === "ignore"
    ? { message: `将${selected.size}条情报移到已忽略？`, button: "确认忽略" }
    : { message: `将${selected.size}条情报标记无效？`, button: "确认标记无效" };

  return (
    <section className="stack-lg">
      <div className="feed-tools">
        <label className="feed-search"><Search size={18} /><input type="search" aria-label="搜索情报" placeholder="搜索标题、摘要、来源或关键词" maxLength={200} value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} />{searchDraft && <button aria-label="清除搜索" onClick={() => setSearchDraft("")}><X size={17} /></button>}</label>
      </div>
      <div className="filter-bar">
        <div className="segmented" aria-label="情报分类">
          {categories.map((category) => <button key={category.value} aria-pressed={kind === category.value} className={kind === category.value ? "active" : ""} onClick={() => setView({ kind: category.value, page: 1 })}>{category.label}</button>)}
        </div>
        <div className="filter-selects">
          <select aria-label="情报排序" value={sort} onChange={(event) => setView({ sort: event.target.value, page: 1 })}>{sortOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
          <select aria-label="情报状态" value={state} onChange={(event) => setView({ state: event.target.value, page: 1 })}>
            <option value="">全部</option><option value="unread">未读</option><option value="saved">收藏</option><option value="stale">可能过期</option><option value="low">低优先级</option><option value="source-unavailable">原文失效</option><option value="ignored">已忽略</option><option value="invalid">无效</option>
          </select>
          <select aria-label="情报时间" value={days} onChange={(event) => setView({ days: event.target.value, page: 1 })}>
            <option value="">不限</option><option value="7">7天</option><option value="30">30天</option><option value="90">90天</option>
          </select>
          <select aria-label="情报来源" value={source} onChange={(event) => setView({ source: event.target.value, page: 1 })}>
            <option value="">全部来源</option>
            {source && !sourceOptions.includes(source) && <option value={source}>{source}</option>}
            {sourceOptions.map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
        </div>
      </div>
      <div className="feed-list-heading">
        <div className="section-count">{query.data ? `${query.data.total}条情报` : "正在同步"}{q ? ` · 搜索“${q}”` : ""}</div>
        <button aria-pressed={selectMode} className={`selection-toggle ${selectMode ? "active" : ""}`} onClick={() => { setSelectMode(!selectMode); setSelected(new Set()); setConfirmAction(null); }}><ListChecks size={17} />{selectMode ? "退出批量" : "批量选择"}</button>
      </div>
      {selectMode && (
        <div className="bulk-toolbar" role="group" aria-label="批量操作">
          {confirmAction ? (
            <div className="bulk-confirm"><p>{confirmCopy.message}</p><button className="secondary-button" onClick={() => setConfirmAction(null)}>取消</button><button className="danger-button" disabled={bulk.isPending} onClick={() => bulk.mutate(confirmAction)}>{confirmCopy.button}</button></div>
          ) : <>
            <label className="bulk-select-all"><input ref={selectAllRef} type="checkbox" checked={allSelected} onChange={(event) => toggleAll(event.target.checked)} disabled={pageIds.length === 0} />全选当前页</label>
            <span className="bulk-count">已选{selected.size}条</span>
            <div className="bulk-actions">
              <button aria-label="标记所选已读" disabled={selected.size === 0 || bulk.isPending} onClick={() => bulk.mutate("read")}><CheckCheck size={17} /><span className="bulk-label-full">标记所选已读</span><span className="bulk-label-short">已读</span></button>
              <button aria-label={savedAction === "save" ? "收藏所选" : "取消收藏所选"} disabled={selected.size === 0 || bulk.isPending} onClick={() => bulk.mutate(savedAction)}><Bookmark size={17} /><span className="bulk-label-full">{savedAction === "save" ? "收藏所选" : "取消收藏所选"}</span><span className="bulk-label-short">{savedAction === "save" ? "收藏" : "取消收藏"}</span></button>
              <button aria-label={ignoredAction === "ignore" ? "忽略所选" : "取消忽略所选"} disabled={selected.size === 0 || bulk.isPending} onClick={() => ignoredAction === "ignore" ? requestProtectedAction("ignore") : bulk.mutate("unignore")}><EyeOff size={17} /><span className="bulk-label-full">{ignoredAction === "ignore" ? "忽略所选" : "取消忽略所选"}</span><span className="bulk-label-short">{ignoredAction === "ignore" ? "忽略" : "取消忽略"}</span></button>
              <button aria-label={invalidAction === "invalidate" ? "标记所选无效" : "恢复所选有效"} disabled={selected.size === 0 || bulk.isPending} onClick={() => invalidAction === "invalidate" ? requestProtectedAction("invalidate") : bulk.mutate("restore")}><CircleX size={17} /><span className="bulk-label-full">{invalidAction === "invalidate" ? "标记所选无效" : "恢复所选有效"}</span><span className="bulk-label-short">{invalidAction === "invalidate" ? "无效" : "恢复"}</span></button>
              <button aria-label="生成报告" className="bulk-report-button" disabled={selected.size === 0 || selected.size > 20 || bulk.isPending} onClick={(event) => openReportDialog(event.currentTarget)}><FileText size={17} /><span className="bulk-label-full">生成报告</span><span className="bulk-label-short">报告</span></button>
            </div>
          </>}
        </div>
      )}
      {notice && <div className={`action-notice ${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>
        <span>{notice.text}</span>
        {notice.undoIgnoredId !== undefined && <button type="button" disabled={update.isPending} onClick={() => update.mutate({ id: notice.undoIgnoredId!, patch: { isIgnored: false } })}>撤销忽略</button>}
      </div>}
      {query.isPending && <div className="list-skeleton"><i /><i /><i /></div>}
      {query.isError && <div className="inline-error" role="alert">情报加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>}
      {query.data?.items.length === 0 && <EmptyState compact title={q ? `没有找到“${q}”相关的情报` : "当前筛选下没有情报"} action={<button className="text-button" onClick={clearFilters}>清除筛选</button>} />}
      <div className="item-list">
        {pageItems.map((item) => <ItemCard key={item.id} item={item} selectable={selectMode} selected={selected.has(item.id)} onSelect={(checked) => setSelected((current) => { const next = new Set(current); checked ? next.add(item.id) : next.delete(item.id); return next; })} detailHref={`/items/${item.id}?from=${encodeURIComponent(returnHref)}`} busy={bulk.isPending || (update.isPending && update.variables?.id === item.id)} onChange={selectMode ? undefined : (patch) => update.mutate({ id: item.id, patch })} />)}
      </div>
      {query.data && query.data.total > PAGE_SIZE && <nav className="pagination" aria-label="情报分页"><button disabled={page <= 1} onClick={() => setView({ page: page - 1 })}><ChevronLeft size={17} />上一页</button><span>第{page}/{totalPages}页</span><button disabled={page >= totalPages} onClick={() => setView({ page: page + 1 })}>下一页<ChevronRight size={17} /></button></nav>}
      {reportOpen && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeReportDialog(); }}>
        <section ref={reportDialogRef} className="dialog-panel report-create-dialog" role="dialog" aria-modal="true" aria-labelledby="report-create-title">
          <div className="dialog-heading"><h2 id="report-create-title">用{selected.size}条情报生成报告</h2><button aria-label="关闭" disabled={generateReport.isPending} onClick={closeReportDialog}><X size={18} /></button></div>
          <label>整理要求<textarea data-autofocus maxLength={1000} rows={4} value={reportInstruction} onChange={(event) => setReportInstruction(event.target.value)} placeholder="例如：比较共同趋势，说明对研究工作的影响；留空则由Hermes自行组织。" /></label>
          <p className="dialog-error" role="alert">{generateReport.isError ? `创建失败：${generateReport.error instanceof ApiError ? generateReport.error.message : "服务暂时不可用"}。所选内容已保留，可直接重试。` : ""}</p>
          <div className="dialog-actions"><button className="secondary-button" disabled={generateReport.isPending} onClick={closeReportDialog}>取消</button><button className="primary-button" disabled={generateReport.isPending} onClick={() => generateReport.mutate()}>{generateReport.isPending ? "正在创建" : generateReport.isError ? "重试创建" : "交给Hermes"}</button></div>
        </section>
      </div>}
    </section>
  );
}
