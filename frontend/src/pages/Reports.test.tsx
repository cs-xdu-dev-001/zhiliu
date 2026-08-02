import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { Reports } from "./Reports";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../api", () => ({ api: { get } }));

beforeEach(() => {
  get.mockReset().mockResolvedValue({
    items: [{
      id: 1,
      subscriptionId: 1,
      title: "今日AI热点简报",
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

it("加载后直接展示最新简报", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Reports />
    </QueryClientProvider>,
  );

  expect(await screen.findByText("这是最新简报正文。")).toBeVisible();
  expect(screen.queryByText("选择一份报告阅读")).not.toBeInTheDocument();
});
