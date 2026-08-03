import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Route } from "wouter";

import { ApiError } from "../api";
import { ItemDetail } from "./ItemDetail";

const { get, patch } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));
vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  api: { get, patch },
}));

const item = {
  id: 1, subscriptionId: 1, kind: "news" as const, title: "Agent框架发布新版本",
  summary: "完整摘要。", url: "https://example.com", source: "Example · 微信Hermes",
  publishedAt: "2026-08-01T00:00:00Z", keywords: ["Agent", "MCP"], reason: "影响Agent开发工作流",
  importance: 0.9, isRead: false, isSaved: false, isIgnored: false, createdAt: "2026-08-01T00:00:00Z",
  traceAvailable: true,
  publications: [{
    id: 7, traceId: "trace-agent-7", origin: "weixin-hermes", requestSummary: "整理Agent更新并放进知流",
    createdAt: "2026-08-01T01:00:00Z", hermesRunId: "hermes-7", taskRunId: null,
    wasInserted: true, ordinal: 0, briefingId: 3, briefingTitle: "Agent更新报告",
  }],
};

beforeEach(() => {
  window.history.pushState({}, "", "/items/1?from=%2Ffeed%3Fstate%3Dunread");
  get.mockReset().mockResolvedValue(item);
  patch.mockReset().mockResolvedValue({ ...item, isSaved: true });
});

afterEach(cleanup);

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Route path="/items/:id" component={ItemDetail} />
    </QueryClientProvider>,
  );
}

it("显示完整情报并返回来源列表", async () => {
  renderPage();
  expect(await screen.findByRole("heading", { name: "Agent框架发布新版本" })).toBeVisible();
  expect(screen.getByText("影响Agent开发工作流")).toBeVisible();
  expect(screen.getByRole("link", { name: "返回情报列表" })).toHaveAttribute("href", "/feed?state=unread");
  expect(screen.getByRole("link", { name: /打开原文/ })).toHaveAttribute("href", "https://example.com");
});

it("可以在详情收藏", async () => {
  renderPage();
  await screen.findByText("完整摘要。");
  await userEvent.click(screen.getByRole("button", { name: "收藏" }));
  expect(patch).toHaveBeenCalledWith("/api/items/1", { isSaved: true });
});

it("展示Hermes写入记录和完整链路入口", async () => {
  renderPage();

  expect(await screen.findByRole("heading", { name: "写入记录" })).toBeVisible();
  expect(screen.getByText("整理Agent更新并放进知流")).toBeVisible();
  expect(screen.getByText("首次写入")).toBeVisible();
  expect(screen.getByRole("link", { name: "查看完整链路" })).toHaveAttribute("href", "/traces/7");
  expect(screen.getByRole("link", { name: "Agent更新报告" })).toHaveAttribute("href", "/reports/3");
});

it("历史情报明确显示暂无追踪", async () => {
  get.mockResolvedValue({ ...item, traceAvailable: false, publications: [] });
  renderPage();

  expect(await screen.findByText("历史数据，暂无完整追踪信息")).toBeVisible();
});

it("404时显示详情不存在", async () => {
  get.mockRejectedValue(new ApiError(404, "情报不存在"));
  renderPage();
  expect(await screen.findByText("情报不存在或已删除")).toBeVisible();
});

it("拒绝外部返回地址", async () => {
  window.history.pushState({}, "", "/items/1?from=https%3A%2F%2Fevil.example");
  renderPage();

  expect(await screen.findByRole("link", { name: "返回情报列表" })).toHaveAttribute("href", "/feed");
});

it("拒绝反斜杠伪装的外部返回地址", async () => {
  window.history.pushState({}, "", "/items/1?from=%2F%5Cevil.example");
  renderPage();

  expect(await screen.findByRole("link", { name: "返回情报列表" })).toHaveAttribute("href", "/feed");
});

it("加载时向辅助技术说明状态", () => {
  get.mockReturnValue(new Promise(() => undefined));
  renderPage();

  expect(screen.getByRole("status", { name: "正在加载情报" })).toBeVisible();
});
