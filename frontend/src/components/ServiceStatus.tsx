import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, RefreshCw, WifiOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";

export function ServiceStatus() {
  const queryClient = useQueryClient();
  const [browserOnline, setBrowserOnline] = useState(() => navigator.onLine);
  const [recovered, setRecovered] = useState(false);
  const hadIssue = useRef(false);
  const health = useQuery({
    queryKey: ["service-health"],
    queryFn: () => api.get<{ status: string }>("/api/health"),
    enabled: browserOnline,
    retry: false,
    refetchInterval: (query) => query.state.status === "error" ? 15_000 : 60_000,
    refetchOnWindowFocus: true,
  });
  const hasIssue = !browserOnline || health.isError;

  useEffect(() => {
    const handleOnline = () => setBrowserOnline(true);
    const handleOffline = () => setBrowserOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  useEffect(() => {
    if (hasIssue) {
      hadIssue.current = true;
      setRecovered(false);
      return;
    }
    if (health.isPending || !hadIssue.current) return;
    hadIssue.current = false;
    setRecovered(true);
    queryClient.invalidateQueries({ predicate: (query) => query.queryKey[0] !== "service-health" });
    const timer = window.setTimeout(() => setRecovered(false), 4500);
    return () => window.clearTimeout(timer);
  }, [hasIssue, health.isPending, queryClient]);

  if (hasIssue) {
    return (
      <div className="service-status error" role="alert">
        <WifiOff size={19} />
        <span>{browserOnline ? "无法连接知流服务，当前内容可能不是最新状态。" : "网络已断开，恢复连接后将自动刷新。"}</span>
        {browserOnline && <button type="button" disabled={health.isFetching} onClick={() => health.refetch()}>
          <RefreshCw size={17} className={health.isFetching ? "spin" : ""} />{health.isFetching ? "正在重试" : "立即重试"}
        </button>}
      </div>
    );
  }

  if (recovered) {
    return <div className="service-status recovered" role="status"><CheckCircle2 size={19} /><span>连接已恢复，页面内容正在更新。</span></div>;
  }

  return null;
}
