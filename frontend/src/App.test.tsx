import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";

vi.mock("./pages/ItemDetail", () => ({ ItemDetail: () => <p>情报详情内容</p> }));
vi.mock("./pages/BriefingDetail", () => ({ BriefingDetail: () => <p>报告详情内容</p> }));

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
  renderApp("/items/1");
  expect(screen.getByRole("heading", { name: "情报详情" })).toBeVisible();
  expect(screen.getByText("情报详情内容")).toBeVisible();
});

test("报告详情路由显示正确顶栏标题", () => {
  renderApp("/reports/1");
  expect(screen.getByRole("heading", { name: "报告详情" })).toBeVisible();
  expect(screen.getByText("报告详情内容")).toBeVisible();
});
