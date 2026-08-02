import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";
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
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["items", kind, state],
    queryFn: () => api.get<ItemPage>(`/api/items?state=${state}${kind ? `&kind=${kind}` : ""}`),
  });
  const update = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<IntelligenceItem> }) => api.patch(`/api/items/${id}`, patch),
    onMutate: () => setNotice(null),
    onSuccess: (_, { patch }) => {
      const text = patch.isRead !== undefined
        ? patch.isRead ? "已标记为已读" : "已恢复为未读"
        : patch.isSaved !== undefined
          ? patch.isSaved ? "已收藏" : "已取消收藏"
          : "已忽略，可在“已忽略”中查看";
      setNotice({ tone: "success", text });
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
    onError: () => setNotice({ tone: "error", text: "操作未完成，请重试" }),
  });

  function clearFilters() {
    setKind("");
    setState("unread");
  }

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
      {notice && <div className={`action-notice ${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>{notice.text}</div>}
      {query.isPending && <div className="list-skeleton"><i /><i /><i /></div>}
      {query.isError && <div className="inline-error" role="alert">情报加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>}
      {query.data?.items.length === 0 && <div className="empty-state"><p>当前筛选下没有情报</p><button className="text-button" onClick={clearFilters}>清除筛选</button></div>}
      <div className="item-list">
        {query.data?.items.map((item) => <ItemCard key={item.id} item={item} busy={update.isPending && update.variables?.id === item.id} onChange={(patch) => update.mutate({ id: item.id, patch })} />)}
      </div>
    </section>
  );
}
