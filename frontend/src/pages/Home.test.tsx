import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

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

afterEach(cleanup);

it("统计卡和内容卡进入对应筛选或详情", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Home />
    </QueryClientProvider>,
  );

  expect(await screen.findByRole("link", { name: /1\s*待阅读/ })).toHaveAttribute("href", "/feed?state=unread");
  expect(screen.getByRole("link", { name: /2\s*已收藏/ })).toHaveAttribute("href", "/feed?state=saved");
  expect(screen.getByRole("link", { name: /3\s*运行订阅/ })).toHaveAttribute("href", "/settings");
  expect(screen.getByRole("link", { name: /4\s*异常任务/ })).toHaveAttribute("href", "/tasks?status=failed");
  expect(screen.getByRole("link", { name: /Agent框架发布新版本/ })).toHaveAttribute("href", "/items/1?from=%2F");
  expect(screen.getByRole("link", { name: /微信整理 · 今日AI热点简报/ })).toHaveAttribute("href", "/reports/2?from=%2F");
});
