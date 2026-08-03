import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Feed } from "./Feed";

const { get, patch, post } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), post: vi.fn() }));
vi.mock("../api", () => ({ api: { get, patch, post } }));

afterEach(cleanup);

beforeEach(() => {
  window.history.pushState({}, "", "/feed");
  get.mockReset().mockResolvedValue({
    items: [{
      id: 1, subscriptionId: 1, kind: "news", title: "Agent框架发布新版本",
      summary: "工具调用可靠性提升。", url: "https://example.com", source: "Example",
      publishedAt: "2026-08-01T00:00:00Z", keywords: ["Agent"], reason: "值得跟踪",
      importance: 0.9, isRead: false, isSaved: false, isIgnored: false, createdAt: "2026-08-01T00:00:00Z",
      isInvalid: false, mergedIntoId: null,
    }], total: 1, limit: 30, offset: 0,
  });
  patch.mockReset().mockResolvedValue({});
  post.mockReset().mockResolvedValue({ requested: 1, updated: 1, skipped: [] });
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

it("筛选无结果时可以清除筛选", async () => {
  get.mockResolvedValue({ items: [], total: 0, limit: 30, offset: 0 });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Feed />
    </QueryClientProvider>,
  );

  await screen.findByText("当前筛选下没有情报");
  await userEvent.click(screen.getByRole("button", { name: "清除筛选" }));

  expect(screen.getByRole("button", { name: "全部" })).toHaveClass("active");
  expect(screen.getByRole("combobox", { name: "情报状态" })).toHaveValue("unread");
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
  expect(screen.getByRole("combobox", { name: "情报状态" })).toHaveValue("saved");

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
  expect(screen.getByRole("combobox", { name: "情报状态" })).toHaveValue("unread");
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
  expect(screen.getByRole("combobox", { name: "情报状态" })).toHaveValue("invalid");
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

  expect(post).toHaveBeenCalledWith("/api/items/bulk", { ids: [1], action: "save" });
  expect(await screen.findByRole("status")).toHaveTextContent("已处理1条");
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
  await userEvent.click(screen.getByRole("button", { name: "忽略所选" }));
  expect(screen.getByText("将1条情报移到已忽略？")).toBeVisible();
  expect(post).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "确认忽略" }));
  expect(post).toHaveBeenCalledWith("/api/items/bulk", { ids: [1], action: "ignore" });
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
