import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { TaskDetail } from "./TaskDetail";

const { get, post, navigate } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), navigate: vi.fn() }));
vi.mock("../api", () => ({ api: { get, post }, ApiError: class ApiError extends Error {} }));
vi.mock("wouter", async () => {
  const actual = await vi.importActual<typeof import("wouter")>("wouter");
  return { ...actual, useParams: () => ({ id: "7" }), useLocation: () => ["/tasks/7", navigate] };
});

beforeEach(() => {
  navigate.mockReset();
  post.mockReset().mockResolvedValue({ id: 9, retryOfId: 7, status: "queued" });
  get.mockResolvedValue({
    id: 7, subscriptionId: -1, retryOfId: null, subscriptionName: "微信整理·情报", hermesRunId: "hermes-7",
    traceId: "trace-7", origin: "weixin-hermes", topic: "整理Agent更新",
    requestSummary: "整理今天的Agent更新并放进知流", status: "success", stage: "completed",
    resultSummary: "新增2条情报，复用1条，生成报告《Agent更新简报》",
    startedAt: "2026-08-01T09:00:00Z", finishedAt: "2026-08-01T09:01:00Z",
    durationMs: 60000, errorMessage: null, publicationId: 12, briefingId: 5,
  });
});

afterEach(cleanup);

it("展示任务阶段、结果和追踪入口", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TaskDetail />
    </QueryClientProvider>,
  );

  expect(await screen.findByRole("heading", { name: "整理Agent更新" })).toBeVisible();
  expect(screen.getByText("已完成")).toBeVisible();
  expect(screen.getByText("整理今天的Agent更新并放进知流")).toBeVisible();
  expect(screen.getByText(/新增2条情报/)).toBeVisible();
  expect(screen.getByRole("link", { name: "查看完整处理链路" })).toHaveAttribute("href", "/traces/12?from=%2Ftasks%2F7");
  expect(screen.getByRole("link", { name: "查看生成报告" })).toHaveAttribute("href", "/reports/5?from=%2Ftasks%2F7");
  await userEvent.click(screen.getByText("技术信息"));
  expect(screen.getByText("hermes-7")).toBeVisible();
  expect(screen.getByText("trace-7")).toBeVisible();
});

it("失败任务明确说明没有写入知流", async () => {
  get.mockResolvedValueOnce({
    id: 8, subscriptionId: -1, retryOfId: null, subscriptionName: "微信整理·情报", hermesRunId: null,
    traceId: "trace-8", origin: "weixin-hermes", topic: "失败的整理任务",
    requestSummary: "整理来源不可用的内容", status: "failed", stage: "failed",
    resultSummary: null, startedAt: "2026-08-01T09:00:00Z", finishedAt: "2026-08-01T09:00:05Z",
    durationMs: 5000, errorMessage: "来源网站暂时不可达", publicationId: null, briefingId: null,
  });

  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TaskDetail />
    </QueryClientProvider>,
  );

  expect(await screen.findByText("来源网站暂时不可达")).toBeVisible();
  expect(screen.getByRole("heading", { name: "知流结果" })).toBeVisible();
  expect(screen.getByText(/本次未写入知流/)).toBeVisible();
  expect(screen.getByRole("link", { name: "检查订阅与Hermes连接" })).toHaveAttribute("href", "/settings?view=runtime");
  expect(screen.queryByRole("button", { name: "重新执行" })).not.toBeInTheDocument();
});

it("失败的订阅任务可以重新排队并保留原任务", async () => {
  get.mockResolvedValueOnce({
    id: 7, subscriptionId: 2, retryOfId: null, subscriptionName: "Agent论文周报", hermesRunId: null,
    traceId: null, origin: "subscription-hermes", topic: "Agent论文周报",
    requestSummary: "检索过去一周Agent论文", status: "failed", stage: "failed",
    resultSummary: null, startedAt: "2026-08-01T09:00:00Z", finishedAt: "2026-08-01T09:00:05Z",
    durationMs: 5000, errorMessage: "Hermes暂时不可用", publicationId: null, briefingId: null,
  });

  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TaskDetail />
    </QueryClientProvider>,
  );

  await userEvent.click(await screen.findByRole("button", { name: "重新执行" }));

  expect(post).toHaveBeenCalledWith("/api/runs/7/retry");
  expect(navigate).toHaveBeenCalledWith("/tasks/9");
});
