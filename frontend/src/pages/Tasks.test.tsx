import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Tasks } from "./Tasks";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../api", () => ({ api: { get } }));

afterEach(cleanup);

beforeEach(() => {
  window.history.pushState({}, "", "/tasks?status=failed");
  get.mockReset();
  get.mockImplementation((path: string) => Promise.resolve(
    path.startsWith("/api/runs?")
      ? {
          items: [
            { id: 1, subscriptionId: 1, subscriptionName: "每日Agent动态", topic: "微信检索任务", hermesRunId: null, traceId: "trace-1", origin: "weixin-hermes", status: "failed", stage: "failed", resultSummary: null, startedAt: "2026-08-01T08:00:00Z", finishedAt: null, durationMs: null, errorMessage: "连接失败", publicationId: null, briefingId: null },
          ],
          total: 1,
          limit: 20,
          offset: 0,
        }
      : [{ id: 1, name: "每日Agent动态" }],
  ));
});

it("status=failed时只展示失败任务", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Tasks />
    </QueryClientProvider>,
  );

  expect(await screen.findByText("连接失败")).toBeVisible();
  expect(get).toHaveBeenCalledWith("/api/runs?limit=20&offset=0&status=failed");
  expect(screen.getByText("失败")).toBeVisible();
  expect(screen.queryByText("已完成")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /微信检索任务/ })).toHaveAttribute("href", "/tasks/1");
  expect(screen.getByRole("link", { name: "仅失败" })).toHaveClass("active");
  expect(screen.getByRole("link", { name: "全部任务" })).toHaveAttribute("href", "/tasks");
});

it("第二页使用稳定的服务端分页参数", async () => {
  window.history.pushState({}, "", "/tasks?page=2");
  get.mockResolvedValueOnce({
    items: [{ id: 21, subscriptionId: 1, subscriptionName: "每日Agent动态", topic: "较早任务", hermesRunId: null, traceId: null, origin: "subscription-hermes", status: "success", stage: "completed", resultSummary: "完成", startedAt: "2026-08-01T07:00:00Z", finishedAt: null, durationMs: null, errorMessage: null, publicationId: null, briefingId: null }],
    total: 21,
    limit: 20,
    offset: 20,
  });

  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Tasks />
    </QueryClientProvider>,
  );

  expect(await screen.findByText("较早任务")).toBeVisible();
  expect(get).toHaveBeenCalledWith("/api/runs?limit=20&offset=20");
  expect(screen.getByText("第2/2页")).toBeVisible();
  expect(screen.getByRole("link", { name: /上一页/ })).toHaveAttribute("href", "/tasks");
  expect(screen.getByRole("link", { name: /下一页/ })).toHaveAttribute("aria-disabled", "true");
});

it("加载失败时提供重新加载", async () => {
  get.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ items: [], total: 0, limit: 20, offset: 0 });

  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Tasks />
    </QueryClientProvider>,
  );

  const retry = await screen.findByRole("button", { name: "重新加载" });
  fireEvent.click(retry);
  await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
});
