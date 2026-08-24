import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { DataExport } from "./DataExport";

const { get, download } = vi.hoisted(() => ({ get: vi.fn(), download: vi.fn() }));
vi.mock("../api", () => ({ api: { get, download } }));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  get.mockReset().mockResolvedValue({ items: [{ id: 3, name: "智能体" }], total: 1, limit: 100, offset: 0 });
  download.mockReset().mockResolvedValue({ blob: new Blob(["{}"]), filename: "zhiliu-export.json" });
  vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:export"), revokeObjectURL: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
});

function renderExport() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><DataExport /></QueryClientProvider>);
}

it("按日期、主题、类型和数据范围生成JSON导出", async () => {
  renderExport();
  await screen.findByRole("option", { name: "智能体" });
  await userEvent.type(screen.getByLabelText("开始日期"), "2026-08-01");
  await userEvent.selectOptions(screen.getByLabelText("导出主题"), "3");
  await userEvent.selectOptions(screen.getByLabelText("导出内容类型"), "paper");
  await userEvent.click(screen.getByText("标签"));
  await userEvent.click(screen.getByRole("button", { name: "生成导出文件" }));

  await waitFor(() => expect(download).toHaveBeenCalledTimes(1));
  const url = download.mock.calls[0][0] as string;
  expect(url).toContain("format=json");
  expect(url).toContain("fromDate=2026-08-01");
  expect(url).toContain("topicId=3");
  expect(url).toContain("kind=paper");
  expect(url).not.toContain("include=tags");
  expect(URL.createObjectURL).toHaveBeenCalled();
  expect(await screen.findByText("导出文件已生成")).toBeVisible();
});

it("阻止无效日期和空数据范围", async () => {
  renderExport();
  await userEvent.type(screen.getByLabelText("开始日期"), "2026-08-24");
  await userEvent.type(screen.getByLabelText("结束日期"), "2026-08-23");
  expect(screen.getByRole("alert")).toHaveTextContent("开始日期不能晚于结束日期");
  expect(screen.getByRole("button", { name: "生成导出文件" })).toBeDisabled();

  await userEvent.clear(screen.getByLabelText("开始日期"));
  for (const label of ["情报", "报告", "来源", "标签", "主题", "偏好", "任务链路"]) {
    await userEvent.click(screen.getByRole("checkbox", { name: label }));
  }
  expect(screen.getByRole("alert")).toHaveTextContent("至少选择一类数据");
});

it("可以搜索并选择历史主题", async () => {
  get.mockImplementation((url: string) => Promise.resolve({
    items: url.includes("q=%E5%8E%86%E5%8F%B2") ? [{ id: 9, name: "历史主题" }] : [],
    total: 1, limit: 100, offset: 0,
  }));
  renderExport();
  await userEvent.type(screen.getByRole("searchbox", { name: "搜索导出主题" }), "历史");
  expect(await screen.findByRole("option", { name: "历史主题" })).toBeVisible();
  await userEvent.selectOptions(screen.getByLabelText("导出主题"), "9");
  await userEvent.click(screen.getByRole("button", { name: "生成导出文件" }));
  await waitFor(() => expect(download).toHaveBeenCalledWith(expect.stringContaining("topicId=9")));
});
