import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect } from "react";
import { Link, useSearchParams } from "wouter";

import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import { TaskRunCard } from "../components/TaskRunCard";
import type { TaskRunPage } from "../types";

const PAGE_SIZE = 20;

export function Tasks() {
  const [searchParams, setSearchParams] = useSearchParams();
  const status = searchParams.get("status");
  const rawPage = Number(searchParams.get("page") ?? "1");
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1;
  const failedOnly = status === "failed";
  const queryParams = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String((page - 1) * PAGE_SIZE) });
  if (failedOnly) queryParams.set("status", "failed");
  const runs = useQuery({
    queryKey: ["runs", failedOnly ? "failed" : "all", page],
    queryFn: () => api.get<TaskRunPage>(`/api/runs?${queryParams.toString()}`),
    refetchInterval: 5000,
  });
  const totalPages = Math.max(1, Math.ceil((runs.data?.total ?? 0) / PAGE_SIZE));
  useEffect(() => {
    if (!runs.data || page <= totalPages) return;
    const params = new URLSearchParams();
    if (failedOnly) params.set("status", "failed");
    if (totalPages > 1) params.set("page", String(totalPages));
    setSearchParams(params, { replace: true });
  }, [failedOnly, page, runs.data, setSearchParams, totalPages]);

  function pageHref(nextPage: number) {
    const params = new URLSearchParams();
    if (failedOnly) params.set("status", "failed");
    if (nextPage > 1) params.set("page", String(nextPage));
    return `/tasks${params.size ? `?${params.toString()}` : ""}`;
  }

  return <section className="stack-lg">
    <div className="settings-toolbar"><Link className="secondary-link" href="/settings"><ArrowLeft size={17} />返回订阅</Link><span className="auto-refresh">每5秒更新</span></div>
    <nav className="segmented task-filters" aria-label="任务筛选">
      <Link className={!failedOnly ? "active" : ""} href="/tasks">全部任务</Link>
      <Link className={failedOnly ? "active" : ""} href="/tasks?status=failed">仅失败</Link>
    </nav>
    {runs.isPending && <div className="list-skeleton"><i /><i /><i /></div>}
    {runs.isError && <div className="inline-error" role="alert">任务记录加载失败。<button onClick={() => runs.refetch()}>重新加载</button></div>}
    {runs.data?.items.length === 0 && <EmptyState title={failedOnly ? "没有失败任务" : "还没有任务记录"} />}
    <div className="task-list task-list-full">{runs.data?.items.map((run) => <TaskRunCard key={run.id} run={run} />)}</div>
    {runs.data && runs.data.total > PAGE_SIZE && <nav className="pagination" aria-label="任务分页"><Link aria-disabled={page <= 1} className={page <= 1 ? "disabled" : ""} href={pageHref(Math.max(1, page - 1))}><ChevronLeft size={17} />上一页</Link><span>第{page}/{totalPages}页</span><Link aria-disabled={page >= totalPages} className={page >= totalPages ? "disabled" : ""} href={pageHref(Math.min(totalPages, page + 1))}>下一页<ChevronRight size={17} /></Link></nav>}
  </section>;
}
