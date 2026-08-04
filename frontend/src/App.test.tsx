import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";

vi.mock("./pages/ItemDetail", () => ({ ItemDetail: () => <p>情报详情内容</p> }));
vi.mock("./pages/BriefingDetail", () => ({ BriefingDetail: () => <p>报告详情内容</p> }));
vi.mock("./pages/TraceDetail", () => ({ TraceDetail: () => <p>处理链路内容</p> }));

afterEach(cleanup);

function renderApp(path: string) {
  window.history.pushState({}, "", path);
  return render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);
}

test("直接显示应用，即使地址为/login", () => {
  renderApp("/login");
  expect(screen.getByRole("heading", { name: "今日情报" })).toBeVisible();
  expect(screen.queryByText("登录")).not.toBeInTheDocument();
});

test("情报详情路由显示正确顶栏标题", () => {
  renderApp("/items/1?from=%2Ffeed%3Fstate%3Dunread");
  expect(screen.getByRole("heading", { name: "情报详情" })).toBeVisible();
  expect(screen.getByText("情报详情内容")).toBeVisible();
  expect(screen.getByRole("link", { name: "返回上一列表" })).toHaveAttribute("href", "/feed?state=unread");
  expect(document.title).toBe("情报详情 · 知流");
});

test("报告详情路由显示正确顶栏标题", () => {
  renderApp("/reports/1");
  expect(screen.getByRole("heading", { name: "报告详情" })).toBeVisible();
  expect(screen.getByText("报告详情内容")).toBeVisible();
});

test.each(["/items/1", "/reports/1", "/traces/1"])("详情页隐藏会覆盖内容的手机底部导航：%s", (path) => {
  renderApp(path);
  expect(screen.queryByRole("navigation", { name: "主导航" })).not.toBeInTheDocument();
});

test("筛选参数不影响顶栏和页签标题", () => {
  renderApp("/feed?state=saved&q=Agent");
  expect(screen.getByRole("heading", { name: "情报流" })).toBeVisible();
  expect(document.title).toBe("情报流 · 知流");
});

test("详情页拒绝跨站返回地址", () => {
  renderApp("/reports/1?from=https%3A%2F%2Fevil.example");
  expect(screen.getByRole("link", { name: "返回上一列表" })).toHaveAttribute("href", "/reports");
});

test("提供键盘跳转正文入口", () => {
  renderApp("/");
  expect(screen.getByRole("link", { name: "跳到主要内容" })).toHaveAttribute("href", "#main-content");
  expect(document.querySelector("main")).toHaveAttribute("id", "main-content");
});

test("手机主导航可直接进入内容质量", () => {
  renderApp("/quality");
  const qualityLink = within(screen.getByRole("navigation", { name: "主导航" })).getByRole("link", { name: "质量" });
  expect(qualityLink).toHaveAttribute("href", "/quality");
  expect(qualityLink).toHaveAttribute("aria-current", "page");
});
