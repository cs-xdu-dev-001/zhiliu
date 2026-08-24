import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { SystemDiagnostics } from "./SystemDiagnostics";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../api", () => ({ api: { get } }));
afterEach(cleanup);
beforeEach(() => get.mockReset().mockResolvedValue({
  status: "degraded",
  generatedAt: "2026-08-24T00:00:00Z",
  database: { status: "ok", latencyMs: 3, migrationVersion: "20260824_ops" },
  scheduler: { enabled: true, running: false, jobCount: 0, lastQueuePollAt: null, lastQueuePollFailed: false, lastSweepAt: null, lastSweepLostCount: 1 },
  queue: { queued: 2, running: 1, oldestActiveSeconds: 125, lastSuccessAt: null, lastFailureAt: null },
  hermes: { configured: true, status: "connected", checkedAt: null },
  mcp: { status: "verified", lastWriteAt: "2026-08-24T01:30:00Z", lastTaskStatus: "success", lastTaskAt: "2026-08-24T01:30:00Z" },
}));

function renderDiagnostics() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SystemDiagnostics /></QueryClientProvider>);
}

it("展示非敏感运行摘要", async () => {
  renderDiagnostics();

  expect(await screen.findByText("需要检查")).toBeVisible();
  expect(screen.getByText("数据库可用")).toBeVisible();
  expect(screen.getByText("调度器未运行")).toBeVisible();
  expect(screen.getByText("1个处理中 · 2个等待")).toBeVisible();
  expect(screen.getByText("Hermes连接正常")).toBeVisible();
  expect(screen.getByText("MCP写入已验证")).toBeVisible();
  expect(document.body.textContent).not.toContain("API Key");
});

it("允许手动刷新诊断", async () => {
  renderDiagnostics();
  await screen.findByText("需要检查");
  await userEvent.click(screen.getByRole("button", { name: "刷新系统诊断" }));
  expect(get).toHaveBeenCalledTimes(2);
});
