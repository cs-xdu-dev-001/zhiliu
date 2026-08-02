import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Route } from "wouter";

import { ApiError } from "../api";
import { BriefingDetail } from "./BriefingDetail";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  api: { get },
}));

const briefing = {
  id: 1, subscriptionId: 1, title: "微信整理 · 今日AI热点简报", kind: "news" as const,
  content: "这是完整报告正文。", itemCount: 3,
  periodStart: "2026-07-31T00:00:00Z", periodEnd: "2026-08-01T00:00:00Z", createdAt: "2026-08-01T08:00:00Z",
};

beforeEach(() => {
  window.history.pushState({}, "", "/reports/1?from=%2Freports");
  get.mockReset().mockResolvedValue(briefing);
});

afterEach(cleanup);

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Route path="/reports/:id" component={BriefingDetail} />
    </QueryClientProvider>,
  );
}

it("加载完整报告并返回列表", async () => {
  renderPage();
  expect(await screen.findByRole("heading", { name: "微信整理 · 今日AI热点简报" })).toBeVisible();
  expect(get).toHaveBeenCalledWith("/api/briefings/1");
  expect(screen.getByText("这是完整报告正文。")).toBeVisible();
  expect(screen.getByRole("link", { name: "返回报告列表" })).toHaveAttribute("href", "/reports");
});

it("404时显示报告不存在", async () => {
  get.mockRejectedValue(new ApiError(404, "简报不存在"));
  renderPage();
  expect(await screen.findByText("报告不存在或已删除")).toBeVisible();
});

it("拒绝跨站返回地址", async () => {
  window.history.pushState({}, "", "/reports/1?from=%2F%5Cevil.example");
  renderPage();

  expect(await screen.findByRole("link", { name: "返回报告列表" })).toHaveAttribute("href", "/reports");
});

it("加载时向辅助技术说明状态", () => {
  get.mockReturnValue(new Promise(() => undefined));
  renderPage();

  expect(screen.getByRole("status", { name: "正在加载报告" })).toBeVisible();
});
