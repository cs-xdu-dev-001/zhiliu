import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { Subscriptions } from "./Subscriptions";

const { get, post, put, remove } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), remove: vi.fn() }));
vi.mock("../api", () => ({ api: { get, post, put, delete: remove } }));

beforeEach(() => {
  get.mockReset().mockResolvedValue([]);
  post.mockReset().mockResolvedValue({});
  put.mockReset().mockResolvedValue({});
  remove.mockReset().mockResolvedValue(undefined);
});

it("填写名称后创建订阅", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Subscriptions />
    </QueryClientProvider>,
  );
  await screen.findByText("还没有订阅");
  await userEvent.click(screen.getByRole("button", { name: "新建订阅" }));
  await userEvent.type(screen.getByLabelText("订阅名称"), "RAG论文");
  await userEvent.type(screen.getByLabelText("Hermes任务说明"), "检索过去7天RAG论文");
  await userEvent.click(screen.getByRole("button", { name: "保存订阅" }));

  expect(post).toHaveBeenCalledWith("/api/subscriptions", expect.objectContaining({ name: "RAG论文" }));
});
