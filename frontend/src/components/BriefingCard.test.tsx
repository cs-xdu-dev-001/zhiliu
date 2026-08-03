import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { BriefingCard } from "./BriefingCard";

const briefing = {
  id: 2, subscriptionId: 1, title: "微信整理 · 今日AI热点简报", kind: "news" as const,
  content: "第一段。\n\n第二段包含更完整的分析。", itemCount: 3,
  periodStart: null, periodEnd: null, createdAt: "2026-08-01T08:00:00Z",
};

afterEach(cleanup);

it("展示标题、纯文本摘要和详情链接", () => {
  render(<BriefingCard briefing={briefing} detailHref="/reports/2?from=%2Freports" />);

  expect(screen.getByRole("link", { name: /微信整理 · 今日AI热点简报/ })).toHaveAttribute("href", "/reports/2?from=%2Freports");
  expect(screen.getByText("第一段。 第二段包含更完整的分析。")).toHaveClass("briefing-summary");
  expect(screen.getByText("引用3条情报")).toBeVisible();
});
