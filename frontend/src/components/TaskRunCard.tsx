import { CheckCircle2, CircleDashed, Clock3, XCircle } from "lucide-react";
import { Link } from "wouter";

import type { TaskRun } from "../types";

export const taskStatusMeta = {
  queued: { label: "已受理", icon: CircleDashed },
  running: { label: "处理中", icon: Clock3 },
  success: { label: "已完成", icon: CheckCircle2 },
  failed: { label: "失败", icon: XCircle },
};

export const taskStageCopy: Record<TaskRun["stage"], string> = {
  accepted: "等待Hermes开始处理",
  processing: "Hermes正在理解、检索和整理",
  publishing: "正在写入知流",
  completed: "任务已完成",
  failed: "任务处理失败",
};

export function taskMessage(run: TaskRun) {
  return run.errorMessage || run.resultSummary || taskStageCopy[run.stage] || taskStageCopy.accepted;
}

export function TaskRunCard({ run }: { run: TaskRun }) {
  const meta = taskStatusMeta[run.status];
  const Icon = meta.icon;
  const title = run.topic || run.subscriptionName || `任务#${run.id}`;

  return (
    <Link className={`task-row task-row-link ${run.status}`} href={`/tasks/${run.id}`}>
      <Icon size={19} />
      <div className="task-copy">
        <strong>{title}</strong>
        <p className={run.status === "failed" ? "task-message danger" : "task-message"}>{taskMessage(run)}</p>
        <span className="task-meta">
          <time dateTime={run.startedAt}>{new Date(run.startedAt).toLocaleString("zh-CN")}</time>
          {run.durationMs !== null && ` · ${(run.durationMs / 1000).toFixed(1)}秒`}
          {run.origin === "weixin-hermes" && " · 微信Hermes"}
        </span>
      </div>
      <span className="task-status">{meta.label}</span>
    </Link>
  );
}
