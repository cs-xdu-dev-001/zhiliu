import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ItemCard } from "../components/ItemCard";
import type { IntelligenceItem, ItemPage } from "../types";

const categories = [
  { value: "", label: "全部" },
  { value: "news", label: "热点" },
  { value: "paper", label: "论文" },
  { value: "job", label: "招聘" },
];

export function Feed() {
  const [kind, setKind] = useState("");
  const [state, setState] = useState("unread");
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["items", kind, state],
    queryFn: () => api.get<ItemPage>(`/api/items?state=${state}${kind ? `&kind=${kind}` : ""}`),
  });
  const update = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<IntelligenceItem> }) => api.patch(`/api/items/${id}`, patch),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["items"] }),
  });

  return (
    <section className="stack-lg">
      <div className="filter-bar">
        <div className="segmented" aria-label="情报分类">
          {categories.map((category) => <button key={category.value} className={kind === category.value ? "active" : ""} onClick={() => setKind(category.value)}>{category.label}</button>)}
        </div>
        <select aria-label="情报状态" value={state} onChange={(event) => setState(event.target.value)}>
          <option value="unread">未读</option><option value="saved">收藏</option><option value="ignored">已忽略</option>
        </select>
      </div>
      <div className="section-count">{query.data ? `${query.data.total}条情报` : "正在同步"}</div>
      {query.isPending && <div className="list-skeleton"><i /><i /><i /></div>}
      {query.isError && <div className="inline-error">情报加载失败</div>}
      {query.data?.items.length === 0 && <EmptyState title="这个分类暂时没有情报" />}
      <div className="item-list">
        {query.data?.items.map((item) => <ItemCard key={item.id} item={item} onChange={(patch) => update.mutate({ id: item.id, patch })} />)}
      </div>
    </section>
  );
}

