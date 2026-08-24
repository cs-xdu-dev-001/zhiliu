import { Ban, CheckCircle2, CircleDashed, Clock3, XCircle } from "lucide-react";
import { Link } from "wouter";

import type { TaskRun } from "../types";

export const taskStatusMeta = {
  queued: { label: "已受理", icon: CircleDashed },
  running: { label: "处理中", icon: Clock3 },
  success: { label: "已完成", icon: CheckCircle2 },
  failed: { label: "失败", icon: XCircle },
  cancelled: { label: "已取消", icon: Ban },
};

export const taskStageCopy: Record<TaskRun["stage"], string> = {
  accepted: "等待Hermes开始处理",
  processing: "Hermes正在理解、检索和整理",
  understanding: "Hermes正在理解请求",
  searching: "Hermes正在检索来源",
  organizing: "Hermes正在整理内容",
  publishing: "正在写入知流",
  completed: "任务已完成",
  failed: "任务处理失败",
  cancelled: "任务已取消，未交给Hermes执行",
  lost: "任务长时间未上报进度，可能已中断",
};

export function taskMessage(run: TaskRun) {
  return run.errorMessage || run.resultSummary || taskStageCopy[run.stage] || taskStageCopy.accepted;
}

export function TaskRunCard({ run }: { run: TaskRun }) {
  const meta = taskStatusMeta[run.status];
  const Icon = meta.icon;
  const title = run.topic || run.subscriptionName || `任务#${run.id}`;
  const message = taskMessage(run);
  const showMessage = run.status !== "success" || Boolean(run.resultSummary);

  return (
    <Link className={`task-row task-row-link ${run.status}`} href={`/tasks/${run.id}`}>
      <Icon size={19} />
      <div className="task-copy">
        <strong>{title}</strong>
        {showMessage && <p className={run.status === "failed" ? "task-message danger" : "task-message"}>{message}</p>}
        <span className="task-meta">
          <time dateTime={run.startedAt}>{new Date(run.startedAt).toLocaleString("zh-CN")}</time>
          {run.durationMs !== null && ` · ${(run.durationMs / 1000).toFixed(1)}秒`}
          {run.origin === "weixin-hermes" && " · 微信Hermes"}
          {run.origin === "web-report" && " · 知流报告"}
          {run.retryOfId && <span className="retry-indicator">手动重试</span>}
          {run.status === "queued" && run.retryCount > 0 && <span className="retry-indicator">自动重试{run.retryCount}/2</span>}
        </span>
      </div>
      <span className="task-status">{meta.label}</span>
    </Link>
  );
}
