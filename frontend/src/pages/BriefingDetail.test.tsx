import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Route } from "wouter";

import { ApiError } from "../api";
import { BriefingDetail } from "./BriefingDetail";

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  api: { get, post },
}));

const briefing = {
  id: 1, subscriptionId: 1, title: "微信整理 · 今日AI热点简报", kind: "news" as const,
  content: "这是完整报告正文。", itemCount: 3,
  periodStart: "2026-07-31T00:00:00Z", periodEnd: "2026-08-01T00:00:00Z", createdAt: "2026-08-01T08:00:00Z",
  traceAvailable: true,
  publication: {
    id: 7, traceId: "trace-report-7", origin: "weixin-hermes", requestSummary: "整理今天的重要AI动态",
    createdAt: "2026-08-01T08:00:00Z", hermesRunId: "hermes-7", taskRunId: null,
  },
  sourceItems: [{
    id: 9, title: "Agent框架发布新版本", summary: "工具调用可靠性提升。", source: "Example",
    url: "https://example.com/agent", ordinal: 0, wasInserted: true,
  }],
};

beforeEach(() => {
  window.history.pushState({}, "", "/reports/1?from=%2Freports");
  get.mockReset().mockResolvedValue(briefing);
  post.mockReset().mockResolvedValue({ id: 42 });
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } });
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:report") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

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

it("展示准确来源情报和独立原文链接", async () => {
  renderPage();

  expect(await screen.findByRole("heading", { name: "来源情报" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Agent框架发布新版本" })).toHaveAttribute("href", "/items/9?from=%2Freports%2F1");
  expect(screen.getByRole("link", { name: "打开原文（新窗口）" })).toHaveAttribute("href", "https://example.com/agent");
  expect(screen.getByRole("link", { name: "查看生成链路" })).toHaveAttribute("href", "/traces/7?from=%2Freports%2F1");
  expect(screen.getByText("1条")).toBeVisible();
});

it("复制摘要并导出Markdown", async () => {
  const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  renderPage();

  await screen.findByRole("heading", { name: "微信整理 · 今日AI热点简报" });
  await userEvent.click(screen.getByRole("button", { name: "复制摘要" }));
  expect(navigator.clipboard.writeText).toHaveBeenCalledWith("微信整理 · 今日AI热点简报\n\n这是完整报告正文。");
  expect(await screen.findByText("报告摘要已复制")).toBeVisible();

  await userEvent.click(screen.getByRole("button", { name: "导出Markdown" }));
  expect(URL.createObjectURL).toHaveBeenCalled();
  expect(anchorClick).toHaveBeenCalled();
  expect(await screen.findByText("Markdown报告已导出")).toBeVisible();
});

it("历史报告明确显示暂无追踪", async () => {
  get.mockResolvedValue({ ...briefing, traceAvailable: false, publication: null, sourceItems: [] });
  renderPage();

  expect(await screen.findByText("历史数据，暂无完整追踪信息")).toBeVisible();
});

it("拒绝非HTTP来源链接", async () => {
  get.mockResolvedValue({ ...briefing, sourceItems: [{ ...briefing.sourceItems[0], url: "javascript:alert(1)" }] });
  renderPage();

  expect(await screen.findByText("原文链接不可用")).toBeVisible();
  expect(screen.queryByRole("link", { name: "打开原文（新窗口）" })).not.toBeInTheDocument();
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

it("来源已标记失效时停用报告中的原文外链", async () => {
  get.mockResolvedValue({ ...briefing, sourceItems: [{ ...briefing.sourceItems[0], sourceUnavailable: true }] });
  renderPage();

  expect(await screen.findByText("原文已失效", { exact: true })).toBeVisible();
  expect(screen.getByText(/Example · 本次写入 · 原文失效/)).toBeVisible();
  expect(screen.queryByRole("link", { name: "打开原文（新窗口）" })).not.toBeInTheDocument();
});

it("展示引用和版本，并可重新生成", async () => {
  get.mockResolvedValue({
    ...briefing,
    content: "工具可靠性提高[1]。",
    seriesId: "series-1",
    versionNumber: 2,
    citationStatus: "valid",
    citationWarnings: [],
    versions: [
      { ...briefing, id: 2, seriesId: "series-1", versionNumber: 2 },
      { ...briefing, id: 1, seriesId: "series-1", versionNumber: 1 },
    ],
  });
  renderPage();

  expect(await screen.findByRole("link", { name: "查看来源1" })).toHaveAttribute("href", "#source-1");
  expect(screen.getByText("来源编号已校验")).toBeVisible();
  expect(screen.getByRole("navigation", { name: "报告版本" })).toHaveTextContent("v2");
  await userEvent.click(screen.getByRole("button", { name: "重新生成" }));
  await userEvent.type(screen.getByRole("textbox", { name: "调整要求" }), "更精炼");
  await userEvent.click(screen.getByRole("button", { name: "开始生成" }));

  expect(post).toHaveBeenCalledWith("/api/briefings/1/regenerate", {
    instruction: "更精炼",
    requestId: expect.any(String),
  });
  expect(window.location.pathname).toBe("/tasks/42");
});

it("重新生成失败后保留要求、沿用请求标识并恢复焦点", async () => {
  post.mockRejectedValue(new ApiError(503, "Hermes暂时不可用"));
  renderPage();

  const trigger = await screen.findByRole("button", { name: "重新生成" });
  await userEvent.click(trigger);
  const input = screen.getByRole("textbox", { name: "调整要求" });
  await waitFor(() => expect(input).toHaveFocus());
  await userEvent.type(input, "保留这段要求");
  await userEvent.click(screen.getByRole("button", { name: "开始生成" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Hermes暂时不可用");
  expect(input).toHaveValue("保留这段要求");
  const firstRequestId = post.mock.calls[0][1].requestId;
  await userEvent.click(screen.getByRole("button", { name: "重试生成" }));
  expect(post.mock.calls[1][1].requestId).toBe(firstRequestId);
  await userEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(trigger).toHaveFocus();
});

it("引用不完整时可以展开查看具体来源", async () => {
  get.mockResolvedValue({
    ...briefing,
    citationStatus: "warning",
    citationWarnings: ["来源[2]未在正文中引用"],
  });
  renderPage();

  const warning = await screen.findByText("有1条来源未在正文中引用");
  expect(warning).toBeVisible();
  await userEvent.click(warning);
  expect(screen.getByText("来源[2]未在正文中引用")).toBeVisible();
});
