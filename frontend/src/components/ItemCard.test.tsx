import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

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
  createdAt: "2026-08-01T00:00:00Z",
};

it("用优先级语义解释重要性并明确已读状态", () => {
  render(<ItemCard item={item} />);

  expect(screen.getByText("高优先级")).toHaveAccessibleName("高优先级，重要性90分");
  expect(screen.getByText("已读")).toBeVisible();
});

it("展示微信Hermes组合来源", () => {
  render(<ItemCard item={{ ...item, source: "arXiv · 微信Hermes" }} />);

  expect(screen.getByText("arXiv · 微信Hermes")).toBeVisible();
});
