import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Route } from "wouter";

import { ApiError } from "../api";
import { ItemDetail } from "./ItemDetail";

const { get, patch, put, post } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  api: { get, patch, put, post },
}));

const item = {
  id: 1, subscriptionId: 1, kind: "news" as const, title: "Agent框架发布新版本",
  summary: "完整摘要。", url: "https://example.com", source: "Example · 微信Hermes",
  publishedAt: "2026-08-01T00:00:00Z", keywords: ["Agent", "MCP"], reason: "影响Agent开发工作流",
  importance: 0.9, isRead: false, isSaved: false, isIgnored: false, createdAt: "2026-08-01T00:00:00Z",
  isInvalid: false, mergedIntoId: null, mergedInto: null,
  traceAvailable: true,
  revisions: [{ id: 11, action: "edited", before: { title: "旧标题" }, after: { title: "Agent框架发布新版本" }, createdAt: "2026-08-01T02:00:00Z" }],
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
  put.mockReset().mockResolvedValue({ ...item, isInvalid: true });
  post.mockReset().mockResolvedValue({ ...item });
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

it("可以编辑标题摘要和分类", async () => {
  renderPage();
  await screen.findByText("完整摘要。");
  await userEvent.click(screen.getByRole("button", { name: "编辑内容" }));
  await userEvent.clear(screen.getByLabelText("标题"));
  await userEvent.type(screen.getByLabelText("标题"), "修正后的标题");
  await userEvent.clear(screen.getByLabelText("摘要"));
  await userEvent.type(screen.getByLabelText("摘要"), "修正后的摘要");
  await userEvent.selectOptions(screen.getByLabelText("分类"), "paper");
  await userEvent.click(screen.getByRole("button", { name: "保存修改" }));

  expect(patch).toHaveBeenCalledWith("/api/items/1/content", {
    title: "修正后的标题", summary: "修正后的摘要", kind: "paper",
  });
});

it("可以标记无效", async () => {
  renderPage();
  await screen.findByText("完整摘要。");
  await userEvent.click(screen.getByRole("button", { name: "标记无效" }));
  expect(put).toHaveBeenCalledWith("/api/items/1/validity", { invalid: true });
});

it("可以选择候选情报并合并", async () => {
  get.mockImplementation((path: string) => path.endsWith("merge-candidates")
    ? Promise.resolve([{ id: 2, title: "相似情报", summary: "同一事件的另一条记录", source: "另一来源", similarity: 0.92 }])
    : Promise.resolve(item));
  renderPage();
  await screen.findByText("完整摘要。");
  await userEvent.click(screen.getByRole("button", { name: "合并重复" }));
  await userEvent.click(await screen.findByRole("radio", { name: /相似情报/ }));
  await userEvent.click(screen.getByRole("button", { name: "确认合并" }));
  expect(post).toHaveBeenCalledWith("/api/items/1/merge", { targetId: 2 });
});

it("展示版本记录", async () => {
  renderPage();
  const section = (await screen.findByRole("heading", { name: "修改记录" })).closest("section")!;
  expect(within(section).getByText("编辑内容")).toBeVisible();
  expect(within(section).getByText(/标题：旧标题 → Agent框架发布新版本/)).toBeVisible();
});

it("微信来源提示回到微信重新发起", async () => {
  renderPage();
  expect(await screen.findByText(/回到微信重新发起/)).toBeVisible();
  expect(screen.queryByRole("button", { name: "重新整理" })).not.toBeInTheDocument();
});

it("订阅来源可以重新整理", async () => {
  get.mockResolvedValue({ ...item, publications: [{ ...item.publications[0], origin: "subscription-hermes" }] });
  renderPage();
  await userEvent.click(await screen.findByRole("button", { name: "重新整理" }));
  expect(post).toHaveBeenCalledWith("/api/subscriptions/1/run");
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

it("拒绝不安全的原文链接", async () => {
  get.mockResolvedValue({ ...item, url: "javascript:alert(1)" });
  renderPage();

  expect(await screen.findByText("原文链接不可用")).toBeVisible();
  expect(screen.queryByRole("link", { name: /打开原文/ })).not.toBeInTheDocument();
});

it("编辑弹窗关闭后恢复焦点并解锁页面", async () => {
  renderPage();
  const trigger = await screen.findByRole("button", { name: "编辑内容" });
  await userEvent.click(trigger);
  expect(document.body.style.overflow).toBe("hidden");
  await userEvent.keyboard("{Escape}");

  expect(screen.queryByRole("dialog", { name: "编辑情报" })).not.toBeInTheDocument();
  expect(document.body.style.overflow).toBe("");
  expect(trigger).toHaveFocus();
});
