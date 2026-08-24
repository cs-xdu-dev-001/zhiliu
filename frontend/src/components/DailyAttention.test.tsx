import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { DailyAttention } from "./DailyAttention";

const { get, post, put } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("../api", () => ({ api: { get, post, put } }));

const item = {
  id: 1, subscriptionId: 1, kind: "news", title: "Agent框架出现重要更新",
  summary: "新增可靠性能力。", url: "https://example.com/agent", source: "Example",
  publishedAt: "2026-08-24T00:00:00Z", keywords: ["Agent"], reason: "值得关注",
  importance: 0.9, personalizedScore: 0.92, recommendationReasons: [],
  isRead: false, isSaved: false, isIgnored: false, isInvalid: false, mergedIntoId: null,
  tags: [], createdAt: "2026-08-24T00:00:00Z",
};

const attention = {
  date: "2026-08-24", settings: { minImportance: 0.7, importantOnly: true },
  items: [{ item, reasons: ["重要变化", "关注主题升温"] }],
  risingTopics: [{ id: 3, name: "Agent", currentCount: 4, previousCount: 1 }],
  importantChangeCount: 1, sourceUnavailableCount: 0, pendingChangeCount: 1,
  consecutiveFailureCount: 0, actionableCount: 2, idempotencyKey: "daily-attention:test",
  latestBriefing: null, activeTask: null,
};

function renderAttention() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><DailyAttention /></QueryClientProvider>);
}

beforeEach(() => {
  get.mockReset().mockResolvedValue(attention);
  post.mockReset().mockResolvedValue({ created: true, message: "每日关注摘要已进入生成队列", task: null });
  put.mockReset().mockResolvedValue({ ...attention, settings: { minImportance: 0.8, importantOnly: true } });
});
afterEach(cleanup);

it("展示可追溯的今日关注并生成摘要", async () => {
  renderAttention();

  expect(await screen.findByRole("link", { name: /Agent框架出现重要更新/ })).toHaveAttribute("href", "/items/1?from=%2F");
  expect(screen.getByRole("link", { name: "Agent" })).toHaveAttribute("href", "/topics/3");
  await userEvent.click(screen.getByRole("button", { name: "生成今日摘要" }));

  expect(post).toHaveBeenCalledWith("/api/daily-attention/generate");
  expect(await screen.findByText("每日关注摘要已进入生成队列")).toBeVisible();
});

it("可以调整最低重要程度", async () => {
  renderAttention();

  await userEvent.selectOptions(await screen.findByRole("combobox", { name: "关注摘要最低重要程度" }), "0.8");

  expect(put).toHaveBeenCalledWith("/api/daily-attention/settings", { minImportance: 0.8, importantOnly: true });
});

it("没有有效变化时不提供空摘要按钮", async () => {
  get.mockResolvedValue({ ...attention, items: [], risingTopics: [], importantChangeCount: 0, pendingChangeCount: 0, actionableCount: 0 });
  renderAttention();

  expect(await screen.findByText("今天没有达到条件的重要变化，不会生成空摘要。")).toBeVisible();
  expect(screen.getByRole("button", { name: "生成今日摘要" })).toBeDisabled();
});
