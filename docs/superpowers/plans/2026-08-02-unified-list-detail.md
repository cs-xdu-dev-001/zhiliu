# 知流统一列表与详情页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将首页、情报页和报告页统一为标题加两行摘要的可导航卡片，并提供独立的情报与报告详情页。

**Architecture:** 保留现有FastAPI响应模型，在情报API补充单条读取；前端使用wouter动态路由和查询参数保存筛选状态。列表卡片只负责摘要与导航，完整内容和状态操作集中到详情页，卡片操作区与详情链接保持独立。

**Tech Stack:** FastAPI、SQLAlchemy、pytest、React 19、TypeScript、wouter 3、TanStack Query 5、Vitest、Testing Library、CSS

---

## 文件结构

- `backend/app/api/items.py`：新增单条情报读取，不改变列表和PATCH语义。
- `backend/tests/test_items.py`：覆盖情报详情成功和404。
- `frontend/src/components/ItemCard.tsx`：统一情报预览卡及详情链接，保留独立快捷操作。
- `frontend/src/components/BriefingCard.tsx`：新增报告预览卡，供首页和报告列表复用。
- `frontend/src/pages/ItemDetail.tsx`：加载和操作单条情报。
- `frontend/src/pages/BriefingDetail.tsx`：加载完整报告。
- `frontend/src/pages/Feed.tsx`：用URL查询参数保存分类和状态筛选。
- `frontend/src/pages/Reports.tsx`：从左右分栏改为报告卡片列表。
- `frontend/src/pages/Home.tsx`：统计卡导航、情报详情入口和最新报告入口。
- `frontend/src/pages/Tasks.tsx`：支持`status=failed`入口的客户端筛选。
- `frontend/src/components/AppShell.tsx`：注册动态详情路由并显示详情页标题。
- `frontend/src/styles.css`：卡片、详情阅读、状态与响应式样式。

### Task 1: 提供单条情报详情API

**Files:**
- Modify: `backend/app/api/items.py`
- Modify: `backend/tests/test_items.py`

- [ ] **Step 1: 写入失败测试**

在`backend/tests/test_items.py`增加：

```python
def test_get_item_detail(client: TestClient, seeded_item) -> None:
    response = client.get(f"/api/items/{seeded_item.id}")

    assert response.status_code == 200
    assert response.json()["id"] == seeded_item.id
    assert response.json()["title"] == "Agent框架发布新版本"
    assert response.json()["reason"] == "影响Agent开发工作流"


def test_missing_item_detail_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/items/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "情报不存在"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
cd backend
uv run pytest tests/test_items.py::test_get_item_detail tests/test_items.py::test_missing_item_detail_returns_not_found -v
```

Expected: 两项FAIL，`GET /api/items/{id}`尚未注册。

- [ ] **Step 3: 实现最小详情接口**

在`list_items`之后、PATCH接口之前增加：

```python
@router.get("/items/{item_id}", response_model=IntelligenceItemResponse)
def get_item(item_id: int, db: Session = Depends(get_db)) -> IntelligenceItemResponse:
    record = db.get(IntelligenceItem, item_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="情报不存在")
    return serialize_item(record)
```

- [ ] **Step 4: 运行情报API测试**

Run: `uv run pytest tests/test_items.py -v`

Expected: 全部PASS。

- [ ] **Step 5: 提交**

```powershell
git add backend/app/api/items.py backend/tests/test_items.py
git commit -m "feat: add intelligence detail API"
```

### Task 2: 将情报筛选和失败任务入口写入URL

**Files:**
- Modify: `frontend/src/pages/Feed.tsx`
- Modify: `frontend/src/pages/Feed.test.tsx`
- Modify: `frontend/src/pages/Tasks.tsx`
- Create: `frontend/src/pages/Tasks.test.tsx`

- [ ] **Step 1: 给情报页增加URL筛选失败测试**

在`Feed.test.tsx`增加：

```tsx
it("从URL读取筛选并在修改时更新URL", async () => {
  window.history.pushState({}, "", "/feed?state=saved&kind=paper");
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  expect(get).toHaveBeenCalledWith("/api/items?state=saved&kind=paper");
  expect(screen.getByRole("button", { name: "论文" })).toHaveClass("active");
  expect(screen.getByRole("combobox", { name: "情报状态" })).toHaveValue("saved");

  await userEvent.click(screen.getByRole("button", { name: "热点" }));
  expect(window.location.search).toBe("?state=saved&kind=news");
});
```

在`beforeEach`开头增加：

```tsx
window.history.pushState({}, "", "/feed");
```

- [ ] **Step 2: 给失败任务入口增加失败测试**

创建`Tasks.test.tsx`，完整内容：

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { Tasks } from "./Tasks";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../api", () => ({ api: { get } }));

beforeEach(() => {
  window.history.pushState({}, "", "/tasks?status=failed");
  get.mockImplementation((path: string) => Promise.resolve(
    path === "/api/runs"
      ? {
          items: [
            { id: 1, subscriptionId: 1, hermesRunId: null, status: "failed", startedAt: "2026-08-01T08:00:00Z", finishedAt: null, durationMs: null, errorMessage: "连接失败" },
            { id: 2, subscriptionId: 1, hermesRunId: "run-2", status: "success", startedAt: "2026-08-01T09:00:00Z", finishedAt: null, durationMs: 1000, errorMessage: null },
          ],
          total: 2,
        }
      : [{ id: 1, name: "每日Agent动态" }],
  ));
});

it("status=failed时只展示失败任务", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Tasks />
    </QueryClientProvider>,
  );

  expect(await screen.findByText("连接失败")).toBeVisible();
  expect(screen.getByText("失败")).toBeVisible();
  expect(screen.queryByText("已完成")).not.toBeInTheDocument();
});
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```powershell
cd frontend
npm test -- --run src/pages/Feed.test.tsx src/pages/Tasks.test.tsx
```

Expected: URL筛选和失败任务筛选断言FAIL。

- [ ] **Step 4: 实现URL筛选**

在`Feed.tsx`中用wouter查询参数替换`kind`和`state`本地状态：

```tsx
import { useSearchParams } from "wouter";

const [searchParams, setSearchParams] = useSearchParams();
const kind = searchParams.get("kind") ?? "";
const state = searchParams.get("state") ?? "unread";

function setFilters(nextKind: string, nextState: string) {
  const next = new URLSearchParams({ state: nextState });
  if (nextKind) next.set("kind", nextKind);
  setSearchParams(next, { replace: true });
}

function clearFilters() {
  setFilters("", "unread");
}
```

分类按钮改为`onClick={() => setFilters(category.value, state)}`，状态下拉框改为`onChange={(event) => setFilters(kind, event.target.value)}`，删除`useState`导入。

在`Tasks.tsx`读取查询参数并筛选：

```tsx
import { Link, useSearchParams } from "wouter";

const [searchParams] = useSearchParams();
const status = searchParams.get("status");
const visibleRuns = status === "failed"
  ? runs.data?.items.filter((run) => run.status === "failed")
  : runs.data?.items;
```

空状态和列表都改用`visibleRuns`。

- [ ] **Step 5: 运行并提交**

Run: `npm test -- --run src/pages/Feed.test.tsx src/pages/Tasks.test.tsx`

Expected: 全部PASS。

```powershell
git add frontend/src/pages/Feed.tsx frontend/src/pages/Feed.test.tsx frontend/src/pages/Tasks.tsx frontend/src/pages/Tasks.test.tsx
git commit -m "feat: preserve list filters in URLs"
```

### Task 3: 统一情报卡并新增情报详情页

**Files:**
- Modify: `frontend/src/components/ItemCard.tsx`
- Modify: `frontend/src/components/ItemCard.test.tsx`
- Create: `frontend/src/pages/ItemDetail.tsx`
- Create: `frontend/src/pages/ItemDetail.test.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: 编辑UI前加载Impeccable质量底线**

Run:

```powershell
Get-Content C:\Users\z2986\.codex\skills\impeccable\reference\craft-floor.md -Raw -Encoding utf8
```

Expected: 完整读完后再修改UI。

- [ ] **Step 2: 给情报卡写失败测试**

在`ItemCard.test.tsx`增加：

```tsx
it("标题摘要进入独立详情且列表不展开判断理由", () => {
  render(<ItemCard item={item} detailHref="/items/1?from=%2Ffeed%3Fstate%3Dunread" />);

  expect(screen.getByRole("link", { name: /Agent框架发布新版本/ })).toHaveAttribute(
    "href",
    "/items/1?from=%2Ffeed%3Fstate%3Dunread",
  );
  expect(screen.getByText("工具调用可靠性提升。")).toHaveClass("item-summary");
  expect(screen.queryByText(/值得关注/)).not.toBeInTheDocument();
});

it("快捷操作位于详情链接之外", () => {
  const onChange = vi.fn();
  render(<ItemCard item={item} onChange={onChange} />);

  expect(screen.getByRole("link", { name: /Agent框架发布新版本/ })).not.toContainElement(
    screen.getByRole("button", { name: "收藏" }),
  );
});
```

把`vitest`导入改为`import { expect, it, vi } from "vitest";`。

- [ ] **Step 3: 给详情页写失败测试**

创建`ItemDetail.test.tsx`，覆盖成功、操作和404：

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../api";
import { ItemDetail } from "./ItemDetail";

const { get, patch } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));
vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  api: { get, patch },
}));

const item = {
  id: 1, subscriptionId: 1, kind: "news", title: "Agent框架发布新版本",
  summary: "完整摘要。", url: "https://example.com", source: "Example · 微信Hermes",
  publishedAt: "2026-08-01T00:00:00Z", keywords: ["Agent", "MCP"], reason: "影响Agent开发工作流",
  importance: 0.9, isRead: false, isSaved: false, isIgnored: false, createdAt: "2026-08-01T00:00:00Z",
};

beforeEach(() => {
  window.history.pushState({}, "", "/items/1?from=%2Ffeed%3Fstate%3Dunread");
  get.mockReset().mockResolvedValue(item);
  patch.mockReset().mockResolvedValue({ ...item, isSaved: true });
});

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ItemDetail />
    </QueryClientProvider>,
  );
}

it("显示完整情报并返回来源列表", async () => {
  renderPage();
  expect(await screen.findByRole("heading", { name: "Agent框架发布新版本" })).toBeVisible();
  expect(screen.getByText("影响Agent开发工作流")).toBeVisible();
  expect(screen.getByRole("link", { name: "返回情报列表" })).toHaveAttribute("href", "/feed?state=unread");
  expect(screen.getByRole("link", { name: /打开原文/ })).toHaveAttribute("href", "https://example.com");
});

it("可以在详情收藏", async () => {
  renderPage();
  await screen.findByText("完整摘要。");
  await userEvent.click(screen.getByRole("button", { name: "收藏" }));
  expect(patch).toHaveBeenCalledWith("/api/items/1", { isSaved: true });
});

it("404时显示详情不存在", async () => {
  get.mockRejectedValue(new ApiError(404, "情报不存在"));
  renderPage();
  expect(await screen.findByText("情报不存在或已删除")).toBeVisible();
});
```

- [ ] **Step 4: 运行测试确认失败**

Run: `npm test -- --run src/components/ItemCard.test.tsx src/pages/ItemDetail.test.tsx`

Expected: `detailHref`、`ItemDetail`和路由尚不存在而FAIL。

- [ ] **Step 5: 实现情报卡**

`ItemCard`增加`detailHref = \`/items/${item.id}\``参数。删除列表中的`item-reason`，把元信息、标题、摘要和“查看详情”放进独立Link；关键词和操作按钮留在Link外：

```tsx
import { Link } from "wouter";

<article className={`item-card ${item.isRead ? "read" : ""} ${compact ? "compact" : ""}`}>
  <Link className="item-card-link" href={detailHref}>
    <div className="item-meta">
      <span className={`kind-tag ${item.kind}`}>{kindLabels[item.kind]}</span>
      <span>{item.source}</span>
      <time dateTime={date}>{new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(new Date(date))}</time>
      {item.isRead && <span className="read-state">已读</span>}
      <span className="importance" aria-label={`${priority}，重要性${importance}分`}>{priority}</span>
    </div>
    <h2>{item.title}</h2>
    <p className="item-summary">{item.summary || item.reason || "暂无摘要"}</p>
    <span className="card-detail-cue">查看详情</span>
  </Link>
  <div className="item-footer">
    <div className="keyword-row">{item.keywords.slice(0, 3).map((keyword) => <span key={keyword}>{keyword}</span>)}</div>
    <div className="item-actions">
      {onChange && <>
        <button disabled={busy} className={item.isSaved ? "selected" : ""} onClick={() => onChange({ isSaved: !item.isSaved })} aria-label={item.isSaved ? "取消收藏" : "收藏"} title={item.isSaved ? "取消收藏" : "收藏"}><Bookmark size={17} fill={item.isSaved ? "currentColor" : "none"} /></button>
        <button disabled={busy} onClick={() => onChange({ isRead: !item.isRead })} aria-label={item.isRead ? "标记未读" : "标记已读"} title={item.isRead ? "标记未读" : "标记已读"}><Check size={17} /></button>
        <button disabled={busy} onClick={() => onChange({ isIgnored: true })} aria-label="忽略" title="忽略"><EyeOff size={17} /></button>
      </>}
      <a href={item.url} target="_blank" rel="noreferrer" aria-label="打开原文（新窗口）" title="打开原文"><ExternalLink size={17} /></a>
    </div>
  </div>
</article>
```

在`Feed.tsx`生成包含当前查询参数的返回地址，并传给每个卡片：

```tsx
const returnHref = `/feed${searchParams.toString() ? `?${searchParams.toString()}` : ""}`;

{query.data?.items.map((item) => (
  <ItemCard
    key={item.id}
    item={item}
    detailHref={`/items/${item.id}?from=${encodeURIComponent(returnHref)}`}
    busy={update.isPending && update.variables?.id === item.id}
    onChange={(patch) => update.mutate({ id: item.id, patch })}
  />
))}
```

- [ ] **Step 6: 实现情报详情和路由**

创建`ItemDetail.tsx`：

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bookmark, Check, ExternalLink, EyeOff } from "lucide-react";
import { Link, useParams, useSearchParams } from "wouter";

import { api, ApiError } from "../api";
import type { IntelligenceItem } from "../types";

const kindLabels = { news: "热点", paper: "论文", job: "招聘" };

export function ItemDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["item", id], queryFn: () => api.get<IntelligenceItem>(`/api/items/${id}`) });
  const update = useMutation({
    mutationFn: (patch: Partial<Pick<IntelligenceItem, "isRead" | "isSaved" | "isIgnored">>) => api.patch<IntelligenceItem>(`/api/items/${id}`, patch),
    onSuccess: (item) => {
      queryClient.setQueryData(["item", id], item);
      queryClient.invalidateQueries({ queryKey: ["items"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  const backHref = searchParams.get("from") || "/feed";

  if (query.isPending) return <div className="detail-skeleton" aria-label="正在加载情报" />;
  if (query.error instanceof ApiError && query.error.status === 404) return <div className="empty-state"><p>情报不存在或已删除</p><Link className="secondary-link" href={backHref}>返回情报列表</Link></div>;
  if (query.isError) return <div className="inline-error" role="alert">情报加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>;

  const item = query.data;
  const date = item.publishedAt ?? item.createdAt;
  const busy = update.isPending;
  return <article className="detail-page">
    <Link className="detail-back" href={backHref}><ArrowLeft size={17} />返回情报列表</Link>
    <div className="detail-copy">
      <div className="detail-meta"><span className={`kind-tag ${item.kind}`}>{kindLabels[item.kind]}</span><span>{item.source}</span><time dateTime={date}>{new Date(date).toLocaleString("zh-CN")}</time><span>{Math.round(item.importance * 100)}分</span></div>
      <h2>{item.title}</h2>
      <p className="detail-summary">{item.summary || "暂无摘要"}</p>
      <section className="detail-reason" aria-labelledby="reason-heading"><h3 id="reason-heading">值得关注</h3><p>{item.reason}</p></section>
      <div className="keyword-row">{item.keywords.map((keyword) => <span key={keyword}>{keyword}</span>)}</div>
    </div>
    {update.isError && <div className="action-notice error" role="alert">操作未完成，请重试</div>}
    <div className="detail-actions">
      <button disabled={busy} onClick={() => update.mutate({ isSaved: !item.isSaved })}><Bookmark size={17} fill={item.isSaved ? "currentColor" : "none"} />{item.isSaved ? "取消收藏" : "收藏"}</button>
      <button disabled={busy} onClick={() => update.mutate({ isRead: !item.isRead })}><Check size={17} />{item.isRead ? "标记未读" : "标记已读"}</button>
      <button disabled={busy} onClick={() => update.mutate({ isIgnored: true })}><EyeOff size={17} />忽略</button>
      <a className="primary-compact" href={item.url} target="_blank" rel="noreferrer"><ExternalLink size={17} />打开原文（新窗口）</a>
    </div>
  </article>;
}
```

在`AppShell.tsx`引入`ItemDetail`，在`/feed`之前注册：

```tsx
<Route path="/items/:id" component={ItemDetail} />
```

页面标题函数增加：

```tsx
function pageName(location: string) {
  if (location.startsWith("/items/")) return "情报详情";
  return pageNames[location] ?? "今日情报";
}
```

- [ ] **Step 7: 增加基础样式并运行测试**

在`styles.css`增加`.item-card-link`、`.card-detail-cue`、`.detail-page`、`.detail-header`、`.detail-copy`和`.detail-actions`。摘要使用两行截断：

```css
.item-summary {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.item-card-link { display:block; color:inherit; text-decoration:none; border-radius:8px; }
.item-card-link:hover h2, .item-card-link:focus-visible h2 { color:var(--signal); }
.detail-page { width:100%; max-width:820px; margin:0 auto; display:grid; gap:18px; }
.detail-copy { padding:20px; border:1px solid var(--line); border-radius:12px; background:var(--paper); }
```

Run: `npm test -- --run src/components/ItemCard.test.tsx src/pages/ItemDetail.test.tsx`

Expected: 全部PASS。

- [ ] **Step 8: 提交**

```powershell
git add frontend/src/components/ItemCard.tsx frontend/src/components/ItemCard.test.tsx frontend/src/pages/ItemDetail.tsx frontend/src/pages/ItemDetail.test.tsx frontend/src/components/AppShell.tsx frontend/src/styles.css
git commit -m "feat: add intelligence detail experience"
```

### Task 4: 将报告改为摘要卡片和独立详情页

**Files:**
- Create: `frontend/src/components/BriefingCard.tsx`
- Create: `frontend/src/components/BriefingCard.test.tsx`
- Modify: `frontend/src/pages/Reports.tsx`
- Modify: `frontend/src/pages/Reports.test.tsx`
- Create: `frontend/src/pages/BriefingDetail.tsx`
- Create: `frontend/src/pages/BriefingDetail.test.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: 写报告卡失败测试**

创建`BriefingCard.test.tsx`：

```tsx
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { BriefingCard } from "./BriefingCard";

const briefing = {
  id: 2, subscriptionId: 1, title: "微信整理 · 今日AI热点简报", kind: "news" as const,
  content: "第一段。\n\n第二段包含更完整的分析。", itemCount: 3,
  periodStart: null, periodEnd: null, createdAt: "2026-08-01T08:00:00Z",
};

it("展示标题、纯文本摘要和详情链接", () => {
  render(<BriefingCard briefing={briefing} detailHref="/reports/2?from=%2Freports" />);
  expect(screen.getByRole("link", { name: /微信整理 · 今日AI热点简报/ })).toHaveAttribute("href", "/reports/2?from=%2Freports");
  expect(screen.getByText("第一段。 第二段包含更完整的分析。")).toHaveClass("briefing-summary");
  expect(screen.getByText("3条情报")).toBeVisible();
});
```

- [ ] **Step 2: 改写报告列表失败测试**

把`Reports.test.tsx`测试改为：

```tsx
it("只展示摘要卡并进入独立报告详情", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Reports />
    </QueryClientProvider>,
  );

  expect(await screen.findByRole("link", { name: /微信整理 · 今日AI热点简报/ })).toHaveAttribute("href", "/reports/1?from=%2Freports");
  expect(screen.getByText("这是最新简报正文。")).toHaveClass("briefing-summary");
  expect(screen.queryByRole("article", { name: "报告正文" })).not.toBeInTheDocument();
});
```

- [ ] **Step 3: 写报告详情失败测试**

创建`BriefingDetail.test.tsx`：

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../api";
import { BriefingDetail } from "./BriefingDetail";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  api: { get },
}));

const briefing = {
  id: 1, subscriptionId: 1, title: "微信整理 · 今日AI热点简报", kind: "news",
  content: "这是完整报告正文。", itemCount: 3,
  periodStart: "2026-07-31T00:00:00Z", periodEnd: "2026-08-01T00:00:00Z", createdAt: "2026-08-01T08:00:00Z",
};

beforeEach(() => {
  window.history.pushState({}, "", "/reports/1?from=%2Freports");
  get.mockReset().mockResolvedValue(briefing);
});

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <BriefingDetail />
    </QueryClientProvider>,
  );
}

it("加载完整报告并返回列表", async () => {
  renderPage();
  expect(await screen.findByRole("heading", { name: "微信整理 · 今日AI热点简报" })).toBeVisible();
  expect(get).toHaveBeenCalledWith("/api/briefings/1");
  expect(screen.getByText("这是完整报告正文。")).toBeVisible();
  expect(screen.getByRole("link", { name: "返回报告列表" })).toHaveAttribute("href", "/reports");
});

it("404时显示报告不存在", async () => {
  get.mockRejectedValue(new ApiError(404, "简报不存在"));
  renderPage();
  expect(await screen.findByText("报告不存在或已删除")).toBeVisible();
});
```

- [ ] **Step 4: 运行测试确认失败**

Run:

```powershell
npm test -- --run src/components/BriefingCard.test.tsx src/pages/Reports.test.tsx src/pages/BriefingDetail.test.tsx
```

Expected: 新组件和详情页不存在，现有Reports仍为分栏，测试FAIL。

- [ ] **Step 5: 实现BriefingCard和Reports列表**

创建`BriefingCard.tsx`，规范正文空白并显示元信息、标题、两行摘要和详情提示。

```tsx
import { Link } from "wouter";
import type { Briefing } from "../types";

const kindLabels = { news: "热点", paper: "论文", job: "招聘" };

export function BriefingCard({ briefing, detailHref = `/reports/${briefing.id}` }: { briefing: Briefing; detailHref?: string }) {
  const summary = briefing.content.replace(/\s+/g, " ").trim() || "暂无摘要";
  return <article className="briefing-card">
    <Link className="briefing-card-link" href={detailHref}>
      <div className="briefing-meta"><span className={`kind-tag ${briefing.kind}`}>{kindLabels[briefing.kind]}</span><time>{new Date(briefing.createdAt).toLocaleDateString("zh-CN")}</time><span>{briefing.itemCount}条情报</span></div>
      <h2>{briefing.title}</h2>
      <p className="briefing-summary">{summary}</p>
      <span className="card-detail-cue">查看报告</span>
    </Link>
  </article>;
}
```

`Reports.tsx`删除`selected`状态、左右分栏和`FileText/ChevronRight`，改为：

```tsx
<div className="briefing-list">
  {query.data.items.map((briefing) => (
    <BriefingCard key={briefing.id} briefing={briefing} detailHref={`/reports/${briefing.id}?from=${encodeURIComponent("/reports")}`} />
  ))}
</div>
```

- [ ] **Step 6: 实现报告详情和路由**

创建`BriefingDetail.tsx`：

```tsx
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams, useSearchParams } from "wouter";

import { api, ApiError } from "../api";
import type { Briefing } from "../types";

const kindLabels = { news: "热点", paper: "论文", job: "招聘" };

export function BriefingDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const query = useQuery({ queryKey: ["briefing", id], queryFn: () => api.get<Briefing>(`/api/briefings/${id}`) });
  const backHref = searchParams.get("from") || "/reports";

  if (query.isPending) return <div className="detail-skeleton" aria-label="正在加载报告" />;
  if (query.error instanceof ApiError && query.error.status === 404) return <div className="empty-state"><p>报告不存在或已删除</p><Link className="secondary-link" href={backHref}>返回报告列表</Link></div>;
  if (query.isError) return <div className="inline-error" role="alert">报告加载失败。<button onClick={() => query.refetch()}>重新加载</button></div>;

  const report = query.data;
  return <article className="detail-page">
    <Link className="detail-back" href={backHref}><ArrowLeft size={17} />返回报告列表</Link>
    <div className="detail-copy">
      <div className="detail-meta"><span className={`kind-tag ${report.kind}`}>{kindLabels[report.kind]}</span><time>{new Date(report.createdAt).toLocaleString("zh-CN")}</time><span>{report.itemCount}条情报</span></div>
      <h2>{report.title}</h2>
      {(report.periodStart || report.periodEnd) && <p className="report-period">覆盖时间：{report.periodStart ? new Date(report.periodStart).toLocaleDateString("zh-CN") : "未指定"}—{report.periodEnd ? new Date(report.periodEnd).toLocaleDateString("zh-CN") : "未指定"}</p>}
      <p className="report-body">{report.content}</p>
    </div>
  </article>;
}
```

在`AppShell.tsx`注册`/reports/:id`，必须位于`/reports`之前；`pageName`对`/reports/`返回“报告详情”。

- [ ] **Step 7: 样式、测试和提交**

删除不再使用的`.report-layout`分栏规则，增加：

```css
.briefing-list { display:grid; gap:10px; }
.briefing-card { border:1px solid var(--line); border-radius:12px; background:var(--paper); }
.briefing-card-link { display:block; padding:16px; border-radius:12px; color:inherit; text-decoration:none; }
.briefing-card-link:hover h2, .briefing-card-link:focus-visible h2 { color:var(--signal); }
.briefing-card h2 { margin:10px 0 7px; font-size:17px; line-height:1.45; overflow-wrap:anywhere; }
.briefing-meta, .detail-meta { display:flex; flex-wrap:wrap; align-items:center; gap:8px; color:var(--muted); font-size:12px; }
.briefing-summary { margin:0; display:-webkit-box; overflow:hidden; -webkit-box-orient:vertical; -webkit-line-clamp:2; color:#46514c; font-size:14px; line-height:1.7; }
.report-body { margin:18px 0 0; color:#35413b; line-height:1.9; white-space:pre-wrap; overflow-wrap:anywhere; }
.report-period { color:var(--muted); font-size:13px; }
```

Run: `npm test -- --run src/components/BriefingCard.test.tsx src/pages/Reports.test.tsx src/pages/BriefingDetail.test.tsx`

Expected: 全部PASS。

```powershell
git add frontend/src/components/BriefingCard.tsx frontend/src/components/BriefingCard.test.tsx frontend/src/pages/Reports.tsx frontend/src/pages/Reports.test.tsx frontend/src/pages/BriefingDetail.tsx frontend/src/pages/BriefingDetail.test.tsx frontend/src/components/AppShell.tsx frontend/src/styles.css
git commit -m "feat: add report cards and detail pages"
```

### Task 5: 把首页全部入口连接到筛选和详情

**Files:**
- Modify: `frontend/src/pages/Home.tsx`
- Create: `frontend/src/pages/Home.test.tsx`
- Modify: `frontend/src/components/ItemCard.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: 写首页导航失败测试**

创建`Home.test.tsx`：

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { Home } from "./Home";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../api", () => ({ api: { get } }));

beforeEach(() => {
  get.mockReset().mockResolvedValue({
    unreadCount: 1,
    savedCount: 2,
    activeSubscriptions: 3,
    failedRuns: 4,
    topItems: [{
      id: 1, subscriptionId: 1, kind: "news", title: "Agent框架发布新版本",
      summary: "工具调用可靠性提升。", url: "https://example.com", source: "Example",
      publishedAt: "2026-08-01T00:00:00Z", keywords: ["Agent"], reason: "值得跟踪",
      importance: 0.9, isRead: false, isSaved: false, isIgnored: false, createdAt: "2026-08-01T00:00:00Z",
    }],
    latestBriefing: {
      id: 2, subscriptionId: 1, title: "微信整理 · 今日AI热点简报", kind: "news",
      content: "这是最新简报正文。", itemCount: 3,
      periodStart: null, periodEnd: null, createdAt: "2026-08-01T08:00:00Z",
    },
  });
});

it("统计卡和内容卡进入对应筛选或详情", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Home />
    </QueryClientProvider>,
  );

  expect(await screen.findByRole("link", { name: /1 待阅读/ })).toHaveAttribute("href", "/feed?state=unread");
  expect(screen.getByRole("link", { name: /2 已收藏/ })).toHaveAttribute("href", "/feed?state=saved");
  expect(screen.getByRole("link", { name: /3 运行订阅/ })).toHaveAttribute("href", "/settings");
  expect(screen.getByRole("link", { name: /4 异常任务/ })).toHaveAttribute("href", "/tasks?status=failed");
  expect(screen.getByRole("link", { name: /Agent框架发布新版本/ })).toHaveAttribute("href", "/items/1?from=%2F");
  expect(screen.getByRole("link", { name: /微信整理 · 今日AI热点简报/ })).toHaveAttribute("href", "/reports/2?from=%2F");
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test -- --run src/pages/Home.test.tsx`

Expected: 统计卡仍是`div`，最新简报没有详情链接，测试FAIL。

- [ ] **Step 3: 实现首页入口**

给metrics增加`href`：

```tsx
const metrics = [
  { label: "待阅读", value: data.unreadCount, icon: Radio, tone: "green", href: "/feed?state=unread" },
  { label: "已收藏", value: data.savedCount, icon: Bookmark, tone: "blue", href: "/feed?state=saved" },
  { label: "运行订阅", value: data.activeSubscriptions, icon: Activity, tone: "amber", href: "/settings" },
  { label: "异常任务", value: data.failedRuns, icon: TriangleAlert, tone: "coral", href: "/tasks?status=failed" },
];
```

每个metric用`<Link className={\`metric ${tone}\`} href={href}>`渲染。首页topItems传入`detailHref={\`/items/${item.id}?from=${encodeURIComponent("/")}\`}`；最新简报改用`BriefingCard`，传入对应详情URL。

- [ ] **Step 4: 增加统计入口样式并测试**

`.metric`增加`color:inherit;text-decoration:none`，并为`:hover`和`:focus-visible`增加边框与轻微背景反馈；不增加位移动画。

Run: `npm test -- --run src/pages/Home.test.tsx src/components/ItemCard.test.tsx src/components/BriefingCard.test.tsx`

Expected: 全部PASS。

- [ ] **Step 5: 提交**

```powershell
git add frontend/src/pages/Home.tsx frontend/src/pages/Home.test.tsx frontend/src/components/ItemCard.tsx frontend/src/styles.css
git commit -m "feat: connect dashboard cards to details"
```

### Task 6: 完成错误状态、响应式样式与回归验证

**Files:**
- Modify only if verification reveals a defect: `frontend/src/styles.css`
- Modify only if detector reveals a defect: changed frontend files from Tasks 2-5

- [ ] **Step 1: 检查动态路由和未知路由**

在`App.test.tsx`增加页面mock，并把测试整理为：

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";

vi.mock("./pages/ItemDetail", () => ({ ItemDetail: () => <p>情报详情内容</p> }));
vi.mock("./pages/BriefingDetail", () => ({ BriefingDetail: () => <p>报告详情内容</p> }));

afterEach(cleanup);

function renderApp(path: string) {
  window.history.pushState({}, "", path);
  return render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);
}

test("直接显示应用，即使地址为/login", () => {
  renderApp("/login");
  expect(screen.getByRole("heading", { name: "今日情报" })).toBeVisible();
  expect(screen.queryByText("登录")).not.toBeInTheDocument();
});

test("情报详情路由显示正确顶栏标题", () => {
  renderApp("/items/1");
  expect(screen.getByRole("heading", { name: "情报详情" })).toBeVisible();
  expect(screen.getByText("情报详情内容")).toBeVisible();
});

test("报告详情路由显示正确顶栏标题", () => {
  renderApp("/reports/1");
  expect(screen.getByRole("heading", { name: "报告详情" })).toBeVisible();
  expect(screen.getByText("报告详情内容")).toBeVisible();
});
```

Run: `npm test -- --run src/App.test.tsx`

Expected: 三种路由行为全部PASS。

- [ ] **Step 2: 运行后端全量测试**

Run:

```powershell
cd backend
uv run pytest -v
```

Expected: 全部PASS。

- [ ] **Step 3: 运行前端全量测试、构建和审计**

Run:

```powershell
cd ../frontend
npm test -- --run
npm run build
npm audit --omit=dev
```

Expected: 测试和构建PASS，生产依赖0个漏洞。

- [ ] **Step 4: 运行Impeccable机械检测**

仅在UI完成后运行一次：

```powershell
node C:\Users\z2986\.codex\skills\impeccable\scripts\detect.mjs --json frontend/src/components/ItemCard.tsx frontend/src/components/BriefingCard.tsx frontend/src/pages/Home.tsx frontend/src/pages/Feed.tsx frontend/src/pages/Reports.tsx frontend/src/pages/ItemDetail.tsx frontend/src/pages/BriefingDetail.tsx frontend/src/components/AppShell.tsx frontend/src/styles.css
```

Expected: 无必须修复的可访问性、层级或模板化UI问题。一次性修复所有确认问题后，不重复开放式打磨。

- [ ] **Step 5: 桌面和移动端视觉检查**

启动本地前后端，使用真实演示数据一次性截取：首页、情报列表、情报详情、报告列表、报告详情的桌面宽度和390px移动宽度。集中检查：两行摘要、长标题换行、焦点可见、操作区不误触、详情正文宽度、底部导航遮挡和404状态。

Expected: 一轮检查后批量修复确认问题，最多再进行一轮确认。

- [ ] **Step 6: 最终Git检查和提交**

Run:

```powershell
git diff --check
git status --short
```

Expected: 无空白错误，只有本任务确认的文件。

若Task 6产生修正：

```powershell
git add frontend/src frontend/src/styles.css
git commit -m "fix: polish list and detail experience"
```

若没有修正则不创建空提交。
