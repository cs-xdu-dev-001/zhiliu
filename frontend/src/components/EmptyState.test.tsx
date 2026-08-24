import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { EmptyState } from "./EmptyState";

it("筛选空结果使用紧凑布局并保留恢复动作", () => {
  render(<EmptyState compact title="没有符合条件的内容" action={<button>清除筛选</button>} />);

  expect(screen.getByRole("status", { name: "没有符合条件的内容" })).toHaveClass("compact");
  expect(screen.getByRole("button", { name: "清除筛选" })).toBeVisible();
});

it("首次使用引导保持完整布局", () => {
  render(<EmptyState title="还没有内容" description="完成首次整理后会显示在这里。" />);

  expect(screen.getByRole("status", { name: "还没有内容" })).not.toHaveClass("compact");
  expect(screen.getByText("完成首次整理后会显示在这里。")).toBeVisible();
});
