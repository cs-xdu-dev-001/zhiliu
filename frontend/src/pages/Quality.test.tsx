import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";

import { Quality } from "./Quality";

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("../api", () => ({ api: { get, post } }));
afterEach(cleanup);
beforeEach(() => {
  get.mockReset().mockResolvedValue({ filteredCount: 1, duplicateCount: 2, restoredCount: 0, staleCount: 3, lowImportanceCount: 4, sourceUnavailableCount: 1, total: 1, items: [{ id: 8, publicationId: 3, itemId: null, action: "filtered", reasonCode: "source_avoid", reason: "命中来源避开偏好，未写入", kind: "news", title: "被过滤内容", summary: "摘要", source: "低质量来源", url: "https://example.com/blocked", importance: 0.4, restoredAt: null, createdAt: "2026-08-04T00:00:00Z", traceId: "trace-8", briefingId: null }] });
  post.mockReset().mockResolvedValue({ id: 8, itemId: 12, action: "filtered", restoredAt: "2026-08-04T01:00:00Z" });
});

it("展示过滤理由并允许恢复写入", async () => {
  const { hook } = memoryLocation({ path: "/quality" });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(["items"], { items: [], total: 0 });
  queryClient.setQueryData(["dashboard"], { unreadCount: 0 });
  render(<Router hook={hook}><QueryClientProvider client={queryClient}><Quality /></QueryClientProvider></Router>);
  expect(await screen.findByText("被过滤内容")).toBeVisible();
  expect(screen.getByText("命中来源避开偏好，未写入")).toBeVisible();
  expect(screen.getByRole("link", { name: /3\s+可能过期/ })).toHaveAttribute("href", "/feed?state=stale");
  expect(screen.getByRole("link", { name: /4\s+低优先级/ })).toHaveAttribute("href", "/feed?state=low");
  expect(screen.getByRole("link", { name: /1\s+原文失效/ })).toHaveAttribute("href", "/feed?state=source-unavailable");
  await userEvent.click(screen.getByRole("button", { name: "恢复写入" }));
  expect(post).toHaveBeenCalledWith("/api/quality/8/restore");
  expect(await screen.findByText("内容已恢复写入。")).toBeVisible();
  expect(screen.getByRole("link", { name: "查看情报" })).toHaveAttribute("href", "/items/12");
  await waitFor(() => expect(queryClient.getQueryState(["items"])?.isInvalidated).toBe(true));
  expect(queryClient.getQueryState(["dashboard"])?.isInvalidated).toBe(true);
});

it("已恢复指标可以筛选恢复记录", async () => {
  window.history.pushState({}, "", "/quality");
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Quality /></QueryClientProvider>);
  await screen.findByText("被过滤内容");
  await userEvent.click(within(screen.getByRole("group", { name: "质量概览" })).getByRole("button", { name: /已恢复/ }));
  await waitFor(() => expect(get).toHaveBeenCalledWith("/api/quality?action=restored"));
  expect(screen.queryByRole("group", { name: "质量记录筛选" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "查看全部" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "查看全部" }));
  await waitFor(() => expect(get).toHaveBeenCalledWith("/api/quality"));
});

it("空记录使用紧凑状态行", async () => {
  get.mockResolvedValue({ filteredCount: 0, duplicateCount: 0, restoredCount: 0, staleCount: 0, lowImportanceCount: 0, sourceUnavailableCount: 0, total: 0, items: [] });
  window.history.pushState({}, "", "/quality?action=restored");
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Quality /></QueryClientProvider>);
  expect(await screen.findByRole("status", { name: "还没有恢复记录" })).toHaveClass("quality-empty");
  expect(screen.queryByText("恢复被误过滤的内容后，记录会保留在这里。")).not.toBeInTheDocument();
});
