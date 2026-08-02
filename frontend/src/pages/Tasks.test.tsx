import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Tasks } from "./Tasks";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../api", () => ({ api: { get } }));

afterEach(cleanup);

beforeEach(() => {
  window.history.pushState({}, "", "/tasks?status=failed");
  get.mockImplementation((path: string) => Promise.resolve(
    path === "/api/runs"
      ? {
          items: [
            { id: 1, subscriptionId: 1, hermesRunId: null, status: "failed", startedAt: "2026-08-01T08:00:00Z", finishedAt: null, durationMs: null, errorMessage: "连接失败" },
            { id: 2, subscriptionId: 1, hermesRunId: "run-2", status: "success", startedAt: "2026-08-01T09:00:00Z", finishedAt: null, durationMs: 1000, errorMessage: null },
          ],
          total: 2,
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
  expect(screen.getByText("失败")).toBeVisible();
  expect(screen.queryByText("已完成")).not.toBeInTheDocument();
});
