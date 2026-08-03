import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Reports } from "./Reports";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../api", () => ({ api: { get } }));

beforeEach(() => {
  window.history.pushState({}, "", "/reports");
  get.mockReset().mockResolvedValue({
    items: [{
      id: 1,
      subscriptionId: 1,
      title: "微信整理 · 今日AI热点简报",
      kind: "news",
      content: "这是最新简报正文。",
      itemCount: 3,
      periodStart: null,
      periodEnd: null,
      createdAt: "2026-08-01T08:00:00Z",
    }],
    total: 1,
    limit: 20,
    offset: 0,
  });
});

afterEach(cleanup);

it("只展示摘要卡并进入独立报告详情", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Reports />
    </QueryClientProvider>,
  );

  expect(await screen.findByRole("link", { name: /微信整理 · 今日AI热点简报/ })).toHaveAttribute("href", "/reports/1?from=%2Freports");
  expect(get).toHaveBeenCalledWith("/api/briefings?limit=20&offset=0");
  expect(screen.getByText("这是最新简报正文。")).toHaveClass("briefing-summary");
  expect(screen.getByText("引用3条情报")).toBeVisible();
  expect(screen.queryByRole("article", { name: "报告正文" })).not.toBeInTheDocument();
});

it("搜索并组合报告分类和时间筛选", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Reports />
    </QueryClientProvider>,
  );

  await screen.findByText("微信整理 · 今日AI热点简报");
  await userEvent.type(screen.getByRole("searchbox", { name: "搜索报告" }), "Agent");
  await waitFor(() => expect(get).toHaveBeenLastCalledWith("/api/briefings?limit=20&offset=0&q=Agent"));
  await userEvent.click(screen.getByRole("button", { name: "论文" }));
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "报告时间" }), "7");
  await waitFor(() => expect(get).toHaveBeenLastCalledWith("/api/briefings?limit=20&offset=0&kind=paper&days=7&q=Agent"));
});

it("翻页时保留报告视图状态", async () => {
  get.mockResolvedValue({
    items: [{ id: 21, subscriptionId: 1, title: "较早报告", kind: "news", content: "正文", itemCount: 1, periodStart: null, periodEnd: null, createdAt: "2026-07-01T08:00:00Z" }],
    total: 21,
    limit: 20,
    offset: 0,
  });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Reports />
    </QueryClientProvider>,
  );

  await screen.findByText("较早报告");
  await userEvent.click(screen.getByRole("button", { name: /下一页/ }));
  await waitFor(() => expect(get).toHaveBeenLastCalledWith("/api/briefings?limit=20&offset=20"));
  expect(window.location.search).toBe("?page=2");
});
