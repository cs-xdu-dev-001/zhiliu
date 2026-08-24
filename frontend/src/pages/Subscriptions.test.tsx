import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Subscriptions } from "./Subscriptions";

const { get, post, put, remove, download } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), remove: vi.fn(), download: vi.fn() }));
vi.mock("../api", () => ({ api: { get, post, put, delete: remove, download } }));

afterEach(cleanup);

beforeEach(() => {
  window.history.pushState({}, "", "/settings");
  get.mockReset().mockImplementation((url: string) => {
    if (url.includes("/api/integrations/hermes")) return Promise.resolve({ baseUrl: "", apiKeyConfigured: false, apiKeyHint: null, status: "unconfigured", message: "请配置", checkedAt: null, version: null });
    if (url.includes("/api/diagnostics")) return Promise.resolve({ status: "ok", generatedAt: "2026-08-24T00:00:00Z", database: { status: "ok", latencyMs: 2, migrationVersion: "head" }, scheduler: { enabled: true, running: true, jobCount: 2, lastQueuePollAt: null, lastQueuePollFailed: false, lastSweepAt: null, lastSweepLostCount: 0 }, queue: { queued: 0, running: 0, oldestActiveSeconds: null, lastSuccessAt: null, lastFailureAt: null }, hermes: { configured: false, status: "unconfigured", checkedAt: null }, mcp: { status: "unverified", lastWriteAt: null, lastTaskStatus: null, lastTaskAt: null } });
    return Promise.resolve([]);
  });
  post.mockReset().mockResolvedValue({});
  put.mockReset().mockResolvedValue({});
  remove.mockReset().mockResolvedValue(undefined);
  download.mockReset().mockResolvedValue({ blob: new Blob(), filename: "export.json" });
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
  await userEvent.click(screen.getByRole("button", { name: "编辑Agent论文周报" }));
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
  const trigger = screen.getByRole("button", { name: "新建订阅" });
  await userEvent.click(trigger);
  expect(document.body.style.overflow).toBe("hidden");
  await userEvent.keyboard("{Escape}");

  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(document.body.style.overflow).toBe("");
  expect(trigger).toHaveFocus();
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

  expect(await screen.findByText("Agent论文周报已加入任务队列")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "查看任务进度" })).toHaveAttribute("href", "/tasks");
});

it("搜索筛选订阅并展示下次执行时间", async () => {
  get.mockImplementation((url: string) => url.includes("/api/integrations/hermes")
    ? Promise.resolve({ baseUrl: "", apiKeyConfigured: false, apiKeyHint: null, status: "unconfigured", message: "请配置", checkedAt: null, version: null })
    : Promise.resolve([
        { id: 7, name: "Agent论文周报", kind: "paper", keywords: ["Agent"], schedule: "0 8 * * 1", prompt: "检索论文", enabled: true, lastRunAt: null, nextRunAt: "2026-08-10T00:00:00Z", createdAt: "2026-08-01T00:00:00Z", updatedAt: "2026-08-01T00:00:00Z" },
        { id: 8, name: "AI招聘", kind: "job", keywords: ["Python"], schedule: "0 8 * * *", prompt: "检索岗位", enabled: false, lastRunAt: null, nextRunAt: null, createdAt: "2026-08-01T00:00:00Z", updatedAt: "2026-08-01T00:00:00Z" },
      ]));

  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Subscriptions />
    </QueryClientProvider>,
  );

  expect(await screen.findByText(/下次/)).toBeVisible();
  await userEvent.type(screen.getByRole("searchbox", { name: "搜索订阅" }), "Python");
  expect(screen.getByText("AI招聘")).toBeVisible();
  expect(screen.queryByText("Agent论文周报")).not.toBeInTheDocument();
  expect(screen.getByText("1个订阅")).toBeVisible();
  expect(screen.getByText("已暂停自动执行")).toBeVisible();
});

it("停用订阅需要明确确认", async () => {
  const record = {
    id: 7, name: "Agent论文周报", kind: "paper", keywords: ["Agent"], schedule: "0 8 * * 1", prompt: "检索过去一周的重要论文", enabled: true, lastRunAt: null, nextRunAt: "2026-08-10T00:00:00Z", createdAt: "2026-08-01T00:00:00Z", updatedAt: "2026-08-01T00:00:00Z",
  };
  get.mockImplementation((url: string) => url.includes("/api/integrations/hermes")
    ? Promise.resolve({ baseUrl: "", apiKeyConfigured: false, apiKeyHint: null, status: "unconfigured", message: "请配置", checkedAt: null, version: null })
    : Promise.resolve([record]));

  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Subscriptions />
    </QueryClientProvider>,
  );

  await screen.findByText("Agent论文周报");
  await userEvent.click(screen.getByRole("checkbox", { name: "暂停Agent论文周报" }));
  expect(put).not.toHaveBeenCalled();
  expect(screen.getByRole("alertdialog", { name: "暂停“Agent论文周报”？" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "确认暂停" }));
  expect(put).toHaveBeenCalledWith("/api/subscriptions/7", expect.objectContaining({ enabled: false }));
});

it("暂停确认支持Escape并把焦点还给开关", async () => {
  const record = {
    id: 7, name: "Agent论文周报", kind: "paper", keywords: ["Agent"], schedule: "0 8 * * 1", prompt: "检索过去一周的重要论文", enabled: true, lastRunAt: null, nextRunAt: null, createdAt: "2026-08-01T00:00:00Z", updatedAt: "2026-08-01T00:00:00Z",
  };
  get.mockResolvedValue([record]);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Subscriptions />
    </QueryClientProvider>,
  );

  const trigger = await screen.findByRole("checkbox", { name: "暂停Agent论文周报" });
  await userEvent.click(trigger);
  await waitFor(() => expect(screen.getByRole("button", { name: "继续订阅" })).toHaveFocus());
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

it("订阅列表分页限制首屏渲染量", async () => {
  get.mockResolvedValue(Array.from({ length: 21 }, (_, index) => ({
    id: index + 1, name: `订阅${index + 1}`, kind: "news", keywords: [], schedule: "0 8 * * *", prompt: "检索更新", enabled: true, lastRunAt: null, nextRunAt: null, createdAt: "2026-08-01T00:00:00Z", updatedAt: "2026-08-01T00:00:00Z",
  })));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Subscriptions />
    </QueryClientProvider>,
  );

  expect(await screen.findByText("订阅1")).toBeVisible();
  expect(screen.queryByText("订阅21")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect(screen.getByText("订阅21")).toBeVisible();
  expect(screen.queryByText("订阅1")).not.toBeInTheDocument();
});

it("用独立视图切换订阅管理和Hermes运行设置", async () => {
  get.mockImplementation((url: string) => {
    if (url.includes("/api/integrations/hermes")) return Promise.resolve({ baseUrl: "", apiKeyConfigured: false, apiKeyHint: null, status: "unconfigured", message: "请配置", checkedAt: null, version: null });
    if (url.includes("/api/diagnostics")) return Promise.resolve({ status: "ok", generatedAt: "2026-08-24T00:00:00Z", database: { status: "ok", latencyMs: 2, migrationVersion: "head" }, scheduler: { enabled: true, running: true, jobCount: 2, lastQueuePollAt: null, lastQueuePollFailed: false, lastSweepAt: null, lastSweepLostCount: 0 }, queue: { queued: 0, running: 0, oldestActiveSeconds: null, lastSuccessAt: null, lastFailureAt: null }, hermes: { configured: false, status: "unconfigured", checkedAt: null }, mcp: { status: "unverified", lastWriteAt: null, lastTaskStatus: null, lastTaskAt: null } });
    return Promise.resolve([{
        id: 7, name: "Agent论文周报", kind: "paper", keywords: ["Agent"], schedule: "0 8 * * 1", prompt: "检索论文", enabled: true, lastRunAt: null, nextRunAt: null, createdAt: "2026-08-01T00:00:00Z", updatedAt: "2026-08-01T00:00:00Z",
      }]);
  });

  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Subscriptions />
    </QueryClientProvider>,
  );

  expect(await screen.findByText("Agent论文周报")).toBeVisible();
  expect(screen.queryByRole("heading", { name: "Hermes连接" })).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("link", { name: "Hermes与运行" }));
  expect(window.location.search).toBe("?view=runtime");
  expect(await screen.findByRole("heading", { name: "Hermes连接" })).toBeVisible();
  expect(screen.queryByText("Agent论文周报")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "新建订阅" })).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("link", { name: "订阅" }));
  expect(window.location.search).toBe("");
  expect(await screen.findByText("Agent论文周报")).toBeVisible();
});

it("数据导出使用独立设置视图", async () => {
  get.mockImplementation((url: string) => url.includes("/api/topics")
    ? Promise.resolve({ items: [], total: 0, limit: 100, offset: 0 })
    : Promise.resolve([]));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Subscriptions />
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole("link", { name: "数据导出" }));
  expect(window.location.search).toBe("?view=data");
  expect(screen.getByRole("heading", { name: "数据导出" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "新建订阅" })).not.toBeInTheDocument();
});
