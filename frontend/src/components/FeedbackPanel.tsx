import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, BellRing, ChevronDown, CircleOff, Copy, RotateCcw, ShieldAlert, ThumbsUp, Undo2 } from "lucide-react";
import { FormEvent, useRef, useState } from "react";

import { api, ApiError } from "../api";
import type { ContentFeedback, FeedbackPage, FeedbackType } from "../types";

const feedbackOptions = [
  { type: "useful", label: "有用", icon: ThumbsUp, direct: true },
  { type: "irrelevant", label: "不相关", icon: CircleOff, direct: true },
  { type: "duplicate", label: "内容重复", icon: Copy, direct: true },
  { type: "summary_wrong", label: "摘要有误", icon: AlertCircle, direct: false },
  { type: "source_unreliable", label: "来源不可靠", icon: ShieldAlert, direct: false },
  { type: "follow_up", label: "持续关注", icon: BellRing, direct: false },
] as const;

const feedbackLabels: Record<FeedbackType, string> = Object.fromEntries(
  feedbackOptions.map((option) => [option.type, option.label]),
) as Record<FeedbackType, string>;
const impactLabels = { current: "仅当前内容", topic: "影响主题排序", long_term: "Hermes长期偏好" } as const;

type TargetType = "item" | "briefing";
type Draft = { type: FeedbackType; note: string; applyLongTerm: boolean };
type EditDraft = { id: number; note: string; applyLongTerm: boolean };

function errorText(error: unknown) {
  return error instanceof ApiError ? error.message : "操作未完成，请重试";
}

function canUseLongTerm(type: FeedbackType) {
  return type === "source_unreliable" || type === "follow_up";
}

export function FeedbackPanel({ targetType, targetId }: { targetType: TargetType; targetId: number }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const requestKey = useRef("");
  const queryKey = ["feedback", targetType, targetId] as const;
  const query = useQuery({
    queryKey,
    queryFn: () => api.get<FeedbackPage>(`/api/feedback?${targetType === "item" ? "itemId" : "briefingId"}=${targetId}`),
    enabled: open,
  });

  function refresh() {
    queryClient.invalidateQueries({ queryKey });
    queryClient.invalidateQueries({ queryKey: [targetType === "item" ? "item" : "briefing", String(targetId)] });
    queryClient.invalidateQueries({ queryKey: ["items"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    queryClient.invalidateQueries({ queryKey: ["preferences"] });
  }

  const create = useMutation({
    mutationFn: (value: Draft) => api.post<ContentFeedback>("/api/feedback", {
      targetType,
      targetId,
      feedbackType: value.type,
      note: value.note.trim(),
      applyLongTerm: value.applyLongTerm,
      idempotencyKey: requestKey.current ||= crypto.randomUUID(),
    }),
    onMutate: () => setNotice(null),
    onSuccess: (record) => {
      requestKey.current = "";
      setDraft(null);
      setNotice(`已记录“${feedbackLabels[record.feedbackType]}”，${impactLabels[record.impactScope]}`);
      refresh();
    },
  });
  const update = useMutation({
    mutationFn: ({ record, value }: { record: ContentFeedback; value: EditDraft }) => api.patch<ContentFeedback>(`/api/feedback/${record.id}`, {
      version: record.version,
      note: value.note.trim(),
      ...(canUseLongTerm(record.feedbackType) ? { applyLongTerm: value.applyLongTerm } : {}),
    }),
    onMutate: () => setNotice(null),
    onSuccess: () => { setEditDraft(null); setNotice("反馈已更新"); refresh(); },
  });
  const toggle = useMutation({
    mutationFn: ({ record, action }: { record: ContentFeedback; action: "revoke" | "restore" }) =>
      api.post<ContentFeedback>(`/api/feedback/${record.id}/${action}`, { version: record.version }),
    onMutate: () => setNotice(null),
    onSuccess: (record) => { setEditDraft(null); setNotice(record.active ? "反馈已恢复" : "反馈已撤销"); refresh(); },
  });
  const busy = create.isPending || update.isPending || toggle.isPending;
  const records = query.data?.items ?? [];

  function begin(type: FeedbackType, direct: boolean) {
    create.reset();
    requestKey.current = crypto.randomUUID();
    const value = { type, note: "", applyLongTerm: false };
    if (direct) create.mutate(value);
    else setDraft(value);
  }

  function submitDraft(event: FormEvent) {
    event.preventDefault();
    if (draft) create.mutate(draft);
  }

  return <section className="feedback-panel" aria-labelledby={`feedback-heading-${targetType}-${targetId}`}>
    <details onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary><span><strong id={`feedback-heading-${targetType}-${targetId}`}>反馈与修正</strong>{records.filter((record) => record.active).length > 0 && <b>{records.filter((record) => record.active).length}</b>}</span><ChevronDown size={18} aria-hidden="true" /></summary>
      <div className="feedback-body">
        <div className="feedback-actions" aria-label="选择反馈">
          {feedbackOptions.map(({ type, label, icon: Icon, direct }) => <button disabled={busy} key={type} onClick={() => begin(type, direct)}><Icon size={17} />{label}</button>)}
        </div>
        {draft && <form className="feedback-form" onSubmit={submitDraft}>
          <strong>{feedbackLabels[draft.type]}</strong>
          {(draft.type === "summary_wrong" || draft.type === "source_unreliable") && <textarea autoFocus required={draft.type === "summary_wrong"} maxLength={1000} rows={3} aria-label="反馈说明" placeholder={draft.type === "summary_wrong" ? "指出遗漏或错误，便于后续修正" : "可补充判断依据"} value={draft.note} onChange={(event) => setDraft({ ...draft, note: event.target.value })} />}
          {targetType === "item" && canUseLongTerm(draft.type) && <label className="feedback-long-term"><input type="checkbox" checked={draft.applyLongTerm} onChange={(event) => setDraft({ ...draft, applyLongTerm: event.target.checked })} />同时形成Hermes长期偏好</label>}
          <div><button className="primary-compact" disabled={create.isPending || (draft.type === "summary_wrong" && !draft.note.trim())}>确认反馈</button><button type="button" disabled={create.isPending} onClick={() => { requestKey.current = ""; setDraft(null); }}>取消</button></div>
        </form>}
        {(notice || create.isError || update.isError || toggle.isError) && <p className={`feedback-notice ${create.isError || update.isError || toggle.isError ? "error" : "success"}`} role={create.isError || update.isError || toggle.isError ? "alert" : "status"}>{notice ?? errorText(create.error ?? update.error ?? toggle.error)}</p>}
        {query.isPending ? <p className="feedback-loading">正在加载反馈记录</p> : query.isError ? <p className="feedback-notice error" role="alert">反馈记录暂时无法加载。<button onClick={() => query.refetch()}>重新加载</button></p> : records.length > 0 ? <div className="feedback-history">
          {records.map((record) => <div className={`feedback-record ${record.active ? "" : "revoked"}`} key={record.id}>
            <div className="feedback-record-main"><strong>{feedbackLabels[record.feedbackType]}</strong><span>{record.active ? impactLabels[record.impactScope] : "已撤销"}</span><time dateTime={record.createdAt}>{new Date(record.createdAt).toLocaleString("zh-CN")}</time>{record.note && editDraft?.id !== record.id && <p>{record.note}</p>}</div>
            {editDraft?.id === record.id ? <form className="feedback-edit" onSubmit={(event) => { event.preventDefault(); update.mutate({ record, value: editDraft }); }}>
              <textarea aria-label="修改反馈说明" required={record.feedbackType === "summary_wrong"} maxLength={1000} rows={2} value={editDraft.note} onChange={(event) => setEditDraft({ ...editDraft, note: event.target.value })} />
              {targetType === "item" && canUseLongTerm(record.feedbackType) && <label className="feedback-long-term"><input type="checkbox" checked={editDraft.applyLongTerm} onChange={(event) => setEditDraft({ ...editDraft, applyLongTerm: event.target.checked })} />Hermes长期偏好</label>}
              <div><button disabled={update.isPending}>保存</button><button type="button" onClick={() => setEditDraft(null)}>取消</button></div>
            </form> : <div className="feedback-record-actions">{record.active ? <><button disabled={busy} onClick={() => setEditDraft({ id: record.id, note: record.note, applyLongTerm: record.impactScope === "long_term" })}>修改</button><button disabled={busy} onClick={() => toggle.mutate({ record, action: "revoke" })}><Undo2 size={15} />撤销</button></> : <button disabled={busy} onClick={() => toggle.mutate({ record, action: "restore" })}><RotateCcw size={15} />恢复</button>}</div>}
          </div>)}
        </div> : <p className="feedback-empty">暂无反馈记录</p>}
      </div>
    </details>
  </section>;
}
