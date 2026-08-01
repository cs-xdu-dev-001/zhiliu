import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { Feed } from "./Feed";

const { get, patch } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));
vi.mock("../api", () => ({ api: { get, patch } }));

beforeEach(() => {
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
});
