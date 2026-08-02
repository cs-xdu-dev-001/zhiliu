import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { HermesConnection, HermesConnectionStatus } from "../types";

const queryKey = ["hermes-connection"];
const statuses = new Set<HermesConnectionStatus>(["connected", "unreachable", "unauthorized", "unconfigured", "error"]);
const labels: Record<HermesConnectionStatus, string> = {
  connected: "已连接",
  unreachable: "无法访问",
  unauthorized: "未授权",
  unconfigured: "未配置",
  error: "检查失败",
};

function normalizeConnection(value: unknown): HermesConnection {
  if (!value || typeof value !== "object") throw new Error("invalid Hermes response");
  const item = value as Record<string, unknown>;
  const nullableString = (field: string) => item[field] === null || typeof item[field] === "string";
  if (
    typeof item.baseUrl !== "string" ||
    typeof item.apiKeyConfigured !== "boolean" ||
    typeof item.status !== "string" ||
    !statuses.has(item.status as HermesConnectionStatus) ||
    typeof item.message !== "string" ||
    !nullableString("apiKeyHint") ||
    !nullableString("checkedAt") ||
    !nullableString("version")
  ) throw new Error("invalid Hermes response");
  return item as unknown as HermesConnection;
}

function safeBaseUrl(value: string) {
  if (!value) return "尚未设置服务地址";
  try {
    const url = new URL(value);
    url.username = "";
    url.password = "";
    return url.toString();
  } catch {
    return "地址格式异常";
  }
}

export function HermesConnection() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey,
    queryFn: async () => normalizeConnection(await api.get<unknown>("/api/integrations/hermes")),
  });
  const [open, setOpen] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const configureButtonRef = useRef<HTMLButtonElement>(null);
  const baseUrlInputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const restoreFocus = useRef(false);

  const save = useMutation({
    mutationFn: async () => normalizeConnection(await api.put<unknown>("/api/integrations/hermes", { baseUrl, apiKey })),
    onSuccess: (data) => {
      queryClient.setQueryData(queryKey, data);
      setApiKey("");
      setOpen(false);
    },
  });
  const test = useMutation({
    mutationFn: async () => normalizeConnection(await api.post<unknown>("/api/integrations/hermes/test")),
    onSuccess: (data) => queryClient.setQueryData(queryKey, data),
  });
  const busy = save.isPending || test.isPending;

  useEffect(() => {
    if (open) {
      restoreFocus.current = true;
      baseUrlInputRef.current?.focus();
    } else if (restoreFocus.current) {
      restoreFocus.current = false;
      configureButtonRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (!busy) setOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)") ?? [],
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [busy, open]);

  function configure() {
    setBaseUrl(query.data?.baseUrl ?? "");
    setApiKey("");
    save.reset();
    setOpen(true);
  }

  const data = query.data;
  return (
    <section className="hermes-connection" aria-label="Hermes连接">
      <div className="hermes-summary">
        <div>
          <h2>Hermes连接</h2>
          {query.isPending ? (
            <p role="status">正在检查连接…</p>
          ) : query.isError ? (
            <p role="alert">连接信息加载失败，请刷新后重试</p>
          ) : (
            <p role="status" className={`hermes-status ${data?.status ?? "error"}`}>
              {data ? `${labels[data.status]}：${data.message}` : "尚未配置Hermes服务"}
            </p>
          )}
        </div>
        {data && (
          <div className="hermes-meta">
            <span>{safeBaseUrl(data.baseUrl)}</span>
            {data.apiKeyHint && <span>密钥 {data.apiKeyHint}</span>}
            {data.version && <span>版本 {data.version}</span>}
            {data.checkedAt && <span>{new Date(data.checkedAt).toLocaleString()}</span>}
          </div>
        )}
      </div>
      <div className="hermes-actions">
        <button
          className="secondary-button"
          onClick={() => test.mutate()}
          disabled={!data?.apiKeyConfigured || busy}
        >
          {test.isPending ? "正在测试" : "测试连接"}
        </button>
        <button ref={configureButtonRef} className="primary-button" onClick={configure} disabled={busy}>
          配置连接
        </button>
      </div>
      {test.isError && <p role="alert" className="form-error">连接测试失败，请检查服务状态后重试</p>}
      {open && (
        <div
          className="dialog-backdrop"
          role="presentation"
          onMouseDown={(event) => event.target === event.currentTarget && !busy && setOpen(false)}
        >
          <section
            ref={dialogRef}
            className="dialog-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="hermes-dialog-title"
          >
            <div className="dialog-heading">
              <h2 id="hermes-dialog-title">配置Hermes连接</h2>
              <button className="icon-button" onClick={() => setOpen(false)} aria-label="关闭" disabled={busy}>×</button>
            </div>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (!busy) save.mutate();
              }}
              className="subscription-form"
            >
              <label className="form-field">
                <span>Hermes服务地址</span>
                <input
                  ref={baseUrlInputRef}
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  disabled={busy}
                  required
                />
              </label>
              <label className="form-field">
                <span>Hermes API密钥</span>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  disabled={busy}
                  placeholder="留空保留现有密钥"
                />
              </label>
              {save.isError && <p role="alert" className="form-error">保存失败，请检查地址和密钥后重试</p>}
              <div className="dialog-actions">
                <button className="primary-button" type="submit" disabled={busy}>
                  {save.isPending ? "正在保存" : "保存并测试"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </section>
  );
}
