import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock3, History, MoreHorizontal, Play, Plus, X } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link } from "wouter";

import { api } from "../api";
import type { IntelligenceKind, Subscription, SubscriptionInput } from "../types";

const emptyForm: SubscriptionInput = {
  name: "", kind: "news", keywords: [], schedule: "0 8 * * *", prompt: "", enabled: true,
};

const kindNames: Record<IntelligenceKind, string> = { news: "热点", paper: "论文", job: "招聘" };

export function Subscriptions() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["subscriptions"], queryFn: () => api.get<Subscription[]>("/api/subscriptions") });
  const [editing, setEditing] = useState<Subscription | null>(null);
  const [form, setForm] = useState<SubscriptionInput>(emptyForm);
  const [keywords, setKeywords] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);

  const save = useMutation({
    mutationFn: (payload: SubscriptionInput) => editing ? api.put(`/api/subscriptions/${editing.id}`, payload) : api.post("/api/subscriptions", payload),
    onSuccess: () => { setDialogOpen(false); queryClient.invalidateQueries({ queryKey: ["subscriptions"] }); },
  });
  const update = useMutation({
    mutationFn: ({ record, patch }: { record: Subscription; patch: Partial<SubscriptionInput> }) => api.put(`/api/subscriptions/${record.id}`, { name: record.name, kind: record.kind, keywords: record.keywords, schedule: record.schedule, prompt: record.prompt, enabled: record.enabled, ...patch }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["subscriptions"] }),
  });
  const run = useMutation({ mutationFn: (id: number) => api.post(`/api/subscriptions/${id}/run`), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runs"] }) });
  const remove = useMutation({ mutationFn: (id: number) => api.delete(`/api/subscriptions/${id}`), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["subscriptions"] }) });

  function openNew() { setEditing(null); setForm(emptyForm); setKeywords(""); setDialogOpen(true); }
  function openEdit(record: Subscription) {
    setEditing(record);
    setForm({ name: record.name, kind: record.kind, keywords: record.keywords, schedule: record.schedule, prompt: record.prompt, enabled: record.enabled });
    setKeywords(record.keywords.join(", "));
    setDialogOpen(true);
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate({ ...form, keywords: keywords.split(/[,，]/).map((value) => value.trim()).filter(Boolean) });
  }

  return (
    <section className="stack-lg">
      <div className="settings-toolbar">
        <Link className="secondary-link" href="/tasks"><History size={17} />任务记录</Link>
        <button className="primary-compact" onClick={openNew}><Plus size={17} />新建订阅</button>
      </div>
      {query.isPending && <div className="list-skeleton"><i /><i /></div>}
      {query.data?.length === 0 && <div className="empty-state"><Clock3 size={24} /><p>还没有订阅</p><button className="text-button" onClick={openNew}>创建第一个订阅</button></div>}
      <div className="subscription-list">
        {query.data?.map((record) => <article className="subscription-row" key={record.id}>
          <span className={`kind-block ${record.kind}`}>{kindNames[record.kind]}</span>
          <div className="subscription-copy"><h2>{record.name}</h2><p><Clock3 size={13} />{record.schedule}<span>{record.keywords.join(" · ") || "未设关键词"}</span></p></div>
          <label className="switch" title={record.enabled ? "暂停订阅" : "启用订阅"}><input type="checkbox" checked={record.enabled} onChange={(event) => update.mutate({ record, patch: { enabled: event.target.checked } })} /><span /></label>
          <button className="icon-button" onClick={() => run.mutate(record.id)} aria-label="立即执行" title="立即执行"><Play size={17} /></button>
          <button className="icon-button" onClick={() => openEdit(record)} aria-label="编辑订阅" title="编辑订阅"><MoreHorizontal size={18} /></button>
        </article>)}
      </div>
      {dialogOpen && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setDialogOpen(false)}>
        <section className="dialog-panel" role="dialog" aria-modal="true" aria-labelledby="subscription-dialog-title">
          <div className="dialog-heading"><h2 id="subscription-dialog-title">{editing ? "编辑订阅" : "新建订阅"}</h2><button className="icon-button" onClick={() => setDialogOpen(false)} aria-label="关闭"><X size={19} /></button></div>
          <form onSubmit={submit} className="subscription-form">
            <label className="form-field"><span>订阅名称</span><input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required /></label>
            <div className="form-grid">
              <label className="form-field"><span>类型</span><select value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as IntelligenceKind })}><option value="news">热点</option><option value="paper">论文</option><option value="job">招聘</option></select></label>
              <label className="form-field"><span>执行周期</span><input value={form.schedule} onChange={(event) => setForm({ ...form, schedule: event.target.value })} required /></label>
            </div>
            <label className="form-field"><span>关键词</span><input value={keywords} onChange={(event) => setKeywords(event.target.value)} placeholder="Agent, RAG, Tool Use" /></label>
            <label className="form-field"><span>Hermes任务说明</span><textarea rows={6} value={form.prompt} onChange={(event) => setForm({ ...form, prompt: event.target.value })} required /></label>
            {save.isError && <p className="form-error">{save.error.message}</p>}
            <div className="dialog-actions">{editing && <button type="button" className="danger-button" onClick={() => { remove.mutate(editing.id); setDialogOpen(false); }}>删除</button>}<button className="primary-button" type="submit" disabled={save.isPending}>保存订阅</button></div>
          </form>
        </section>
      </div>}
    </section>
  );
}
