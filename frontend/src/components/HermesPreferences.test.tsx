import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { HermesPreferences } from "./HermesPreferences";

const { get, post, remove } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), remove: vi.fn() }));
vi.mock("../api", () => ({ api: { get, post, delete: remove } }));

afterEach(cleanup);
beforeEach(() => {
  get.mockReset().mockResolvedValue({ items: [] });
  post.mockReset().mockResolvedValue({});
  remove.mockReset().mockResolvedValue({});
});

function renderPreferences() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><HermesPreferences /></QueryClientProvider>);
}

it("新增长期偏好", async () => {
  renderPreferences();
  expect(await screen.findByText(/还没有长期偏好/)).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "新增偏好" }));
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "作用对象" }), "source");
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "处理方式" }), "avoid");
  await userEvent.type(screen.getByRole("textbox", { name: "偏好内容" }), "营销号");
  await userEvent.click(screen.getByRole("button", { name: "保存偏好" }));
  expect(post).toHaveBeenCalledWith("/api/preferences", expect.objectContaining({ scope: "source", effect: "avoid", value: "营销号" }));
  expect(await screen.findByText("偏好已保存，Hermes后续整理会遵循它")).toBeVisible();
});

it("移除已有偏好", async () => {
  get.mockResolvedValue({ items: [{ id: 7, scope: "topic", effect: "prefer", value: "Agent长期记忆", kind: "all", note: "", active: true, createdAt: "2026-08-04T00:00:00Z", updatedAt: "2026-08-04T00:00:00Z" }] });
  renderPreferences();
  expect(await screen.findByText("Agent长期记忆")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "移除偏好Agent长期记忆" }));
  expect(remove).toHaveBeenCalledWith("/api/preferences/7");
});
