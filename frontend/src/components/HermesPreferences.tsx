import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, SlidersHorizontal, Trash2, X } from "lucide-react";
import { FormEvent, useState } from "react";

import { api } from "../api";
import type { HermesPreference, PreferenceEffect, PreferenceKind, PreferencePage, PreferenceScope } from "../types";

const scopeNames: Record<PreferenceScope, string> = { source: "来源", topic: "主题", output: "输出方式" };
const effectNames: Record<PreferenceEffect, string> = { prefer: "优先", avoid: "避开", instruct: "遵循" };
const kindNames: Record<PreferenceKind, string> = { all: "全部内容", news: "热点", paper: "论文", job: "招聘" };

const emptyForm = { scope: "topic" as PreferenceScope, effect: "prefer" as PreferenceEffect, value: "", kind: "all" as PreferenceKind, note: "" };

export function HermesPreferences() {
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [notice, setNotice] = useState("");
  const query = useQuery({ queryKey: ["preferences"], queryFn: () => api.get<PreferencePage>("/api/preferences") });
  const save = useMutation({
    mutationFn: () => api.post<HermesPreference>("/api/preferences", form),
    onSuccess: () => { setAdding(false); setForm(emptyForm); setNotice("偏好已保存，Hermes后续整理会遵循它"); queryClient.invalidateQueries({ queryKey: ["preferences"] }); },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.delete<HermesPreference>(`/api/preferences/${id}`),
    onSuccess: () => { setNotice("偏好已移除"); queryClient.invalidateQueries({ queryKey: ["preferences"] }); },
  });
  const preferences = query.data?.items ?? [];

  function submit(event: FormEvent) { event.preventDefault(); save.mutate(); }

  return <section className="preference-section" aria-labelledby="preference-title">
    <div className="preference-heading"><div><h2 id="preference-title">Hermes偏好</h2><p>长期偏好会影响Hermes检索、筛选和整理知流内容。</p></div><button className="secondary-button" onClick={() => { setAdding(!adding); setNotice(""); }}>{adding ? <X size={17} /> : <Plus size={17} />}{adding ? "取消" : "新增偏好"}</button></div>
    {notice && <p className="action-notice success" role="status">{notice}</p>}
    {adding && <form className="preference-form" onSubmit={submit}>
      <label className="form-field"><span>作用对象</span><select aria-label="作用对象" value={form.scope} onChange={(event) => setForm({ ...form, scope: event.target.value as PreferenceScope })}><option value="topic">主题</option><option value="source">来源</option><option value="output">输出方式</option></select></label>
      <label className="form-field"><span>处理方式</span><select aria-label="处理方式" value={form.effect} onChange={(event) => setForm({ ...form, effect: event.target.value as PreferenceEffect })}><option value="prefer">优先</option><option value="avoid">避开</option><option value="instruct">遵循</option></select></label>
      <label className="form-field"><span>适用内容</span><select aria-label="适用内容" value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as PreferenceKind })}><option value="all">全部内容</option><option value="news">热点</option><option value="paper">论文</option><option value="job">招聘</option></select></label>
      <label className="form-field preference-value"><span>偏好内容</span><input autoFocus required maxLength={300} value={form.value} onChange={(event) => setForm({ ...form, value: event.target.value })} placeholder={form.scope === "source" ? "例如：arXiv" : form.scope === "output" ? "例如：结论先行，并列出来源" : "例如：Agent长期记忆"} /></label>
      <label className="form-field preference-note"><span>补充说明（可选）</span><input maxLength={1000} value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} placeholder="Hermes需要注意的边界" /></label>
      {save.isError && <p className="form-error" role="alert">偏好保存失败，请重试。</p>}
      <button className="primary-button" type="submit" disabled={save.isPending}>{save.isPending ? "正在保存" : "保存偏好"}</button>
    </form>}
    {query.isPending && <div className="preference-loading" role="status">正在加载偏好…</div>}
    {query.isError && <div className="inline-error" role="alert">偏好加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>}
    {query.data && preferences.length === 0 && !adding && <div className="preference-empty"><SlidersHorizontal size={21} /><span>还没有长期偏好，也可以在微信里告诉Hermes“以后优先关注……”</span></div>}
    {preferences.length > 0 && <div className="preference-list">{preferences.map((item) => <div className="preference-row" key={item.id}><div><span className={`preference-effect ${item.effect}`}>{effectNames[item.effect]}</span><strong>{item.value}</strong><span>{scopeNames[item.scope]} · {kindNames[item.kind]}</span>{item.note && <p>{item.note}</p>}</div><button className="icon-button" aria-label={`移除偏好${item.value}`} title="移除偏好" disabled={remove.isPending} onClick={() => remove.mutate(item.id)}><Trash2 size={17} /></button></div>)}</div>}
  </section>;
}
