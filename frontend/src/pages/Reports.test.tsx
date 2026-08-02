import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Reports } from "./Reports";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../api", () => ({ api: { get } }));

beforeEach(() => {
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
  expect(screen.getByText("这是最新简报正文。")).toHaveClass("briefing-summary");
  expect(screen.queryByRole("article", { name: "报告正文" })).not.toBeInTheDocument();
});
