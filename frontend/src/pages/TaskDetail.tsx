import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, CheckCircle2, CircleDashed, Clock3, FileText, MessageCircle, Workflow, XCircle } from "lucide-react";
import { Link, useParams } from "wouter";

import { api, ApiError } from "../api";
import { taskMessage, taskStageCopy, taskStatusMeta } from "../components/TaskRunCard";
import type { TaskRun } from "../types";

const stageIcon = {
  accepted: CircleDashed,
  processing: Bot,
  publishing: Workflow,
  completed: CheckCircle2,
  failed: XCircle,
};

export function TaskDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const query = useQuery({
    queryKey: ["task-run", id],
    queryFn: () => api.get<TaskRun>(`/api/runs/${id}`),
    refetchInterval: (current) => current.state.data?.status === "queued" || current.state.data?.status === "running" ? 5000 : false,
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

  return (
    <article className="task-detail detail-page">
      <Link className="detail-back" href="/tasks"><ArrowLeft size={17} />返回任务记录</Link>
      <header className={`task-detail-header ${run.status}`}>
        <div className="task-detail-title">
          <h2>{run.topic || run.subscriptionName || `任务#${run.id}`}</h2>
          <span className="task-detail-status"><StatusIcon size={17} />{status.label}</span>
        </div>
        <p>{taskMessage(run)}</p>
      </header>

      <section className="task-detail-section">
        <div className="task-detail-section-title"><MessageCircle size={18} /><h3>{run.origin === "weixin-hermes" ? "微信请求" : "订阅任务"}</h3></div>
        <p>{run.requestSummary || "历史任务未保存请求摘要"}</p>
      </section>

      <section className="task-detail-section">
        <div className="task-detail-section-title"><StageIcon size={18} /><h3>当前阶段</h3></div>
        <p>{taskStageCopy[run.stage]}</p>
        <dl className="task-facts">
          <div><dt>开始时间</dt><dd>{new Date(run.startedAt).toLocaleString("zh-CN")}</dd></div>
          {run.finishedAt && <div><dt>完成时间</dt><dd>{new Date(run.finishedAt).toLocaleString("zh-CN")}</dd></div>}
          {run.hermesRunId && <div><dt>Hermes任务ID</dt><dd>{run.hermesRunId}</dd></div>}
          {run.traceId && <div><dt>追踪号</dt><dd>{run.traceId}</dd></div>}
        </dl>
      </section>

      <section className="task-detail-section">
        <div className="task-detail-section-title"><FileText size={18} /><h3>知流结果</h3></div>
        {run.publicationId || run.briefingId ? <div className="detail-actions">
            {run.publicationId && <Link href={`/traces/${run.publicationId}`}>查看完整处理链路</Link>}
            {run.briefingId && <Link href={`/reports/${run.briefingId}?from=${from}`}>查看生成报告</Link>}
          </div>
          : run.status === "failed" ? <div className="task-recovery">
              <p>{run.origin === "weixin-hermes"
                ? "本次未写入知流。确认来源可访问后，可在微信重新发送请求。"
                : "本次未写入知流。确认来源和Hermes连接后，可从订阅页重新执行。"}</p>
              <Link className="secondary-link" href="/settings">检查订阅与Hermes连接</Link>
            </div>
            : <p>结果尚未写入。任务完成后，这里会出现处理链路和报告入口。</p>}
      </section>
    </article>
  );
}
