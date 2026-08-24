import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { useEffect } from "react";
import { Link, useSearchParams } from "wouter";

import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import { TaskRunCard } from "../components/TaskRunCard";
import type { TaskRun, TaskRunPage } from "../types";

const PAGE_SIZE = 20;
const statuses: Array<{ value: TaskRun["status"] | ""; label: string }> = [
  { value: "", label: "全部" },
  { value: "running", label: "处理中" },
  { value: "queued", label: "待开始" },
  { value: "failed", label: "需处理" },
  { value: "success", label: "已完成" },
  { value: "cancelled", label: "已取消" },
];
const origins: Array<{ value: TaskRun["origin"] | ""; label: string }> = [
  { value: "", label: "全部来源" },
  { value: "weixin-hermes", label: "微信Hermes" },
  { value: "subscription-hermes", label: "定时订阅" },
  { value: "web-report", label: "知流报告" },
];

export function Tasks() {
  const [searchParams, setSearchParams] = useSearchParams();
  const status = statuses.some((entry) => entry.value === searchParams.get("status")) ? searchParams.get("status") ?? "" : "";
  const origin = origins.some((entry) => entry.value === searchParams.get("origin")) ? searchParams.get("origin") ?? "" : "";
  const rawPage = Number(searchParams.get("page") ?? "1");
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1;
  const queryParams = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String((page - 1) * PAGE_SIZE) });
  if (status) queryParams.set("status", status);
  if (origin) queryParams.set("origin", origin);
  const runs = useQuery({
    queryKey: ["runs", status || "all", origin || "all", page],
    queryFn: () => api.get<TaskRunPage>(`/api/runs?${queryParams.toString()}`),
    refetchInterval: (current) => current.state.data?.items.some((run) => run.status === "queued" || run.status === "running") ? 5000 : 60_000,
  });
  const totalPages = Math.max(1, Math.ceil((runs.data?.total ?? 0) / PAGE_SIZE));

  function hrefFor(nextStatus = status, nextOrigin = origin, nextPage = 1) {
    const params = new URLSearchParams();
    if (nextStatus) params.set("status", nextStatus);
    if (nextOrigin) params.set("origin", nextOrigin);
    if (nextPage > 1) params.set("page", String(nextPage));
    return `/tasks${params.size ? `?${params.toString()}` : ""}`;
  }

  useEffect(() => {
    if (!runs.data || page <= totalPages) return;
    setSearchParams(new URL(hrefFor(status, origin, totalPages), window.location.origin).searchParams, { replace: true });
  }, [origin, page, runs.data, setSearchParams, status, totalPages]);

  const emptyTitle = status === "failed" ? "没有需要处理的任务" : status || origin ? "此筛选下没有任务" : "还没有任务";

  return <section className="task-inbox stack-lg">
    <div className="inbox-toolbar">
      <div className="inbox-source-filter">
        <label htmlFor="task-origin">来源</label>
        <select id="task-origin" value={origin} onChange={(event) => setSearchParams(new URL(hrefFor(status, event.target.value), window.location.origin).searchParams)}>
          {origins.map((entry) => <option key={entry.value} value={entry.value}>{entry.label}</option>)}
        </select>
      </div>
      <button className="secondary-compact" disabled={runs.isFetching} onClick={() => runs.refetch()}><RefreshCw size={16} />{runs.isFetching ? "正在更新" : "刷新"}</button>
    </div>
    <nav className="segmented task-filters" aria-label="任务状态">
      {statuses.map((entry) => <Link key={entry.value} aria-current={status === entry.value ? "page" : undefined} className={status === entry.value ? "active" : ""} href={hrefFor(entry.value, origin)}>{entry.label}</Link>)}
    </nav>
    {runs.isPending && <div className="list-skeleton"><i /><i /><i /></div>}
    {runs.isError && <div className="inline-error" role="alert">任务收件箱加载失败。<button onClick={() => runs.refetch()}>重新加载</button></div>}
    {runs.data?.items.length === 0 && <EmptyState compact={Boolean(status || origin)} title={emptyTitle} description={!status && !origin ? "从微信让Hermes整理内容，或在知流运行订阅后，进度会出现在这里。" : undefined} action={status || origin ? <Link className="secondary-link" href="/tasks">清除筛选</Link> : <Link className="secondary-link" href="/">查看示例指令</Link>} />}
    <div className="task-list task-list-full">{runs.data?.items.map((run) => <TaskRunCard key={run.id} run={run} />)}</div>
    {runs.data && runs.data.total > PAGE_SIZE && <nav className="pagination" aria-label="任务分页">{page <= 1 ? <span className="disabled"><ChevronLeft size={17} />上一页</span> : <Link href={hrefFor(status, origin, page - 1)}><ChevronLeft size={17} />上一页</Link>}<span>第{page}/{totalPages}页</span>{page >= totalPages ? <span className="disabled">下一页<ChevronRight size={17} /></span> : <Link href={hrefFor(status, origin, page + 1)}>下一页<ChevronRight size={17} /></Link>}</nav>}
  </section>;
}
