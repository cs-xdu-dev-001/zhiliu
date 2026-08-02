import { useQuery } from "@tanstack/react-query";

import { api } from "../api";
import { BriefingCard } from "../components/BriefingCard";
import { EmptyState } from "../components/EmptyState";
import type { BriefingPage } from "../types";

export function Reports() {
  const query = useQuery({ queryKey: ["briefings"], queryFn: () => api.get<BriefingPage>("/api/briefings") });
  if (query.isPending) return <div className="list-skeleton"><i /><i /><i /></div>;
  if (query.isError) return <div className="inline-error" role="alert">报告加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>;
  if (!query.data.items.length) return <EmptyState title="还没有生成定期报告" />;
  return (
    <div className="briefing-list">
      {query.data.items.map((briefing) => (
        <BriefingCard key={briefing.id} briefing={briefing} detailHref={`/reports/${briefing.id}?from=${encodeURIComponent("/reports")}`} />
      ))}
    </div>
  );
}
