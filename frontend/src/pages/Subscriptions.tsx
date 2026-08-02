import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock3, History, MoreHorizontal, Play, Plus, X } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { Link } from "wouter";

import { api } from "../api";
import { HermesConnection } from "../components/HermesConnection";
import type { IntelligenceKind, Subscription, SubscriptionInput } from "../types";

const emptyForm: SubscriptionInput = {
  name: "", kind: "news", keywords: [], schedule: "0 8 * * *", prompt: "", enabled: true,
};

const kindNames: Record<IntelligenceKind, string> = { news: "热点", paper: "论文", job: "招聘" };
const scheduleOptions = [
  { value: "0 8 * * *", label: "每天 08:00" },
  { value: "0 8 * * 1", label: "每周一 08:00" },
  { value: "0 8 * * 1-5", label: "工作日 08:00" },
  { value: "0 */6 * * *", label: "每6小时" },
];

function scheduleLabel(schedule: string) {
  return scheduleOptions.find((option) => option.value === schedule)?.label ?? schedule;
}

export function Subscriptions() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["subscriptions"], queryFn: () => api.get<Subscription[]>("/api/subscriptions") });
  const [editing, setEditing] = useState<Subscription | null>(null);
  const [form, setForm] = useState<SubscriptionInput>(emptyForm);
  const [keywords, setKeywords] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  const save = useMutation({
    mutationFn: (payload: SubscriptionInput) => editing ? api.put(`/api/subscriptions/${editing.id}`, payload) : api.post("/api/subscriptions", payload),
    onSuccess: () => {
      setDialogOpen(false);
      setNotice({ tone: "success", text: editing ? "订阅修改已保存" : "订阅已创建" });
      queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
    },
  });
  const update = useMutation({
    mutationFn: ({ record, patch }: { record: Subscription; patch: Partial<SubscriptionInput> }) => api.put(`/api/subscriptions/${record.id}`, { name: record.name, kind: record.kind, keywords: record.keywords, schedule: record.schedule, prompt: record.prompt, enabled: record.enabled, ...patch }),
    onSuccess: () => {
      setNotice({ tone: "success", text: "订阅状态已更新" });
      queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
    },
    onError: () => setNotice({ tone: "error", text: "订阅状态未更新，请重试" }),
  });
  const run = useMutation({
    mutationFn: (id: number) => api.post(`/api/subscriptions/${id}/run`),
    onSuccess: (_, id) => {
      const name = query.data?.find((record) => record.id === id)?.name ?? "订阅";
      setNotice({ tone: "success", text: `${name}已加入任务队列` });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: () => setNotice({ tone: "error", text: "任务未能提交，请稍后重试" }),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.delete(`/api/subscriptions/${id}`),
    onSuccess: () => {
      setDialogOpen(false);
      setConfirmingDelete(false);
      setNotice({ tone: "success", text: "订阅已删除" });
      queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
    },
  });

  useEffect(() => {
    if (!dialogOpen) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setConfirmingDelete(false);
        setDialogOpen(false);
      }
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [dialogOpen]);

  function openNew() {
    setEditing(null);
    setForm(emptyForm);
    setKeywords("");
    setConfirmingDelete(false);
    save.reset();
    setDialogOpen(true);
  }

  function openEdit(record: Subscription) {
    setEditing(record);
    setForm({ name: record.name, kind: record.kind, keywords: record.keywords, schedule: record.schedule, prompt: record.prompt, enabled: record.enabled });
    setKeywords(record.keywords.join(", "));
    setConfirmingDelete(false);
    save.reset();
    setDialogOpen(true);
  }

  function closeDialog() {
    if (save.isPending || remove.isPending) return;
    setConfirmingDelete(false);
    setDialogOpen(false);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate({ ...form, keywords: keywords.split(/[,，]/).map((value) => value.trim()).filter(Boolean) });
  }

  const schedulePreset = scheduleOptions.some((option) => option.value === form.schedule) ? form.schedule : "custom";

  return (
    <section className="stack-lg">
      <HermesConnection />
      <div className="settings-toolbar">
        <Link className="secondary-link" href="/tasks"><History size={17} />任务记录</Link>
        <button className="primary-compact" onClick={openNew}><Plus size={17} />新建订阅</button>
      </div>
      {notice && <div className={`action-notice ${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>{notice.text}</div>}
      {query.isPending && <div className="list-skeleton"><i /><i /></div>}
      {query.isError && <div className="inline-error" role="alert">订阅加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>}
      {query.data?.length === 0 && <div className="empty-state"><Clock3 size={24} /><p>还没有订阅</p><button className="text-button" onClick={openNew}>创建第一个订阅</button></div>}
      <div className="subscription-list">
        {query.data?.map((record) => <article className="subscription-row" key={record.id}>
          <span className={`kind-block ${record.kind}`}>{kindNames[record.kind]}</span>
          <div className="subscription-copy"><h2>{record.name}</h2><p><Clock3 size={13} /><span>{scheduleLabel(record.schedule)}</span><span>{record.keywords.join(" · ") || "未设关键词"}</span></p></div>
          <label className="switch" title={record.enabled ? "暂停订阅" : "启用订阅"}><input aria-label={`${record.enabled ? "暂停" : "启用"}${record.name}`} type="checkbox" checked={record.enabled} disabled={update.isPending} onChange={(event) => update.mutate({ record, patch: { enabled: event.target.checked } })} /><span /></label>
          <button className="icon-button" disabled={run.isPending} onClick={() => run.mutate(record.id)} aria-label={`${run.isPending && run.variables === record.id ? "正在执行" : "立即执行"}${record.name}`} title="立即执行"><Play size={17} /></button>
          <button className="icon-button" onClick={() => openEdit(record)} aria-label="编辑订阅" title="编辑订阅"><MoreHorizontal size={18} /></button>
        </article>)}
      </div>
      {dialogOpen && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeDialog()}>
        <section className="dialog-panel" role="dialog" aria-modal="true" aria-labelledby="subscription-dialog-title">
          <div className="dialog-heading">
            <h2 id="subscription-dialog-title">{confirmingDelete ? "删除订阅" : editing ? "编辑订阅" : "新建订阅"}</h2>
            <button className="icon-button" onClick={closeDialog} aria-label="关闭"><X size={19} /></button>
          </div>
          {confirmingDelete && editing ? <div className="confirm-delete">
            <p>删除“{editing.name}”？</p>
            <p>相关历史情报与简报会保留，但之后不会再自动获取新内容。</p>
            {remove.isError && <p className="form-error" role="alert">删除失败，请重试</p>}
            <div className="dialog-actions">
              <button type="button" className="secondary-button" onClick={() => setConfirmingDelete(false)} disabled={remove.isPending}>保留订阅</button>
              <button type="button" className="danger-button" onClick={() => remove.mutate(editing.id)} disabled={remove.isPending}>{remove.isPending ? "正在删除" : "确认删除订阅"}</button>
            </div>
          </div> : <form onSubmit={submit} className="subscription-form">
            <label className="form-field"><span>订阅名称</span><input autoFocus value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="例如：Agent论文周报" required maxLength={100} /></label>
            <div className="form-grid">
              <label className="form-field"><span>类型</span><select value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as IntelligenceKind })}><option value="news">热点</option><option value="paper">论文</option><option value="job">招聘</option></select></label>
              <label className="form-field"><span>执行周期</span><select value={schedulePreset} onChange={(event) => setForm({ ...form, schedule: event.target.value === "custom" ? "" : event.target.value })}>{scheduleOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}<option value="custom">自定义Cron</option></select></label>
            </div>
            {schedulePreset === "custom" && <label className="form-field"><span>自定义Cron</span><input value={form.schedule} onChange={(event) => setForm({ ...form, schedule: event.target.value })} placeholder="例如：0 9 * * 1-5" required /></label>}
            <label className="form-field"><span>关键词</span><input value={keywords} onChange={(event) => setKeywords(event.target.value)} placeholder="例如：Agent, RAG, Tool Use" /></label>
            <label className="form-field"><span>Hermes任务说明</span><textarea rows={6} value={form.prompt} onChange={(event) => setForm({ ...form, prompt: event.target.value })} placeholder="例如：检索过去7天的重要论文，说明核心方法、实验结果和推荐理由" required maxLength={4000} /></label>
            {save.isError && <p className="form-error" role="alert">{save.error.message}。请检查填写内容后重试。</p>}
            <div className="dialog-actions">{editing && <button type="button" className="danger-button" onClick={() => setConfirmingDelete(true)}>删除订阅</button>}<button className="primary-button" type="submit" disabled={save.isPending}>{save.isPending ? "正在保存" : "保存订阅"}</button></div>
          </form>}
        </section>
      </div>}
    </section>
  );
}
