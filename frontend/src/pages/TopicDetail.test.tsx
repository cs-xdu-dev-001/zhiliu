import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Route } from "wouter";

import { TopicDetailPage } from "./TopicDetail";

const { get, patch } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));
vi.mock("../api", async (importOriginal) => ({ ...(await importOriginal<typeof import("../api")>()), api: { get, patch } }));

afterEach(cleanup);

it("汇总主题增量并链接到变化情报", async () => {
  window.history.pushState({}, "", "/topics/3");
  get.mockResolvedValue({
    id: 3, name: "Agent", description: "", isFollowed: true, isPinned: false, isMuted: false,
    itemCount7Days: 2, itemCount30Days: 4, previous7DaysCount: 1, trend: "rising", sourceCount: 2, latestAt: "2026-08-24T00:00:00Z",
    aliases: ["Agent"], latestItems: [], relatedBriefings: [], relatedRuns: [], changeSummary: "新增1条，重要更新1条",
    recentChanges: [{ id: 9, itemId: 12, relatedItemId: 8, relatedItemTitle: "旧记录", taskRunId: 4, publicationId: 5, changeType: "important_update", basis: "官方更新日志新增能力", sourceUrls: ["https://example.com"], before: {}, after: { title: "Agent新增长期记忆" }, status: "confirmed", detectedAt: "2026-08-24T00:00:00Z" }],
  });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Route path="/topics/:id" component={TopicDetailPage} /></QueryClientProvider>);
  expect(await screen.findByText("新增1条，重要更新1条")).toBeVisible();
  expect(screen.getByRole("link", { name: /Agent新增长期记忆/ })).toHaveAttribute("href", "/items/12");
});
