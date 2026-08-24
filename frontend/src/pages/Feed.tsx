import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bookmark, CheckCheck, ChevronLeft, ChevronRight, CircleX, EyeOff, FileText, ListChecks, Plus, Search, Tag, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation, useSearchParams } from "wouter";

import { api, ApiError } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ItemCard } from "../components/ItemCard";
import type { BulkItemAction, IntelligenceItem, ItemBulkResult, ItemPage, SavedView, TaskRun } from "../types";
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
const stateOptions = [
  { value: "unread", label: "未读" },
  { value: "saved", label: "收藏" },
  { value: "stale", label: "可能过期" },
  { value: "low", label: "低优先级" },
  { value: "source-unavailable", label: "原文失效" },
  { value: "ignored", label: "已归档" },
  { value: "invalid", label: "无效" },
];
const allowedStates = new Set(stateOptions.map((option) => option.value));
const allowedSorts = new Set(sortOptions.map((option) => option.value));
const allowedDays = new Set(["", "7", "30", "90"]);
type BulkRequest = { ids: number[]; action: BulkItemAction; tags?: string[]; idempotencyKey: string };

const inverseActions: Partial<Record<BulkItemAction, BulkItemAction>> = {
  read: "unread", unread: "read", save: "unsave", unsave: "save",
  ignore: "unignore", unignore: "ignore", invalidate: "restore", restore: "invalidate",
};

export function Feed() {
  const [, navigate] = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const rawKind = searchParams.get("kind") ?? "";
  const rawStates = searchParams.getAll("state");
  const rawSort = searchParams.get("sort") ?? "importance";
  const rawDays = searchParams.get("days") ?? "";
  const source = (searchParams.get("source") ?? "").slice(0, 120);
  const rawPage = Number(searchParams.get("page") ?? "1");
  const kind = allowedKinds.has(rawKind) ? rawKind : "";
  const validStates = [...new Set(rawStates.filter((value) => allowedStates.has(value)))];
  const states = rawStates.includes("all") ? [] : validStates.length ? validStates : ["unread"];
  const tags = [...new Set(searchParams.getAll("tag").map((value) => value.slice(0, 40)).filter(Boolean))];
  const sort = allowedSorts.has(rawSort) ? rawSort : "importance";
  const days = allowedDays.has(rawDays) ? rawDays : "";
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1;
  const q = (searchParams.get("q") ?? "").slice(0, 200);
  const [searchDraft, setSearchDraft] = useState(q);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string; undoIgnoredId?: number; undoBulk?: BulkRequest; retryBulk?: BulkRequest } | null>(null);
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [confirmAction, setConfirmAction] = useState<BulkItemAction | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportInstruction, setReportInstruction] = useState("");
  const [saveViewOpen, setSaveViewOpen] = useState(false);
  const [viewName, setViewName] = useState("");
  const [tagDraft, setTagDraft] = useState("");
  const reportRequestIdRef = useRef("");
  const selectAllRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  function setView(next: { kind?: string; states?: string[]; tags?: string[]; sort?: string; days?: string; source?: string; q?: string; page?: number }) {
    const values = {
      kind: next.kind ?? kind,
      states: next.states ?? states,
      tags: next.tags ?? tags,
      sort: next.sort ?? sort,
      days: next.days ?? days,
      source: next.source ?? source,
      q: next.q ?? q,
      page: next.page ?? page,
    };
    const params = new URLSearchParams();
    if (values.states.length) values.states.forEach((value) => params.append("state", value));
    else params.set("state", "all");
    values.tags.forEach((value) => params.append("tag", value));
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
  }, [searchDraft, q, kind, states.join("|"), tags.join("|"), sort, days, source]);
  useEffect(() => {
    setSelected(new Set());
    setConfirmAction(null);
    setNotice(null);
  }, [kind, states.join("|"), tags.join("|"), sort, days, source, q, page]);

  const itemQuery = new URLSearchParams();
  states.forEach((value) => itemQuery.append("state", value));
  tags.forEach((value) => itemQuery.append("tag", value));
  itemQuery.set("sort", sort);
  itemQuery.set("limit", String(PAGE_SIZE));
  itemQuery.set("offset", String((page - 1) * PAGE_SIZE));
  if (q) itemQuery.set("q", q);
  if (kind) itemQuery.set("kind", kind);
  if (days) itemQuery.set("days", days);
  if (source) itemQuery.set("source", source);
  const returnHref = `/feed${searchParams.toString() ? `?${searchParams.toString()}` : ""}`;
  const query = useQuery({
    queryKey: ["items", kind, states, tags, sort, days, source, q, page],
    queryFn: () => api.get<ItemPage>(`/api/items?${itemQuery.toString()}`),
  });
  const sourceQuery = useQuery({ queryKey: ["item-sources"], queryFn: () => api.get<string[]>("/api/items/sources") });
  const tagQuery = useQuery({ queryKey: ["item-tags"], queryFn: () => api.get<string[]>("/api/tags") });
  const savedViewsQuery = useQuery({ queryKey: ["saved-views"], queryFn: () => api.get<SavedView[]>("/api/saved-views") });
  const sourceOptions = Array.isArray(sourceQuery.data) ? sourceQuery.data : [];
  const tagOptions = Array.isArray(tagQuery.data) ? tagQuery.data : [];
  const savedViews = Array.isArray(savedViewsQuery.data) ? savedViewsQuery.data : [];
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
    mutationFn: (request: BulkRequest) => api.post<ItemBulkResult>("/api/items/bulk", request),
    onMutate: () => setNotice(null),
    onSuccess: (result, request) => {
      setConfirmAction(null);
      setSelected(new Set(result.skipped.map((item) => item.id).filter((id) => request.ids.includes(id))));
      const inverse = inverseActions[request.action];
      setNotice({
        tone: "success",
        text: result.skipped.length
          ? `已处理${result.updated}条，${result.skipped.length}条未修改`
          : `已处理${result.updated}条`,
        undoBulk: inverse && result.updatedIds.length ? {
          ids: result.updatedIds,
          action: inverse,
          tags: request.tags,
          idempotencyKey: crypto.randomUUID(),
        } : undefined,
      });
      queryClient.invalidateQueries({ queryKey: ["items"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["item-tags"] });
    },
    onError: (_, request) => setNotice({ tone: "error", text: "批量操作未完成，所选情报已保留", retryBulk: request }),
  });
  const saveView = useMutation({
    mutationFn: () => {
      const params = new URLSearchParams(searchParams);
      params.delete("page");
      return api.post<SavedView>("/api/saved-views", { name: viewName.trim(), query: params.toString() });
    },
    onSuccess: () => {
      setViewName("");
      setSaveViewOpen(false);
      setNotice({ tone: "success", text: "当前筛选已保存" });
      queryClient.invalidateQueries({ queryKey: ["saved-views"] });
    },
    onError: (error) => setNotice({ tone: "error", text: error instanceof ApiError ? error.message : "保存视图失败" }),
  });
  const deleteView = useMutation({
    mutationFn: (id: number) => api.delete(`/api/saved-views/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["saved-views"] }),
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
  const savedAction: BulkItemAction = states.includes("saved") ? "unsave" : "save";
  const ignoredAction: BulkItemAction = states.includes("ignored") ? "unignore" : "ignore";
  const invalidAction: BulkItemAction = states.includes("invalid") ? "restore" : "invalidate";

  function runBulk(action: BulkItemAction, bulkTags?: string[], ids = [...selected]) {
    if (!ids.length) return;
    bulk.mutate({ ids, action, tags: bulkTags?.length ? bulkTags : undefined, idempotencyKey: crypto.randomUUID() });
  }

  function toggleFilter(current: string[], value: string) {
    return current.includes(value) ? current.filter((item) => item !== value) : [...current, value];
  }

  function toggleAll(checked: boolean) {
    setSelected((current) => {
      const next = new Set(current);
      pageIds.forEach((id) => checked ? next.add(id) : next.delete(id));
      return next;
    });
  }

  function clearFilters() {
    setSearchDraft("");
    setView({ kind: "", states: ["unread"], tags: [], sort: "importance", days: "", source: "", q: "", page: 1 });
  }

  function requestProtectedAction(action: BulkItemAction) {
    if (selected.size === 0) return;
    setConfirmAction(action);
  }

  const confirmCopy = confirmAction === "ignore"
    ? { message: `将${selected.size}条情报归档？`, button: "确认归档" }
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
          <details className="filter-menu"><summary>状态{states.length ? ` · ${states.length}` : " · 全部"}</summary><div className="filter-menu-panel" aria-label="情报状态">{stateOptions.map((option) => <label key={option.value}><input type="checkbox" checked={states.includes(option.value)} onChange={() => setView({ states: toggleFilter(states, option.value), page: 1 })} />{option.label}</label>)}<button className="text-button" onClick={() => setView({ states: [], page: 1 })}>清除状态</button></div></details>
          <select aria-label="情报时间" value={days} onChange={(event) => setView({ days: event.target.value, page: 1 })}>
            <option value="">不限</option><option value="7">7天</option><option value="30">30天</option><option value="90">90天</option>
          </select>
          <select aria-label="情报来源" value={source} onChange={(event) => setView({ source: event.target.value, page: 1 })}>
            <option value="">全部来源</option>
            {source && !sourceOptions.includes(source) && <option value={source}>{source}</option>}
            {sourceOptions.map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
          <details className="filter-menu"><summary>标签{tags.length ? ` · ${tags.length}` : ""}</summary><div className="filter-menu-panel" aria-label="情报标签">{tagOptions.length ? tagOptions.map((option) => <label key={option}><input type="checkbox" checked={tags.includes(option)} onChange={() => setView({ tags: toggleFilter(tags, option), page: 1 })} />{option}</label>) : <span>暂无标签</span>}{tags.length > 0 && <button className="text-button" onClick={() => setView({ tags: [], page: 1 })}>清除标签</button>}</div></details>
        </div>
      </div>
      <div className="saved-view-bar" aria-label="保存的视图">
        <div className="saved-view-list">
          {savedViews.map((view) => <span className="saved-view-chip" key={view.id}><button onClick={() => setSearchParams(new URLSearchParams(view.query), { replace: true })}>{view.name}</button><button aria-label={`删除视图${view.name}`} disabled={deleteView.isPending} onClick={() => deleteView.mutate(view.id)}><Trash2 size={14} /></button></span>)}
        </div>
        {saveViewOpen ? <form className="save-view-form" onSubmit={(event) => { event.preventDefault(); if (viewName.trim()) saveView.mutate(); }}><input autoFocus aria-label="视图名称" maxLength={80} placeholder="给当前筛选命名" value={viewName} onChange={(event) => setViewName(event.target.value)} /><button type="submit" disabled={!viewName.trim() || saveView.isPending}>保存</button><button type="button" aria-label="取消保存视图" onClick={() => { setSaveViewOpen(false); setViewName(""); }}><X size={16} /></button></form> : <button className="save-view-trigger" onClick={() => setSaveViewOpen(true)}><Plus size={16} />保存当前筛选</button>}
      </div>
      <div className="feed-list-heading">
        <div className="section-count">{query.data ? `${query.data.total}条情报` : "正在同步"}{q ? ` · 搜索“${q}”` : ""}</div>
        <button aria-pressed={selectMode} className={`selection-toggle ${selectMode ? "active" : ""}`} onClick={() => { setSelectMode(!selectMode); setSelected(new Set()); setConfirmAction(null); }}><ListChecks size={17} />{selectMode ? "退出批量" : "批量选择"}</button>
      </div>
      {selectMode && (
        <div className="bulk-toolbar" role="group" aria-label="批量操作">
          {confirmAction ? (
            <div className="bulk-confirm"><p>{confirmCopy.message}</p><button className="secondary-button" onClick={() => setConfirmAction(null)}>取消</button><button className="danger-button" disabled={bulk.isPending} onClick={() => runBulk(confirmAction)}>{confirmCopy.button}</button></div>
          ) : <>
            <label className="bulk-select-all"><input ref={selectAllRef} type="checkbox" checked={allSelected} onChange={(event) => toggleAll(event.target.checked)} disabled={pageIds.length === 0} />全选当前页</label>
            <span className="bulk-count">已选{selected.size}条</span>
            <div className="bulk-actions">
              <button aria-label="标记所选已读" disabled={selected.size === 0 || bulk.isPending} onClick={() => runBulk("read")}><CheckCheck size={17} /><span className="bulk-label-full">标记所选已读</span><span className="bulk-label-short">已读</span></button>
              <button aria-label={savedAction === "save" ? "收藏所选" : "取消收藏所选"} disabled={selected.size === 0 || bulk.isPending} onClick={() => runBulk(savedAction)}><Bookmark size={17} /><span className="bulk-label-full">{savedAction === "save" ? "收藏所选" : "取消收藏所选"}</span><span className="bulk-label-short">{savedAction === "save" ? "收藏" : "取消收藏"}</span></button>
              <details className="bulk-tag-menu"><summary aria-label="批量标签"><Tag size={17} /><span>标签</span></summary><div><input aria-label="批量标签内容" maxLength={200} placeholder="标签，用逗号分隔" value={tagDraft} onChange={(event) => setTagDraft(event.target.value)} /><button disabled={!tagDraft.trim() || selected.size === 0 || bulk.isPending} onClick={() => runBulk("tag", tagDraft.split(/[,，]/).map((value) => value.trim()).filter(Boolean))}>添加</button><button disabled={!tagDraft.trim() || selected.size === 0 || bulk.isPending} onClick={() => runBulk("untag", tagDraft.split(/[,，]/).map((value) => value.trim()).filter(Boolean))}>移除</button></div></details>
              <button aria-label={ignoredAction === "ignore" ? "归档所选" : "恢复所选归档"} disabled={selected.size === 0 || bulk.isPending} onClick={() => ignoredAction === "ignore" ? requestProtectedAction("ignore") : runBulk("unignore")}><EyeOff size={17} /><span className="bulk-label-full">{ignoredAction === "ignore" ? "归档所选" : "恢复归档"}</span><span className="bulk-label-short">{ignoredAction === "ignore" ? "归档" : "恢复"}</span></button>
              <button aria-label={invalidAction === "invalidate" ? "标记所选无效" : "恢复所选有效"} disabled={selected.size === 0 || bulk.isPending} onClick={() => invalidAction === "invalidate" ? requestProtectedAction("invalidate") : runBulk("restore")}><CircleX size={17} /><span className="bulk-label-full">{invalidAction === "invalidate" ? "标记所选无效" : "恢复所选有效"}</span><span className="bulk-label-short">{invalidAction === "invalidate" ? "无效" : "恢复"}</span></button>
              <button aria-label="生成报告" className="bulk-report-button" disabled={selected.size === 0 || selected.size > 20 || bulk.isPending} onClick={(event) => openReportDialog(event.currentTarget)}><FileText size={17} /><span className="bulk-label-full">生成报告</span><span className="bulk-label-short">报告</span></button>
            </div>
          </>}
        </div>
      )}
      {notice && <div className={`action-notice ${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>
        <span>{notice.text}</span>
        {notice.undoIgnoredId !== undefined && <button type="button" disabled={update.isPending} onClick={() => update.mutate({ id: notice.undoIgnoredId!, patch: { isIgnored: false } })}>撤销忽略</button>}
        {notice.undoBulk && <button type="button" disabled={bulk.isPending} onClick={() => bulk.mutate(notice.undoBulk!)}>撤销</button>}
        {notice.retryBulk && <button type="button" disabled={bulk.isPending} onClick={() => bulk.mutate(notice.retryBulk!)}>重试</button>}
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
