import { cleanup, render, screen } from "@testing-library/react";
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

it("批量模式提供带标题的选择框", () => {
  render(<ItemCard item={item} selectable selected={false} onSelect={vi.fn()} />);

  expect(screen.getByRole("checkbox", { name: "选择Agent框架发布新版本" })).toBeVisible();
});

it("拒绝不安全的原文链接", () => {
  render(<ItemCard item={{ ...item, url: "javascript:alert(1)" }} />);

  expect(screen.queryByRole("link", { name: "打开原文（新窗口）" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("原文链接不可用")).toBeVisible();
});
