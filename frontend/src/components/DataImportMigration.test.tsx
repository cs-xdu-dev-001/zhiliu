import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { DataImportMigration } from "./DataImportMigration";

const { get, postRaw, post } = vi.hoisted(() => ({ get: vi.fn(), postRaw: vi.fn(), post: vi.fn() }));
vi.mock("../api", () => ({
  ApiError: class ApiError extends Error {},
  api: { get, postRaw, post },
}));

const summary = {
  subscriptions: { create: 1, reuse: 0, conflict: 0, skip: 0 },
  items: { create: 4, reuse: 2, conflict: 0, skip: 0 },
  topics: { create: 1, reuse: 1, conflict: 0, skip: 0 },
  preferences: { create: 0, reuse: 1, conflict: 0, skip: 0 },
  reports: { create: 1, reuse: 0, conflict: 1, skip: 0 },
  relations: { create: 7, reuse: 0, conflict: 0, skip: 1 },
};

const previewResult = {
  payloadHash: "a".repeat(64),
  previewToken: "preview-token-value",
  expiresAt: "2026-08-24T10:30:00+00:00",
  totalRecords: 21,
  summary,
  unsupported: { tasks: 2 },
  warnings: ["任务和原始发布记录属于运行历史，仅展示数量，不写入目标系统"],
  canImport: true,
};

const batch = {
  id: 12,
  payloadHash: "a".repeat(64),
  reportConflict: "keep" as const,
  status: "committed" as const,
  counts: { items: 4 },
  summary,
  createdAt: "2026-08-24T10:00:00+00:00",
  undoneAt: null,
};

afterEach(cleanup);

beforeEach(() => {
  get.mockReset().mockResolvedValue({ items: [] });
  postRaw.mockReset().mockImplementation((path: string) => path.includes("preview")
    ? Promise.resolve(previewResult)
    : Promise.resolve({ batch, idempotent: false }));
  post.mockReset().mockResolvedValue({ batch: { ...batch, status: "undone", undoneAt: "2026-08-24T10:10:00+00:00" } });
});

function renderImport() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><DataImportMigration /></QueryClientProvider>);
}

function jsonFile(name = "zhiliu-export.json") {
  const file = new File(["{\"schemaVersion\":1}"], name, { type: "application/json" });
  Object.defineProperty(file, "text", { value: vi.fn().mockResolvedValue("{\"schemaVersion\":1}") });
  return file;
}

it("选择文件后预览差异并经确认导入", async () => {
  renderImport();
  await screen.findByText("还没有导入记录");
  await userEvent.upload(screen.getByLabelText("选择知流JSON文件"), jsonFile());
  expect(await screen.findByText("zhiliu-export.json")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "预览导入内容" }));

  expect(await screen.findByText("文件结构有效")).toBeVisible();
  expect(screen.getByRole("table", { name: "导入差异" })).toHaveTextContent("报告");
  expect(screen.getByText("任务和原始发布记录属于运行历史，仅展示数量，不写入目标系统")).toBeVisible();
  await userEvent.click(screen.getByLabelText(/创建新版本/));
  await userEvent.click(screen.getByRole("button", { name: "确认导入" }));
  expect(screen.getByRole("alertdialog", { name: "导入14项新内容？" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "开始导入" }));

  await waitFor(() => expect(postRaw).toHaveBeenLastCalledWith(
    "/api/import/confirm?reportConflict=new_version",
    "{\"schemaVersion\":1}",
    { "X-Import-Preview-Token": "preview-token-value" },
  ));
  expect(await screen.findByText("迁移批次#12已完成。")).toBeVisible();
});

it("展示批次记录并在保护弹窗内撤销", async () => {
  get.mockResolvedValue({ items: [batch] });
  renderImport();
  expect(await screen.findByText("批次#12")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "撤销" }));
  expect(screen.getByRole("alertdialog", { name: "撤销迁移批次#12？" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "确认撤销" }));
  await waitFor(() => expect(postRaw).toHaveBeenCalledWith(
    "/api/import/batches/12/undo",
    "{}",
    { "X-Zhiliu-Action": "undo-import" },
  ));
});

it("在浏览器端拒绝非JSON文件", async () => {
  renderImport();
  await userEvent.upload(screen.getByLabelText("选择知流JSON文件"), jsonFile("notes.txt"), { applyAccept: false });
  expect(await screen.findByRole("alert")).toHaveTextContent("请选择知流导出的JSON文件");
  expect(screen.getByRole("button", { name: "预览导入内容" })).toBeDisabled();
});
