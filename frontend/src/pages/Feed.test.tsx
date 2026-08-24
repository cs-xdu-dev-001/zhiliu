import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Feed } from "./Feed";

const { get, patch, post, put, remove } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), post: vi.fn(), put: vi.fn(), remove: vi.fn() }));
vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  api: { get, patch, post, put, delete: remove },
}));

afterEach(cleanup);

beforeEach(() => {
  window.history.pushState({}, "", "/feed");
  const itemPage = {
    items: [{
      id: 1, subscriptionId: 1, kind: "news", title: "Agent框架发布新版本",
      summary: "工具调用可靠性提升。", url: "https://example.com", source: "Example",
      publishedAt: "2026-08-01T00:00:00Z", keywords: ["Agent"], reason: "值得跟踪",
      importance: 0.9, isRead: false, isSaved: false, isIgnored: false, createdAt: "2026-08-01T00:00:00Z",
      isInvalid: false, mergedIntoId: null,
    }], total: 1, limit: 30, offset: 0,
  };
  get.mockReset().mockImplementation((url: string) => Promise.resolve(
    url === "/api/items/sources" || url === "/api/tags" || url === "/api/saved-views" ? [] : itemPage,
  ));
  patch.mockReset().mockResolvedValue({});
  put.mockReset().mockResolvedValue({});
  remove.mockReset().mockResolvedValue(undefined);
  post.mockReset().mockResolvedValue({ operationId: 1, requested: 1, updated: 1, updatedIds: [1], skipped: [], duplicate: false });
});

it("可以将情报标记为已读", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  await userEvent.click(screen.getByRole("button", { name: "标记已读" }));

  expect(patch).toHaveBeenCalledWith("/api/items/1", { isRead: true });
  expect(await screen.findByRole("status")).toHaveTextContent("已标记为已读");
});

it("忽略情报后可以立即撤销", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  await userEvent.click(screen.getByRole("button", { name: "忽略" }));
  expect(patch).toHaveBeenCalledWith("/api/items/1", { isIgnored: true });
  expect(await screen.findByRole("status")).toHaveTextContent("已忽略，可随时撤销");

  await userEvent.click(screen.getByRole("button", { name: "撤销忽略" }));
  expect(patch).toHaveBeenLastCalledWith("/api/items/1", { isIgnored: false });
  expect(await screen.findByRole("status")).toHaveTextContent("已取消忽略");
});

it("筛选无结果时可以清除筛选", async () => {
  get.mockResolvedValue({ items: [], total: 0, limit: 30, offset: 0 });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  expect(await screen.findByRole("status", { name: "当前筛选下没有情报" })).toHaveClass("compact");
  await userEvent.click(screen.getByRole("button", { name: "清除筛选" }));

  expect(screen.getByRole("button", { name: "全部" })).toHaveClass("active");
  expect(screen.getByRole("checkbox", { name: "未读" })).toBeChecked();
});

it("从URL读取筛选并在修改时更新URL", async () => {
  window.history.pushState({}, "", "/feed?state=saved&kind=paper");
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  expect(get).toHaveBeenCalledWith("/api/items?state=saved&sort=importance&limit=20&offset=0&kind=paper");
  expect(screen.getByRole("button", { name: "论文" })).toHaveClass("active");
  expect(screen.getByRole("checkbox", { name: "收藏" })).toBeChecked();

  await userEvent.click(screen.getByRole("button", { name: "热点" }));
  expect(window.location.search).toBe("?state=saved&kind=news");
});

it("忽略非法URL筛选且不会注入额外查询参数", async () => {
  window.history.pushState({}, "", "/feed?state=bogus&kind=a%26state%3Dignored");
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  expect(get).toHaveBeenCalledWith("/api/items?state=unread&sort=importance&limit=20&offset=0");
  expect(screen.getByRole("button", { name: "全部" })).toHaveClass("active");
  expect(screen.getByRole("checkbox", { name: "未读" })).toBeChecked();
});

it("可以查看无效情报", async () => {
  window.history.pushState({}, "", "/feed?state=invalid");
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  expect(get).toHaveBeenCalledWith("/api/items?state=invalid&sort=importance&limit=20&offset=0");
  expect(screen.getByRole("checkbox", { name: "无效" })).toBeChecked();
});

it("搜索防抖后写入URL并请求最终关键词", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  const input = await screen.findByRole("searchbox", { name: "搜索情报" });
  await userEvent.type(input, "Agent更新");

  await vi.waitFor(() => expect(get).toHaveBeenLastCalledWith(
    "/api/items?state=unread&sort=importance&limit=20&offset=0&q=Agent%E6%9B%B4%E6%96%B0",
  ));
  expect(window.location.search).toContain("q=Agent%E6%9B%B4%E6%96%B0");
});

it("可以排序且保留现有筛选", async () => {
  window.history.pushState({}, "", "/feed?state=saved&kind=paper");
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "情报排序" }), "newest");

  expect(window.location.search).toBe("?state=saved&kind=paper&sort=newest");
  expect(get).toHaveBeenLastCalledWith("/api/items?state=saved&sort=newest&limit=20&offset=0&kind=paper");
});

it("可以组合多个状态并筛选多个标签", async () => {
  window.history.pushState({}, "", "/feed?state=unread&state=saved&tag=Agent&tag=%E9%87%8D%E7%82%B9");
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  expect(get).toHaveBeenCalledWith(
    "/api/items?state=unread&state=saved&tag=Agent&tag=%E9%87%8D%E7%82%B9&sort=importance&limit=20&offset=0",
  );
  expect(screen.getByRole("checkbox", { name: "未读" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "收藏" })).toBeChecked();
});

it("可以保存、应用和删除筛选视图", async () => {
  const view = { id: 7, name: "待读论文", query: "state=unread&kind=paper", createdAt: "", updatedAt: "" };
  get.mockImplementation((url: string) => Promise.resolve(
    url === "/api/saved-views" ? [view]
      : url === "/api/items/sources" || url === "/api/tags" ? []
        : { items: [], total: 0, limit: 20, offset: 0 },
  ));
  post.mockResolvedValueOnce(view);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByRole("button", { name: "待读论文" });
  await userEvent.click(screen.getByRole("button", { name: "待读论文" }));
  expect(window.location.search).toBe("?state=unread&kind=paper");
  await userEvent.click(screen.getByRole("button", { name: "保存当前筛选" }));
  await userEvent.type(screen.getByRole("textbox", { name: "视图名称" }), "论文重点");
  await userEvent.click(screen.getByRole("button", { name: "保存" }));
  expect(post).toHaveBeenCalledWith("/api/saved-views", { name: "论文重点", query: "state=unread&kind=paper" });
  await userEvent.click(screen.getByRole("button", { name: "删除视图待读论文" }));
  expect(remove).toHaveBeenCalledWith("/api/saved-views/7");
});

it("可以筛选可能过期的情报", async () => {
  window.history.pushState({}, "", "/feed?state=stale");
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  expect(get).toHaveBeenCalledWith("/api/items?state=stale&sort=importance&limit=20&offset=0");
  expect(screen.getByRole("checkbox", { name: "可能过期" })).toBeChecked();
});

it("可以筛选低优先级情报", async () => {
  window.history.pushState({}, "", "/feed?state=low");
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  expect(get).toHaveBeenCalledWith("/api/items?state=low&sort=importance&limit=20&offset=0");
  expect(screen.getByRole("checkbox", { name: "低优先级" })).toBeChecked();
});

it("可以筛选原文失效情报", async () => {
  window.history.pushState({}, "", "/feed?state=source-unavailable");
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  expect(get).toHaveBeenCalledWith("/api/items?state=source-unavailable&sort=importance&limit=20&offset=0");
  expect(screen.getByRole("checkbox", { name: "原文失效" })).toBeChecked();
});

it("按时间范围筛选并保留在URL中", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "情报时间" }), "30");

  expect(window.location.search).toBe("?state=unread&days=30");
  expect(get).toHaveBeenLastCalledWith("/api/items?state=unread&sort=importance&limit=20&offset=0&days=30");
});

it("按精确来源筛选并保留在URL中", async () => {
  const itemPage = {
    items: [{
      id: 1, subscriptionId: 1, kind: "news", title: "Agent框架发布新版本", summary: "工具调用可靠性提升。", url: "https://example.com", source: "Example", publishedAt: "2026-08-01T00:00:00Z", keywords: ["Agent"], reason: "值得跟踪", importance: 0.9, isRead: false, isSaved: false, isIgnored: false, createdAt: "2026-08-01T00:00:00Z", isInvalid: false, mergedIntoId: null,
    }], total: 1, limit: 20, offset: 0,
  };
  get.mockImplementation((url: string) => Promise.resolve(url === "/api/items/sources" ? ["Example", "arXiv"] : itemPage));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "情报来源" }), "Example");

  expect(window.location.search).toBe("?state=unread&source=Example");
  expect(get).toHaveBeenCalledWith("/api/items?state=unread&sort=importance&limit=20&offset=0&source=Example");
});

it("选择当前页情报并批量收藏", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  await userEvent.click(screen.getByRole("button", { name: "批量选择" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "选择Agent框架发布新版本" }));
  await userEvent.click(screen.getByRole("button", { name: "收藏所选" }));

  expect(post).toHaveBeenCalledWith("/api/items/bulk", expect.objectContaining({ ids: [1], action: "save", idempotencyKey: expect.any(String) }));
  expect(await screen.findByRole("status")).toHaveTextContent("已处理1条");
});

it("批量操作成功后可以按实际改动撤销", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  await userEvent.click(screen.getByRole("button", { name: "批量选择" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "选择Agent框架发布新版本" }));
  await userEvent.click(screen.getByRole("button", { name: "收藏所选" }));
  await userEvent.click(await screen.findByRole("button", { name: "撤销" }));

  expect(post).toHaveBeenLastCalledWith("/api/items/bulk", expect.objectContaining({ ids: [1], action: "unsave", idempotencyKey: expect.any(String) }));
});

it("可以为所选情报批量添加标签", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  await userEvent.click(screen.getByRole("button", { name: "批量选择" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "选择Agent框架发布新版本" }));
  await userEvent.click(screen.getByLabelText("批量标签"));
  await userEvent.type(screen.getByRole("textbox", { name: "批量标签内容" }), "重点，Agent");
  await userEvent.click(screen.getByRole("button", { name: "添加" }));

  expect(post).toHaveBeenCalledWith("/api/items/bulk", expect.objectContaining({ ids: [1], action: "tag", tags: ["重点", "Agent"] }));
});

it("批量忽略需要内联确认", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  await userEvent.click(screen.getByRole("button", { name: "批量选择" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "选择Agent框架发布新版本" }));
  await userEvent.click(screen.getByRole("button", { name: "归档所选" }));
  expect(screen.getByText("将1条情报归档？")).toBeVisible();
  expect(post).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "确认归档" }));
  expect(post).toHaveBeenCalledWith("/api/items/bulk", expect.objectContaining({ ids: [1], action: "ignore", idempotencyKey: expect.any(String) }));
});

it("可以把所选情报交给Hermes生成报告", async () => {
  post.mockResolvedValueOnce({ id: 31 });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  await userEvent.click(screen.getByRole("button", { name: "批量选择" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "选择Agent框架发布新版本" }));
  await userEvent.click(screen.getByRole("button", { name: "生成报告" }));
  await userEvent.type(screen.getByRole("textbox", { name: "整理要求" }), "突出研究影响");
  await userEvent.click(screen.getByRole("button", { name: "交给Hermes" }));

  expect(post).toHaveBeenCalledWith("/api/briefings/generate", {
    itemIds: [1],
    instruction: "突出研究影响",
    requestId: expect.any(String),
  });
  expect(window.location.pathname).toBe("/tasks/31");
});

it("报告任务失败后重试沿用请求标识并恢复触发焦点", async () => {
  post.mockRejectedValue(new Error("服务暂时不可用"));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent框架发布新版本");
  await userEvent.click(screen.getByRole("button", { name: "批量选择" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "选择Agent框架发布新版本" }));
  const trigger = screen.getByRole("button", { name: "生成报告" });
  await userEvent.click(trigger);
  await waitFor(() => expect(screen.getByRole("textbox", { name: "整理要求" })).toHaveFocus());
  await userEvent.click(screen.getByRole("button", { name: "交给Hermes" }));
  expect(await screen.findByText(/所选内容已保留，可直接重试/)).toBeVisible();
  const firstRequestId = post.mock.calls[0][1].requestId;
  await userEvent.click(screen.getByRole("button", { name: "重试创建" }));
  expect(post.mock.calls[1][1].requestId).toBe(firstRequestId);
  await userEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(trigger).toHaveFocus();
});

it("可以翻到下一页", async () => {
  get.mockResolvedValue({ items: [], total: 45, limit: 20, offset: 0 });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("45条情报");
  await userEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect(window.location.search).toBe("?state=unread&page=2");
  expect(get).toHaveBeenLastCalledWith("/api/items?state=unread&sort=importance&limit=20&offset=20");
});
