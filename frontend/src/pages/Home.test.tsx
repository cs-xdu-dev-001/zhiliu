import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Home } from "./Home";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
const writeText = vi.fn();
vi.mock("../api", () => ({ api: { get } }));

const dashboard = {
  unreadCount: 1,
  savedCount: 2,
  activeSubscriptions: 3,
  failedRuns: 4,
  topItems: [{
    id: 1, subscriptionId: 1, kind: "news", title: "Agent框架发布新版本",
    summary: "工具调用可靠性提升。", url: "https://example.com", source: "Example",
    publishedAt: "2026-08-01T00:00:00Z", keywords: ["Agent"], reason: "值得跟踪",
    importance: 0.9, isRead: false, isSaved: false, isIgnored: false, createdAt: "2026-08-01T00:00:00Z",
  }],
  latestBriefing: {
    id: 2, subscriptionId: 1, title: "微信整理 · 今日AI热点简报", kind: "news",
    content: "这是最新简报正文。", itemCount: 3,
    periodStart: null, periodEnd: null, createdAt: "2026-08-01T08:00:00Z",
  },
  recentRuns: [{
    id: 7, subscriptionId: -1, subscriptionName: "微信整理·情报", hermesRunId: "hermes-7",
    traceId: "trace-7", origin: "weixin-hermes", topic: "整理Agent更新",
    requestSummary: "整理今天的Agent更新并放进知流", status: "running", stage: "processing",
    resultSummary: null, startedAt: "2026-08-01T09:00:00Z", finishedAt: null,
    durationMs: null, errorMessage: null, publicationId: null, briefingId: null,
  }],
};

const connectedHermes = {
  baseUrl: "http://hermes:8642", apiKeyConfigured: true, apiKeyHint: "••••1234",
  status: "connected", message: "连接正常", checkedAt: "2026-08-01T09:00:00Z", version: "1.0.0",
};

function renderHome() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Home />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  writeText.mockReset().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  get.mockReset().mockImplementation((path: string) => Promise.resolve(path === "/api/dashboard" ? dashboard : connectedHermes));
});

afterEach(cleanup);

it("统计卡和内容卡进入对应筛选或详情", async () => {
  renderHome();

  expect(await screen.findByRole("link", { name: /1\s*待阅读/ })).toHaveAttribute("href", "/feed?state=unread");
  expect(screen.getByRole("link", { name: /2\s*已收藏/ })).toHaveAttribute("href", "/feed?state=saved");
  expect(screen.getByRole("link", { name: /3\s*运行订阅/ })).toHaveAttribute("href", "/settings");
  expect(screen.getByRole("link", { name: /4\s*异常任务/ })).toHaveAttribute("href", "/tasks?status=failed");
  expect(screen.getByRole("link", { name: /Agent框架发布新版本/ })).toHaveAttribute("href", "/items/1?from=%2F");
  expect(screen.getByRole("link", { name: /微信整理 · 今日AI热点简报/ })).toHaveAttribute("href", "/reports/2?from=%2F");
  expect(screen.getByRole("heading", { name: "最近处理动态" })).toBeVisible();
  expect(screen.getByRole("link", { name: /整理Agent更新/ })).toHaveAttribute("href", "/tasks/7");
  expect(screen.getByText("Hermes正在理解、检索和整理")).toBeVisible();
  expect(screen.getByRole("heading", { name: "需要处理" })).toBeVisible();
  expect(screen.getByRole("link", { name: /4个异常任务/ })).toHaveAttribute("href", "/tasks?status=failed");
  expect(document.querySelector(".home-content-grid")).toHaveClass("three-columns");
});

it("没有最近任务时使用完整双栏布局", async () => {
  get.mockImplementation((path: string) => Promise.resolve(path === "/api/dashboard"
    ? { ...dashboard, failedRuns: 0, recentRuns: [] }
    : connectedHermes));

  renderHome();

  expect(await screen.findByRole("heading", { name: "优先阅读" })).toBeVisible();
  expect(screen.queryByRole("heading", { name: "最近处理动态" })).not.toBeInTheDocument();
  expect(document.querySelector(".home-content-grid")).toHaveClass("two-columns");
});

it("Hermes异常时给出明确恢复入口", async () => {
  get.mockImplementation((path: string) => Promise.resolve(path === "/api/dashboard"
    ? { ...dashboard, failedRuns: 0 }
    : { ...connectedHermes, status: "unauthorized", message: "API密钥校验失败" }));

  renderHome();

  expect(await screen.findByText("Hermes授权无效")).toBeVisible();
  expect(screen.getByText("API密钥校验失败")).toBeVisible();
  expect(screen.getByRole("link", { name: /检查Hermes连接/ })).toHaveAttribute("href", "/settings");
});

it("没有内容时直接提供可复制的微信指令", async () => {
  get.mockImplementation((path: string) => Promise.resolve(path === "/api/dashboard"
    ? { ...dashboard, failedRuns: 0, topItems: [], latestBriefing: null, recentRuns: [] }
    : connectedHermes));

  renderHome();

  expect(await screen.findByRole("heading", { name: "从微信发出第一条知流指令" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "复制示例指令" }));
  expect(writeText).toHaveBeenCalledWith("请检索今天AI Agent领域的重要更新，整理后写入知流，并生成一份带来源链接的简报。");
  expect(screen.getByRole("button", { name: "已复制，去微信发送" })).toBeVisible();
  expect(screen.getByRole("link", { name: "查看处理记录" })).toHaveAttribute("href", "/tasks");
  expect(screen.queryByText(/没有待阅读情报/)).not.toBeInTheDocument();
  expect(screen.queryByText(/还没有简报/)).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "需要处理" })).not.toBeInTheDocument();
});

it("首页优先阅读只展示前两条", async () => {
  const firstItem = dashboard.topItems[0];
  get.mockImplementation((path: string) => Promise.resolve(path === "/api/dashboard"
    ? { ...dashboard, topItems: [firstItem, { ...firstItem, id: 2, title: "第二条情报" }, { ...firstItem, id: 3, title: "第三条情报" }] }
    : connectedHermes));

  renderHome();

  expect(await screen.findByText("Agent框架发布新版本")).toBeVisible();
  expect(screen.getByText("第二条情报")).toBeVisible();
  expect(screen.queryByText("第三条情报")).not.toBeInTheDocument();
});
