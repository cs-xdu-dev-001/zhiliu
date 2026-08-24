import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { ItemCard } from "./ItemCard";

const item = {
  id: 1,
  subscriptionId: 1,
  kind: "news" as const,
  title: "Agent框架发布新版本",
  summary: "工具调用可靠性提升。",
  url: "https://example.com",
  source: "Example",
  publishedAt: "2026-08-01T00:00:00Z",
  keywords: ["Agent"],
  reason: "值得跟踪",
  importance: 0.9,
  isRead: true,
  isSaved: false,
  isIgnored: false,
  isInvalid: false,
  mergedIntoId: null,
  tags: [],
  createdAt: "2026-08-01T00:00:00Z",
};

afterEach(cleanup);

it("用优先级语义解释重要性并明确已读状态", () => {
  render(<ItemCard item={item} />);

  expect(screen.getByText("高优先级")).toHaveAccessibleName("高优先级，重要性90分");
  expect(screen.getByText("已读")).toBeVisible();
});

it("展示微信Hermes组合来源", () => {
  render(<ItemCard item={{ ...item, source: "arXiv · 微信Hermes" }} />);

  expect(screen.getByText("arXiv · 微信Hermes")).toBeVisible();
});

it("只展示一个简洁变化标记并隐藏重复消息", () => {
  const { rerender } = render(<ItemCard item={{ ...item, latestChangeType: "important_update" }} />);
  expect(screen.getByText("重要更新")).toBeVisible();
  rerender(<ItemCard item={{ ...item, latestChangeType: "duplicate_message" }} />);
  expect(screen.queryByText("重复消息")).not.toBeInTheDocument();
});

it("标题摘要进入独立详情且列表不展开判断理由", () => {
  render(<ItemCard item={item} detailHref="/items/1?from=%2Ffeed%3Fstate%3Dunread" />);

  expect(screen.getByRole("link", { name: /Agent框架发布新版本/ })).toHaveAttribute(
    "href",
    "/items/1?from=%2Ffeed%3Fstate%3Dunread",
  );
  expect(screen.getByText("工具调用可靠性提升。")).toHaveClass("item-summary");
  expect(screen.queryByText(/值得关注/)).not.toBeInTheDocument();
});

it("快捷操作位于详情链接之外", () => {
  const onChange = vi.fn();
  render(<ItemCard item={item} onChange={onChange} />);

  expect(screen.getByRole("link", { name: /Agent框架发布新版本/ })).not.toContainElement(
    screen.getByRole("button", { name: "收藏" }),
  );
});

it("明确提示可能过期但仍允许进入详情", () => {
  render(<ItemCard item={{ ...item, isStale: true }} />);

  expect(screen.getByText("可能过期")).toBeVisible();
  expect(screen.getByRole("link", { name: /Agent框架发布新版本/ })).toHaveAttribute("href", "/items/1");
});

it("快捷操作明确当前状态并支持取消忽略", async () => {
  const onChange = vi.fn();
  render(<ItemCard item={{ ...item, isIgnored: true }} onChange={onChange} />);

  expect(screen.getByRole("button", { name: "标记未读" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "取消忽略" })).toHaveAttribute("aria-pressed", "true");
  await userEvent.click(screen.getByRole("button", { name: "取消忽略" }));
  expect(onChange).toHaveBeenCalledWith({ isIgnored: false });
});

it("批量模式提供带标题的选择框", () => {
  render(<ItemCard item={item} selectable selected={false} onSelect={vi.fn()} />);

  expect(screen.getByRole("checkbox", { name: "选择Agent框架发布新版本" })).toBeVisible();
  expect(screen.queryByText("查看详情")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Agent框架发布新版本/ })).toHaveAttribute("href", "/items/1");
  expect(screen.getByRole("link", { name: "打开原文（新窗口）" })).toBeVisible();
});

it("拒绝不安全的原文链接", () => {
  render(<ItemCard item={{ ...item, url: "javascript:alert(1)" }} />);

  expect(screen.queryByRole("link", { name: "打开原文（新窗口）" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("原文链接不可用")).toBeVisible();
});

it("原文失效时保留详情入口但停用外链", () => {
  render(<ItemCard item={{ ...item, sourceUnavailable: true }} />);

  expect(screen.getByText("原文失效")).toBeVisible();
  expect(screen.getByLabelText("原文已标记失效")).toBeVisible();
  expect(screen.queryByRole("link", { name: "打开原文（新窗口）" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Agent框架发布新版本/ })).toBeVisible();
});

it("首页紧凑卡只保留判断所需信息", () => {
  render(<ItemCard item={item} compact />);

  expect(screen.getByText("工具调用可靠性提升。")).toHaveClass("item-summary");
  expect(screen.queryByText("Agent")).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "打开原文（新窗口）" })).not.toBeInTheDocument();
  expect(screen.getByText("查看详情")).toBeVisible();
});
