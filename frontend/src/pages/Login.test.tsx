import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { Login } from "./Login";

const { navigate, post } = vi.hoisted(() => ({ navigate: vi.fn(), post: vi.fn() }));

vi.mock("wouter", async () => {
  const actual = await vi.importActual<typeof import("wouter")>("wouter");
  return { ...actual, useLocation: () => ["/login", navigate] };
});

vi.mock("../api", () => ({ api: { post } }));

beforeEach(() => {
  navigate.mockReset();
  post.mockReset().mockResolvedValue(undefined);
});

it("提交账号后进入首页", async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <Login />
    </QueryClientProvider>,
  );

  await userEvent.type(screen.getByLabelText("用户名"), "admin");
  await userEvent.type(screen.getByLabelText("密码"), "secret");
  await userEvent.click(screen.getByRole("button", { name: "登录" }));

  expect(post).toHaveBeenCalledWith("/api/auth/login", { username: "admin", password: "secret" });
  expect(navigate).toHaveBeenCalledWith("/");
});
