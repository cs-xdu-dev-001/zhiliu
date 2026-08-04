import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";

import { SearchPage } from "./Search";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../api", () => ({ api: { get } }));

afterEach(cleanup);
beforeEach(() => {
  window.history.replaceState({}, "", "/search?q=Agent");
  get.mockReset().mockResolvedValue({
    query: "Agent", itemTotal: 1, briefingTotal: 1,
    items: [{ id: 4, kind: "news", title: "Agent框架更新", summary: "工具调用更稳定。", source: "微信Hermes", url: "https://example.com", createdAt: "2026-08-04T00:00:00Z" }],
    briefings: [{ id: 2, kind: "news", title: "Agent趋势简报", summary: "本期汇总框架更新。", itemCount: 3, createdAt: "2026-08-04T00:00:00Z" }],
  });
});

function renderPage() {
  const { hook } = memoryLocation({ path: "/search?q=Agent" });
  return render(<Router hook={hook}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SearchPage /></QueryClientProvider></Router>);
}

it("按自然语言搜索并分组展示情报和报告", async () => {
  renderPage();
  expect(await screen.findByText("Agent框架更新")).toBeVisible();
  expect(screen.getByText("Agent趋势简报")).toBeVisible();
  expect(screen.getByText("2条结果")).toBeVisible();
  expect(get).toHaveBeenCalledWith(expect.stringContaining("/api/search?q=Agent"));
  expect(screen.getByRole("link", { name: /Agent框架更新/ })).toHaveAttribute("href", expect.stringContaining("/items/4"));
});

it("不足两个字符时不发起搜索", async () => {
  window.history.replaceState({}, "", "/search?q=A");
  const { hook } = memoryLocation({ path: "/search?q=A" });
  render(<Router hook={hook}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SearchPage /></QueryClientProvider></Router>);
  expect(screen.getByText("请至少输入2个字符。")).toBeVisible();
  expect(get).not.toHaveBeenCalled();
  await userEvent.clear(screen.getByRole("textbox", { name: "搜索情报和报告" }));
});
