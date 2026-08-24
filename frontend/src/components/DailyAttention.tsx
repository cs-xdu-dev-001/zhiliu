import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, RefreshCw, Sparkles } from "lucide-react";
import { Link } from "wouter";

import { api } from "../api";
import type { DailyAttention as DailyAttentionData, DailyAttentionGenerate } from "../types";

export function DailyAttention() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["daily-attention"],
    queryFn: () => api.get<DailyAttentionData>("/api/daily-attention"),
    refetchInterval: (current) => ["queued", "running"].includes(current.state.data?.activeTask?.status ?? "") ? 5000 : 60_000,
  });
  const generate = useMutation({
    mutationFn: () => api.post<DailyAttentionGenerate>("/api/daily-attention/generate"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["daily-attention"] }),
  });
  const configure = useMutation({
    mutationFn: (settings: { minImportance: number; importantOnly: boolean }) => api.put<DailyAttentionData>("/api/daily-attention/settings", settings),
    onSuccess: (data) => queryClient.setQueryData(["daily-attention"], data),
  });

  if (query.isPending) return <section className="daily-attention loading" aria-label="今日关注"><span>正在整理今日信号…</span></section>;
  if (query.isError) return <section className="daily-attention error" aria-label="今日关注"><span>今日关注加载失败</span><button onClick={() => query.refetch()}>重试</button></section>;
  const data = query.data;
  const running = data.activeTask && ["queued", "running"].includes(data.activeTask.status);
  const signals = [
    data.importantChangeCount ? `${data.importantChangeCount}条重要变化` : "",
    data.sourceUnavailableCount ? `${data.sourceUnavailableCount}个来源失效` : "",
    data.pendingChangeCount ? `${data.pendingChangeCount}条待确认` : "",
    data.consecutiveFailureCount ? `${data.consecutiveFailureCount}个连续失败任务` : "",
  ].filter(Boolean);

  return <section className="daily-attention" aria-labelledby="daily-attention-title">
    <div className="daily-attention-head">
      <div><Sparkles size={19} /><h2 id="daily-attention-title">今日关注</h2>{signals.length > 0 && <span>{signals.join(" · ")}</span>}</div>
      <div className="daily-attention-controls">
        <label>门槛<select aria-label="关注摘要最低重要程度" value={data.settings.minImportance} disabled={configure.isPending} onChange={(event) => configure.mutate({ minImportance: Number(event.target.value), importantOnly: data.settings.importantOnly })}><option value="0.6">60分</option><option value="0.7">70分</option><option value="0.8">80分</option><option value="0.9">90分</option></select></label>
        <label><input type="checkbox" checked={data.settings.importantOnly} disabled={configure.isPending} onChange={(event) => configure.mutate({ minImportance: data.settings.minImportance, importantOnly: event.target.checked })} />仅重要变化</label>
      </div>
    </div>
    {data.items.length > 0 ? <div className="daily-attention-items">{data.items.slice(0, 3).map(({ item, reasons }) => <Link key={item.id} href={`/items/${item.id}?from=${encodeURIComponent("/")}`}><span>{reasons.slice(0, 2).join(" · ")}</span><strong>{item.title}</strong><ArrowRight size={16} /></Link>)}</div> : <p className="daily-attention-empty">今天没有达到条件的重要变化，不会生成空摘要。</p>}
    {data.risingTopics.length > 0 && <div className="daily-rising">升温主题：{data.risingTopics.slice(0, 3).map((topic, index) => <span key={topic.id}>{index > 0 && "、"}<Link href={`/topics/${topic.id}`}>{topic.name}</Link></span>)}</div>}
    <div className="daily-attention-actions">
      {data.latestBriefing && <Link href={`/reports/${data.latestBriefing.id}?from=${encodeURIComponent("/")}`}>查看最近摘要</Link>}
      {data.activeTask?.id && <Link href={`/tasks/${data.activeTask.id}`}>{running ? "查看生成进度" : "查看生成记录"}</Link>}
      <button className="primary-button" disabled={generate.isPending || Boolean(running) || data.items.length === 0} onClick={() => generate.mutate()}><RefreshCw size={16} />{running ? "正在生成" : "生成今日摘要"}</button>
    </div>
    {generate.data && <p className="daily-attention-notice" role="status">{generate.data.message}</p>}
    {generate.isError && <p className="form-error" role="alert">摘要生成失败，上一份有效摘要未受影响。</p>}
  </section>;
}
