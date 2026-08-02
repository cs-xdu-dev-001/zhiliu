import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test } from "vitest";
import { App } from "./App";

beforeEach(() => {
  window.history.pushState({}, "", "/login");
});

test("直接显示应用，即使地址为/login", () => {
  render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);
  expect(screen.getByRole("heading", { name: "今日情报" })).toBeVisible();
  expect(screen.queryByText("登录")).not.toBeInTheDocument();
});
