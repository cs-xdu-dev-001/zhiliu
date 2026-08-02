import { useQuery } from "@tanstack/react-query";
import { ChevronRight, FileText } from "lucide-react";
import { useState } from "react";

import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import type { Briefing, BriefingPage } from "../types";

export function Reports() {
  const query = useQuery({ queryKey: ["briefings"], queryFn: () => api.get<BriefingPage>("/api/briefings") });
  const [selected, setSelected] = useState<Briefing | null>(null);
  if (query.isPending) return <div className="list-skeleton"><i /><i /><i /></div>;
  if (query.isError) return <div className="inline-error">报告加载失败</div>;
  if (!query.data.items.length) return <EmptyState title="还没有生成定期报告" />;
  const activeReport = selected ?? query.data.items[0];
  return (
    <div className="report-layout">
      <div className="report-list">
        {query.data.items.map((briefing) => <button key={briefing.id} className={activeReport.id === briefing.id ? "active" : ""} aria-pressed={activeReport.id === briefing.id} onClick={() => setSelected(briefing)}><FileText size={19} /><span><strong>{briefing.title}</strong><small>{new Date(briefing.createdAt).toLocaleDateString("zh-CN")} · {briefing.itemCount}条</small></span><ChevronRight size={17} /></button>)}
      </div>
      <article className="report-detail">
        <><div className="report-eyebrow"><span className={`kind-tag ${activeReport.kind}`}>{activeReport.kind === "paper" ? "论文" : activeReport.kind === "job" ? "招聘" : "热点"}</span><time>{new Date(activeReport.createdAt).toLocaleString("zh-CN")}</time></div><h2>{activeReport.title}</h2><p>{activeReport.content}</p></>
      </article>
    </div>
  );
}
