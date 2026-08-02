import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Subscriptions } from "./Subscriptions";

const { get, post, put, remove } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), remove: vi.fn() }));
vi.mock("../api", () => ({ api: { get, post, put, delete: remove } }));

afterEach(cleanup);

beforeEach(() => {
  get.mockReset().mockImplementation((url: string) => url.includes("/api/integrations/hermes") ? Promise.resolve({ baseUrl: "", apiKeyConfigured: false, apiKeyHint: null, status: "unconfigured", message: "请配置", checkedAt: null, version: null }) : Promise.resolve([]));
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

it("用常用选项选择执行周期", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Subscriptions />
    </QueryClientProvider>,
  );

  await screen.findByText("还没有订阅");
  await userEvent.click(screen.getByRole("button", { name: "新建订阅" }));

  expect(screen.getByRole("combobox", { name: "执行周期" })).toHaveValue("0 8 * * *");
  expect(screen.getByRole("option", { name: "每天 08:00" })).toBeInTheDocument();
});

it("确认后才删除订阅", async () => {
  get.mockResolvedValue([{
    id: 7,
    name: "Agent论文周报",
    kind: "paper",
    keywords: ["Agent"],
    schedule: "0 8 * * 1",
    prompt: "检索过去一周的重要论文",
    enabled: true,
    lastRunAt: null,
    nextRunAt: null,
    createdAt: "2026-08-01T00:00:00Z",
    updatedAt: "2026-08-01T00:00:00Z",
  }]);

  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Subscriptions />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent论文周报");
  await userEvent.click(screen.getByRole("button", { name: "编辑订阅" }));
  await userEvent.click(screen.getByRole("button", { name: "删除订阅" }));

  expect(remove).not.toHaveBeenCalled();
  expect(screen.getByText("删除“Agent论文周报”？")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "确认删除订阅" }));
  expect(remove).toHaveBeenCalledWith("/api/subscriptions/7");
});

it("按Escape关闭订阅对话框", async () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Subscriptions />
    </QueryClientProvider>,
  );

  await screen.findByText("还没有订阅");
  await userEvent.click(screen.getByRole("button", { name: "新建订阅" }));
  await userEvent.keyboard("{Escape}");

  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("立即执行后宣布任务已提交", async () => {
  get.mockResolvedValue([{
    id: 7,
    name: "Agent论文周报",
    kind: "paper",
    keywords: ["Agent"],
    schedule: "0 8 * * 1",
    prompt: "检索过去一周的重要论文",
    enabled: true,
    lastRunAt: null,
    nextRunAt: null,
    createdAt: "2026-08-01T00:00:00Z",
    updatedAt: "2026-08-01T00:00:00Z",
  }]);

  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Subscriptions />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent论文周报");
  await userEvent.click(screen.getByRole("button", { name: "立即执行Agent论文周报" }));

  expect(await screen.findByRole("status")).toHaveTextContent("Agent论文周报已加入任务队列");
});
