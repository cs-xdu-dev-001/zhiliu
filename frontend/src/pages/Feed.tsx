import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bookmark, CheckCheck, ChevronLeft, ChevronRight, CircleX, EyeOff, ListChecks, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "wouter";

import { api } from "../api";
import { ItemCard } from "../components/ItemCard";
import type { BulkItemAction, IntelligenceItem, ItemBulkResult, ItemPage } from "../types";

const PAGE_SIZE = 20;
const categories = [
  { value: "", label: "全部" },
  { value: "news", label: "热点" },
  { value: "paper", label: "论文" },
  { value: "job", label: "招聘" },
];
const sortOptions = [
  { value: "importance", label: "综合排序" },
  { value: "newest", label: "最新发布" },
  { value: "oldest", label: "最早发布" },
  { value: "title", label: "标题排序" },
];
const allowedKinds = new Set(categories.map((category) => category.value));
const allowedStates = new Set(["unread", "saved", "ignored", "invalid"]);
const allowedSorts = new Set(sortOptions.map((option) => option.value));

export function Feed() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawKind = searchParams.get("kind") ?? "";
  const rawState = searchParams.get("state") ?? "unread";
  const rawSort = searchParams.get("sort") ?? "importance";
  const rawPage = Number(searchParams.get("page") ?? "1");
  const kind = allowedKinds.has(rawKind) ? rawKind : "";
  const state = allowedStates.has(rawState) ? rawState : "unread";
  const sort = allowedSorts.has(rawSort) ? rawSort : "importance";
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1;
  const q = (searchParams.get("q") ?? "").slice(0, 200);
  const [searchDraft, setSearchDraft] = useState(q);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [confirmAction, setConfirmAction] = useState<BulkItemAction | null>(null);
  const selectAllRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  function setView(next: { kind?: string; state?: string; sort?: string; q?: string; page?: number }) {
    const values = {
      kind: next.kind ?? kind,
      state: next.state ?? state,
      sort: next.sort ?? sort,
      q: next.q ?? q,
      page: next.page ?? page,
    };
    const params = new URLSearchParams({ state: values.state });
    if (values.kind) params.set("kind", values.kind);
    if (values.q) params.set("q", values.q);
    if (values.sort !== "importance") params.set("sort", values.sort);
    if (values.page > 1) params.set("page", String(values.page));
    setSearchParams(params, { replace: true });
  }

  useEffect(() => setSearchDraft(q), [q]);
  useEffect(() => {
    const nextQ = searchDraft.trim().slice(0, 200);
    if (nextQ === q) return;
    const timer = window.setTimeout(() => setView({ q: nextQ, page: 1 }), 300);
    return () => window.clearTimeout(timer);
  }, [searchDraft, q, kind, state, sort]);
  useEffect(() => {
    setSelected(new Set());
    setConfirmAction(null);
    setNotice(null);
  }, [kind, state, sort, q, page]);

  const itemQuery = new URLSearchParams({
    state,
    sort,
    limit: String(PAGE_SIZE),
    offset: String((page - 1) * PAGE_SIZE),
  });
  if (q) itemQuery.set("q", q);
  if (kind) itemQuery.set("kind", kind);
  const returnHref = `/feed${searchParams.toString() ? `?${searchParams.toString()}` : ""}`;
  const query = useQuery({
    queryKey: ["items", kind, state, sort, q, page],
    queryFn: () => api.get<ItemPage>(`/api/items?${itemQuery.toString()}`),
  });
  const update = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<IntelligenceItem> }) => api.patch(`/api/items/${id}`, patch),
    onMutate: () => setNotice(null),
    onSuccess: (_, { patch }) => {
      const text = patch.isRead !== undefined
        ? patch.isRead ? "已标记为已读" : "已恢复为未读"
        : patch.isSaved !== undefined
          ? patch.isSaved ? "已收藏" : "已取消收藏"
          : "已忽略，可在“已忽略”中查看";
      setNotice({ tone: "success", text });
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
    setView({ kind: "", state: "unread", sort: "importance", q: "", page: 1 });
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
        <select aria-label="情报排序" value={sort} onChange={(event) => setView({ sort: event.target.value, page: 1 })}>{sortOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
      </div>
      <div className="filter-bar">
        <div className="segmented" aria-label="情报分类">
          {categories.map((category) => <button key={category.value} className={kind === category.value ? "active" : ""} onClick={() => setView({ kind: category.value, page: 1 })}>{category.label}</button>)}
        </div>
        <select aria-label="情报状态" value={state} onChange={(event) => setView({ state: event.target.value, page: 1 })}>
          <option value="unread">未读</option><option value="saved">收藏</option><option value="ignored">已忽略</option><option value="invalid">无效</option>
        </select>
      </div>
      <div className="feed-list-heading">
        <div className="section-count">{query.data ? `${query.data.total}条情报` : "正在同步"}{q ? ` · 搜索“${q}”` : ""}</div>
        <button className={`selection-toggle ${selectMode ? "active" : ""}`} onClick={() => { setSelectMode(!selectMode); setSelected(new Set()); setConfirmAction(null); }}><ListChecks size={17} />{selectMode ? "退出批量" : "批量选择"}</button>
      </div>
      {selectMode && (
        <div className="bulk-toolbar" aria-label="批量操作">
          {confirmAction ? (
            <div className="bulk-confirm"><p>{confirmCopy.message}</p><button className="secondary-button" onClick={() => setConfirmAction(null)}>取消</button><button className="danger-button" disabled={bulk.isPending} onClick={() => bulk.mutate(confirmAction)}>{confirmCopy.button}</button></div>
          ) : <>
            <label className="bulk-select-all"><input ref={selectAllRef} type="checkbox" checked={allSelected} onChange={(event) => toggleAll(event.target.checked)} disabled={pageIds.length === 0} />全选当前页</label>
            <span className="bulk-count">已选{selected.size}条</span>
            <div className="bulk-actions">
              <button disabled={selected.size === 0 || bulk.isPending} onClick={() => bulk.mutate("read")}><CheckCheck size={17} />标记所选已读</button>
              <button disabled={selected.size === 0 || bulk.isPending} onClick={() => bulk.mutate(savedAction)}><Bookmark size={17} />{savedAction === "save" ? "收藏所选" : "取消收藏所选"}</button>
              <button disabled={selected.size === 0 || bulk.isPending} onClick={() => ignoredAction === "ignore" ? requestProtectedAction("ignore") : bulk.mutate("unignore")}><EyeOff size={17} />{ignoredAction === "ignore" ? "忽略所选" : "取消忽略所选"}</button>
              <button disabled={selected.size === 0 || bulk.isPending} onClick={() => invalidAction === "invalidate" ? requestProtectedAction("invalidate") : bulk.mutate("restore")}><CircleX size={17} />{invalidAction === "invalidate" ? "标记所选无效" : "恢复所选有效"}</button>
            </div>
          </>}
        </div>
      )}
      {notice && <div className={`action-notice ${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>{notice.text}</div>}
      {query.isPending && <div className="list-skeleton"><i /><i /><i /></div>}
      {query.isError && <div className="inline-error" role="alert">情报加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>}
      {query.data?.items.length === 0 && <div className="empty-state"><p>{q ? `没有找到“${q}”相关的情报` : "当前筛选下没有情报"}</p><button className="text-button" onClick={clearFilters}>清除筛选</button></div>}
      <div className="item-list">
        {pageItems.map((item) => <ItemCard key={item.id} item={item} selectable={selectMode} selected={selected.has(item.id)} onSelect={(checked) => setSelected((current) => { const next = new Set(current); checked ? next.add(item.id) : next.delete(item.id); return next; })} detailHref={`/items/${item.id}?from=${encodeURIComponent(returnHref)}`} busy={bulk.isPending || (update.isPending && update.variables?.id === item.id)} onChange={selectMode ? undefined : (patch) => update.mutate({ id: item.id, patch })} />)}
      </div>
      {query.data && query.data.total > PAGE_SIZE && <nav className="pagination" aria-label="情报分页"><button disabled={page <= 1} onClick={() => setView({ page: page - 1 })}><ChevronLeft size={17} />上一页</button><span>第{page}/{totalPages}页</span><button disabled={page >= totalPages} onClick={() => setView({ page: page + 1 })}>下一页<ChevronRight size={17} /></button></nav>}
    </section>
  );
}
