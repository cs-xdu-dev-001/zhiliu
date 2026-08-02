import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Feed } from "./Feed";

const { get, patch } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));
vi.mock("../api", () => ({ api: { get, patch } }));

afterEach(cleanup);

beforeEach(() => {
  window.history.pushState({}, "", "/feed");
  get.mockReset().mockResolvedValue({
    items: [{
      id: 1, subscriptionId: 1, kind: "news", title: "Agent框架发布新版本",
      summary: "工具调用可靠性提升。", url: "https://example.com", source: "Example",
      publishedAt: "2026-08-01T00:00:00Z", keywords: ["Agent"], reason: "值得跟踪",
      importance: 0.9, isRead: false, isSaved: false, isIgnored: false, createdAt: "2026-08-01T00:00:00Z",
    }], total: 1, limit: 30, offset: 0,
  });
  patch.mockReset().mockResolvedValue({});
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
  expect(get).toHaveBeenCalledWith("/api/items?state=saved&kind=paper");
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
  expect(get).toHaveBeenCalledWith("/api/items?state=unread");
  expect(screen.getByRole("button", { name: "全部" })).toHaveClass("active");
  expect(screen.getByRole("combobox", { name: "情报状态" })).toHaveValue("unread");
});
