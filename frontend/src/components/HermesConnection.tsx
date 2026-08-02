import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { HermesConnection } from "../types";

const key = ["hermes-connection"];
const labels: Record<HermesConnection["status"], string> = { connected: "已连接", disconnected: "连接失败", unauthorized: "未授权", unconfigured: "未配置", error: "检查失败" };
export function HermesConnection() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: key, queryFn: () => api.get<HermesConnection>("/api/integrations/hermes") });
  const [open, setOpen] = useState(false); const [baseUrl, setBaseUrl] = useState(""); const [apiKey, setApiKey] = useState("");
  useEffect(() => { if (!open) return; const fn = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false); document.addEventListener("keydown", fn); return () => document.removeEventListener("keydown", fn); }, [open]);
  const save = useMutation({ mutationFn: () => api.put<HermesConnection>("/api/integrations/hermes", { baseUrl, apiKey }), onSuccess: (d) => { qc.setQueryData(key, d); setOpen(false); } });
  const test = useMutation({ mutationFn: () => api.post<HermesConnection>("/api/integrations/hermes/test"), onSuccess: (d) => qc.setQueryData(key, d) });
  function configure() { setBaseUrl(query.data?.baseUrl ?? ""); setApiKey(""); save.reset(); setOpen(true); }
  const d = query.data;
  return <section className="hermes-connection" aria-label="Hermes连接">
    <div className="hermes-summary"><div><h2>Hermes连接</h2>{query.isPending ? <p role="status">正在检查连接…</p> : query.isError ? <p role="alert">连接信息加载失败，请重试</p> : <p role="status" className={`hermes-status ${d?.status ?? "error"}`}>{d ? `${labels[d.status]}：${d.message}` : "尚未配置Hermes服务"}</p>}</div>
      {d && <div className="hermes-meta"><span>{d.baseUrl}</span>{d.apiKeyHint && <span>密钥 {d.apiKeyHint}</span>}{d.version && <span>版本 {d.version}</span>}{d.checkedAt && <span>{new Date(d.checkedAt).toLocaleString()}</span>}</div>}
    </div><div className="hermes-actions"><button className="secondary-button" onClick={() => test.mutate()} disabled={!d?.apiKeyConfigured || test.isPending}>{test.isPending ? "正在测试" : "测试连接"}</button><button className="primary-button" onClick={configure}>配置连接</button></div>
    {test.isError && <p role="alert" className="form-error">{test.error.message}</p>}
    {open && <div className="dialog-backdrop" role="presentation" onMouseDown={e => e.target === e.currentTarget && !save.isPending && setOpen(false)}><section className="dialog-panel" role="dialog" aria-modal="true" aria-labelledby="hermes-dialog-title"><div className="dialog-heading"><h2 id="hermes-dialog-title">配置Hermes连接</h2><button className="icon-button" onClick={() => setOpen(false)} aria-label="关闭" disabled={save.isPending}>×</button></div><form onSubmit={e => { e.preventDefault(); save.mutate(); }} className="subscription-form"><label className="form-field"><span>Hermes服务地址</span><input value={baseUrl} onChange={e => setBaseUrl(e.target.value)} disabled={save.isPending} required /></label><label className="form-field"><span>Hermes API密钥</span><input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} disabled={save.isPending} placeholder="留空保留现有密钥" /></label>{save.isError && <p role="alert" className="form-error">{save.error.message || "保存失败，请重试"}</p>} {save.isSuccess && <p role="status">连接已保存</p>}<div className="dialog-actions"><button className="primary-button" type="submit" disabled={save.isPending}>{save.isPending ? "正在保存" : "保存并测试"}</button></div></form></section></div>}
  </section>;
}
