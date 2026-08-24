import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, FileJson2, History, RotateCcw, ShieldCheck, Upload, X } from "lucide-react";
import { ChangeEvent, useMemo, useRef, useState } from "react";

import { ApiError, api } from "../api";
import { useModalDialog } from "../useModalDialog";

type ImportAction = "create" | "reuse" | "conflict" | "skip";
type ImportSummary = Record<string, Record<ImportAction, number>>;

interface ImportPreview {
  payloadHash: string;
  previewToken: string;
  expiresAt: string;
  totalRecords: number;
  summary: ImportSummary;
  unsupported: Record<string, number>;
  warnings: string[];
  canImport: boolean;
}

interface ImportBatch {
  id: number;
  payloadHash: string;
  reportConflict: "keep" | "new_version";
  status: "committed" | "undone";
  counts: Record<string, number>;
  summary: ImportSummary;
  createdAt: string;
  undoneAt: string | null;
}

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const summaryLabels: Record<string, string> = {
  subscriptions: "订阅映射",
  items: "情报",
  topics: "主题",
  preferences: "偏好",
  reports: "报告",
  relations: "关联关系",
};
const actionLabels: Record<ImportAction, string> = {
  create: "新增",
  reuse: "复用",
  conflict: "冲突",
  skip: "跳过",
};

function countSummary(summary: ImportSummary | undefined, action: ImportAction) {
  return Object.values(summary ?? {}).reduce((total, row) => total + (row[action] ?? 0), 0);
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(date);
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

export function DataImportMigration() {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const [raw, setRaw] = useState("");
  const [localError, setLocalError] = useState("");
  const [reportConflict, setReportConflict] = useState<"keep" | "new_version">("keep");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [undoBatch, setUndoBatch] = useState<ImportBatch | null>(null);

  const batches = useQuery({
    queryKey: ["import-batches"],
    queryFn: () => api.get<{ items: ImportBatch[] }>("/api/import/batches?limit=12"),
  });
  const preview = useMutation({
    mutationFn: (content: string) => api.postRaw<ImportPreview>("/api/import/preview", content),
  });
  const confirm = useMutation({
    mutationFn: () => api.postRaw<{ batch: ImportBatch; idempotent: boolean }>(
      `/api/import/confirm?reportConflict=${reportConflict}`,
      raw,
      { "X-Import-Preview-Token": preview.data!.previewToken },
    ),
    onSuccess: () => {
      setConfirmOpen(false);
      queryClient.invalidateQueries({ queryKey: ["import-batches"] });
    },
  });
  const undo = useMutation({
    mutationFn: (batchId: number) => api.postRaw<{ batch: ImportBatch }>(
      `/api/import/batches/${batchId}/undo`,
      "{}",
      { "X-Zhiliu-Action": "undo-import" },
    ),
    onSuccess: () => {
      setUndoBatch(null);
      queryClient.invalidateQueries({ queryKey: ["import-batches"] });
    },
  });
  const closeConfirm = () => !confirm.isPending && setConfirmOpen(false);
  const closeUndo = () => !undo.isPending && setUndoBatch(null);
  const { dialogRef: confirmRef, rememberTrigger: rememberConfirmTrigger } = useModalDialog<HTMLElement>(confirmOpen, closeConfirm, confirm.isPending);
  const { dialogRef: undoRef, rememberTrigger: rememberUndoTrigger } = useModalDialog<HTMLElement>(Boolean(undoBatch), closeUndo, undo.isPending);

  const previewTotals = useMemo(() => ({
    create: countSummary(preview.data?.summary, "create"),
    reuse: countSummary(preview.data?.summary, "reuse"),
    conflict: countSummary(preview.data?.summary, "conflict"),
    skip: countSummary(preview.data?.summary, "skip") + Object.values(preview.data?.unsupported ?? {}).reduce((a, b) => a + b, 0),
  }), [preview.data]);

  async function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setLocalError("");
    preview.reset();
    confirm.reset();
    if (!file) return;
    if (!file.name.toLocaleLowerCase().endsWith(".json")) {
      setRaw("");
      setFileName(file.name);
      setLocalError("请选择知流导出的JSON文件");
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setRaw("");
      setFileName(file.name);
      setLocalError("文件超过10MiB限制");
      return;
    }
    try {
      const content = await file.text();
      setFileName(file.name);
      setRaw(content);
    } catch {
      setLocalError("文件读取失败，请重新选择");
      setRaw("");
    }
  }

  function clearFile() {
    setFileName("");
    setRaw("");
    setLocalError("");
    preview.reset();
    confirm.reset();
    if (inputRef.current) inputRef.current.value = "";
  }

  return <section className="data-import" aria-labelledby="data-import-title">
    <div className="migration-heading">
      <div><h2 id="data-import-title">导入内容</h2><p>先预览差异，确认后整批写入；密钥、任务历史和内部地址不会导入。</p></div>
      <ShieldCheck size={22} aria-hidden="true" />
    </div>

    <div className="import-file-zone">
      <input ref={inputRef} id="import-json-file" type="file" accept="application/json,.json" aria-label="选择知流JSON文件" onChange={selectFile} />
      {!fileName ? <label htmlFor="import-json-file"><Upload size={20} /><strong>选择知流JSON</strong><span>最大10MiB</span></label> : <div className="selected-import-file">
        <FileJson2 size={21} />
        <span><strong>{fileName}</strong><small>{raw ? `${new Blob([raw]).size.toLocaleString("zh-CN")}字节` : "文件不可用"}</small></span>
        <button type="button" aria-label="移除导入文件" onClick={clearFile}><X size={18} /></button>
      </div>}
    </div>

    {(localError || preview.isError) && <p className="migration-message error" role="alert">{localError || errorMessage(preview.error, "文件预览失败")}</p>}
    {!preview.data && <div className="import-preview-empty"><ShieldCheck size={20} /><span>预览只读，不会修改现有数据。</span><button className="primary-button" disabled={!raw || preview.isPending} onClick={() => preview.mutate(raw)}>{preview.isPending ? "正在校验" : "预览导入内容"}</button></div>}

    {preview.data && <div className="import-preview" aria-live="polite">
      <div className="preview-verdict"><Check size={20} /><strong>文件结构有效</strong><span>{preview.data.totalRecords.toLocaleString("zh-CN")}条记录</span></div>
      <dl className="preview-totals">
        {(Object.keys(actionLabels) as ImportAction[]).map((action) => <div key={action} className={action}><dt>{actionLabels[action]}</dt><dd>{previewTotals[action]}</dd></div>)}
      </dl>
      <div className="preview-table" role="table" aria-label="导入差异">
        <div className="preview-table-head" role="row"><span role="columnheader">内容</span>{(Object.keys(actionLabels) as ImportAction[]).map((action) => <span role="columnheader" key={action}>{actionLabels[action]}</span>)}</div>
        {Object.entries(preview.data.summary).map(([name, row]) => <div className="preview-table-row" role="row" key={name}><strong role="rowheader">{summaryLabels[name] ?? name}</strong>{(Object.keys(actionLabels) as ImportAction[]).map((action) => <span role="cell" key={action}>{row[action] ?? 0}</span>)}</div>)}
      </div>
      {preview.data.warnings.length > 0 && <ul className="import-warnings">{preview.data.warnings.map((warning) => <li key={warning}><AlertTriangle size={16} />{warning}</li>)}</ul>}
      {preview.data.summary.reports?.conflict > 0 && <fieldset className="report-conflict-choice"><legend>报告版本冲突</legend><label><input type="radio" name="report-conflict" checked={reportConflict === "keep"} onChange={() => setReportConflict("keep")} /><span><strong>保留现有版本</strong>冲突报告不写入</span></label><label><input type="radio" name="report-conflict" checked={reportConflict === "new_version"} onChange={() => setReportConflict("new_version")} /><span><strong>创建新版本</strong>接续当前最新版本</span></label></fieldset>}
      <div className="migration-actions"><button className="secondary-button" onClick={clearFile}>换一个文件</button><button className="primary-button" disabled={!preview.data.canImport || confirm.isPending} onClick={(event) => { rememberConfirmTrigger(event.currentTarget); setConfirmOpen(true); }}>确认导入</button></div>
    </div>}
    {confirm.isSuccess && <p className="migration-message success" role="status">{confirm.data.idempotent ? "该文件已经导入，本次未重复写入。" : `迁移批次#${confirm.data.batch.id}已完成。`}</p>}
    {confirm.isError && <p className="migration-message error" role="alert">{errorMessage(confirm.error, "导入失败，数据库未发生部分写入")}</p>}

    <div className="import-history">
      <div className="import-history-title"><h3><History size={18} />迁移记录</h3><button className="text-button" disabled={batches.isFetching} onClick={() => batches.refetch()}>刷新</button></div>
      {batches.isPending && <p className="migration-history-state">正在读取迁移记录</p>}
      {batches.isError && <p className="migration-message error" role="alert">迁移记录加载失败，请刷新重试。</p>}
      {batches.data?.items?.length === 0 && <p className="migration-history-state">还没有导入记录</p>}
      <div className="import-batch-list">{batches.data?.items?.map((batch) => <article key={batch.id} className="import-batch-row">
        <div><strong>批次#{batch.id}</strong><span>{formatDate(batch.createdAt)}</span></div>
        <p><span className={`batch-status ${batch.status}`}>{batch.status === "committed" ? "已导入" : "已撤销"}</span><span>新增{countSummary(batch.summary, "create")}项</span><span>复用{countSummary(batch.summary, "reuse")}项</span></p>
        {batch.status === "committed" && <button className="secondary-compact" onClick={(event) => { rememberUndoTrigger(event.currentTarget); undo.reset(); setUndoBatch(batch); }}><RotateCcw size={16} />撤销</button>}
      </article>)}</div>
    </div>

    {confirmOpen && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeConfirm()}><section ref={confirmRef} className="dialog-panel migration-confirm" role="alertdialog" aria-modal="true" aria-labelledby="confirm-import-title" aria-describedby="confirm-import-description"><div className="dialog-heading"><h2 id="confirm-import-title">导入{previewTotals.create}项新内容？</h2><button className="icon-button" aria-label="关闭" disabled={confirm.isPending} onClick={closeConfirm}><X size={19} /></button></div><p id="confirm-import-description">现有内容不会被覆盖。写入失败时整批回滚，成功后可在迁移记录中撤销。</p><div className="dialog-actions"><button className="secondary-button" disabled={confirm.isPending} onClick={closeConfirm}>返回预览</button><button className="primary-button" disabled={confirm.isPending} onClick={() => confirm.mutate()}>{confirm.isPending ? "正在写入" : "开始导入"}</button></div></section></div>}
    {undoBatch && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeUndo()}><section ref={undoRef} className="dialog-panel migration-confirm" role="alertdialog" aria-modal="true" aria-labelledby="undo-import-title" aria-describedby="undo-import-description"><div className="dialog-heading"><h2 id="undo-import-title">撤销迁移批次#{undoBatch.id}？</h2><button className="icon-button" aria-label="关闭" disabled={undo.isPending} onClick={closeUndo}><X size={19} /></button></div><p id="undo-import-description">只移除该批次新增且之后未变化的内容。若已有修改或新引用，系统会拒绝整次撤销。</p>{undo.isError && <p className="migration-message error" role="alert">{errorMessage(undo.error, "撤销失败，数据未改变")}</p>}<div className="dialog-actions"><button className="secondary-button" disabled={undo.isPending} onClick={closeUndo}>保留内容</button><button className="danger-button" disabled={undo.isPending} onClick={() => undo.mutate(undoBatch.id)}>{undo.isPending ? "正在撤销" : "确认撤销"}</button></div></section></div>}
  </section>;
}
