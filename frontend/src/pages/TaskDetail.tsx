import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Ban, Bot, CheckCircle2, CircleDashed, Clock3, FileText, MessageCircle, Search, Workflow, XCircle } from "lucide-react";
import { Link, useLocation, useParams } from "wouter";

import { api, ApiError } from "../api";
import { taskMessage, taskStageCopy, taskStatusMeta } from "../components/TaskRunCard";
import type { TaskRun } from "../types";

const stageIcon = {
  accepted: CircleDashed,
  processing: Bot,
  understanding: Bot,
  searching: Search,
  organizing: Bot,
  publishing: Workflow,
  completed: CheckCircle2,
  failed: XCircle,
  cancelled: Ban,
  lost: XCircle,
};

export function TaskDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const [, navigate] = useLocation();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["task-run", id],
    queryFn: () => api.get<TaskRun>(`/api/runs/${id}`),
    refetchInterval: (current) => current.state.data?.status === "queued" || current.state.data?.status === "running" ? 5000 : false,
  });
  const retry = useMutation({
    mutationFn: () => api.post<TaskRun>(`/api/runs/${id}/retry`),
    onSuccess: (nextRun) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/tasks/${nextRun.id}`);
    },
  });
  const cancel = useMutation({
    mutationFn: () => api.post<TaskRun>(`/api/runs/${id}/cancel`),
    onSuccess: (updated) => {
      queryClient.setQueryData(["task-run", id], updated);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  if (query.isPending) return <div className="detail-skeleton" role="status" aria-label="正在加载任务详情" />;
  if (query.error instanceof ApiError && query.error.status === 404) {
    return <div className="empty-state"><p>任务不存在或已删除</p><Link className="secondary-link" href="/tasks">返回任务记录</Link></div>;
  }
  if (query.isError) return <div className="inline-error" role="alert">任务详情加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>;

  const run = query.data;
  const status = taskStatusMeta[run.status];
  const StatusIcon = status.icon;
  const StageIcon = stageIcon[run.stage] || Clock3;
  const from = encodeURIComponent(`/tasks/${run.id}`);
  const requestLabel = run.origin === "weixin-hermes" ? "微信请求" : run.origin === "web-report" ? "报告要求" : "订阅任务";

  return (
    <article className="task-detail detail-page">
      <Link className="detail-back" href="/tasks"><ArrowLeft size={17} />返回任务记录</Link>
      <header className={`task-detail-header ${run.status}`}>
        <div className="task-detail-title">
          <h2>{run.topic || run.subscriptionName || `任务#${run.id}`}</h2>
          <span className="task-detail-status"><StatusIcon size={17} />{status.label}</span>
        </div>
        <p>{taskMessage(run)}</p>
        {run.status === "queued" && <div className="task-header-actions"><button className="secondary-compact danger-action" disabled={cancel.isPending} onClick={() => cancel.mutate()}>{cancel.isPending ? "正在取消" : "取消排队"}</button></div>}
        {cancel.isError && <p className="form-error" role="alert">取消失败，任务可能已经开始执行，请刷新确认。</p>}
      </header>

      <section className="task-detail-section">
        <div className="task-detail-section-title"><MessageCircle size={18} /><h3>{requestLabel}</h3></div>
        <p>{run.requestSummary || "历史任务未保存请求摘要"}</p>
      </section>

      <section className="task-detail-section">
        <div className="task-detail-section-title"><StageIcon size={18} /><h3>当前阶段</h3></div>
        <p>{taskStageCopy[run.stage]}</p>
        <dl className="task-facts">
          <div><dt>开始时间</dt><dd>{new Date(run.startedAt).toLocaleString("zh-CN")}</dd></div>
          {run.finishedAt && <div><dt>完成时间</dt><dd>{new Date(run.finishedAt).toLocaleString("zh-CN")}</dd></div>}
          {run.heartbeatAt && run.status === "running" && <div><dt>最近进度</dt><dd>{new Date(run.heartbeatAt).toLocaleString("zh-CN")}</dd></div>}
          {run.durationMs !== null && <div><dt>处理耗时</dt><dd>{(run.durationMs / 1000).toFixed(1)}秒</dd></div>}
          {run.retryOfId && <div><dt>重试来源</dt><dd><Link href={`/tasks/${run.retryOfId}`}>任务#{run.retryOfId}</Link></dd></div>}
        </dl>
        {(run.hermesRunId || run.traceId) && <details className="task-technical-details"><summary>技术信息</summary><dl>{run.hermesRunId && <div><dt>Hermes任务ID</dt><dd>{run.hermesRunId}</dd></div>}{run.traceId && <div><dt>追踪号</dt><dd>{run.traceId}</dd></div>}</dl></details>}
      </section>

      <section className="task-detail-section">
        <div className="task-detail-section-title"><FileText size={18} /><h3>知流结果</h3></div>
        {run.publicationId || run.briefingId ? <div className="detail-actions">
            {run.publicationId && <Link href={`/traces/${run.publicationId}?from=${encodeURIComponent(`/tasks/${run.id}`)}`}>查看完整处理链路</Link>}
            {run.briefingId && <Link href={`/reports/${run.briefingId}?from=${from}`}>查看生成报告</Link>}
          </div>
          : run.status === "failed" ? <div className="task-recovery">
              <p>{run.origin === "weixin-hermes"
                ? "本次未写入知流。确认来源可访问后，可在微信重新发送请求。"
                : run.origin === "web-report"
                  ? "报告未生成。确认来源情报和Hermes连接后，可以重新执行。"
                  : "本次未写入知流。确认来源和Hermes连接后，可从订阅页重新执行。"}</p>
              <div className="task-recovery-actions">
                {run.origin !== "weixin-hermes" && <button className="primary-compact" disabled={retry.isPending} onClick={() => retry.mutate()}>{retry.isPending ? "正在重新排队" : "重新执行"}</button>}
                <Link className="secondary-link" href="/settings?view=runtime">检查订阅与Hermes连接</Link>
              </div>
              {retry.isError && <p className="form-error" role="alert">重新执行失败，请稍后重试。</p>}
            </div>
            : <p>结果尚未写入。任务完成后，这里会出现处理链路和报告入口。</p>}
      </section>
    </article>
  );
}
