import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Route } from "wouter";

import { ApiError } from "../api";
import { TraceDetail } from "./TraceDetail";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  api: { get },
}));

const trace = {
  publicationId: 7, traceId: "trace-full-chain", origin: "weixin-hermes",
  requestSummary: "整理Agent更新并放进知流", hermesRunId: null,
  createdAt: "2026-08-01T08:00:00Z", itemCount: 1, skippedCount: 1,
  subscription: { id: -1, name: "微信整理·情报" }, taskRun: null,
  items: [{ id: 9, title: "Agent框架更新", summary: "工具调用增强。", source: "Example", url: "https://example.com/agent", ordinal: 0, wasInserted: true }],
  briefing: { id: 3, title: "Agent更新报告", kind: "news" as const },
};

beforeEach(() => {
  window.history.pushState({}, "", "/traces/7");
  get.mockReset().mockResolvedValue(trace);
});

afterEach(cleanup);

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Route path="/traces/:id" component={TraceDetail} />
    </QueryClientProvider>,
  );
}

it("展示从微信指令到报告的五阶段链路", async () => {
  renderPage();

  expect(await screen.findByRole("heading", { name: "完整处理链路" })).toBeVisible();
  for (const name of ["微信指令", "Hermes整理任务", "MCP写入知流", "情报入库", "报告生成"]) {
    expect(screen.getByRole("heading", { name })).toBeVisible();
  }
  expect(screen.getByText("本次网关未提供任务ID")).toBeVisible();
  expect(screen.getByRole("link", { name: "Agent框架更新" })).toHaveAttribute("href", "/items/9?from=%2Ftraces%2F7");
  expect(screen.getByRole("link", { name: "Agent更新报告" })).toHaveAttribute("href", "/reports/3?from=%2Ftraces%2F7");
});

it("404时显示追踪记录不存在", async () => {
  get.mockRejectedValue(new ApiError(404, "追踪记录不存在"));
  renderPage();

  expect(await screen.findByText("追踪记录不存在或已删除")).toBeVisible();
});
