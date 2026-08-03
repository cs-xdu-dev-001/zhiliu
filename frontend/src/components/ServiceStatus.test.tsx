import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ServiceStatus } from "./ServiceStatus";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../api", () => ({ api: { get } }));

function renderStatus() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ServiceStatus /></QueryClientProvider>);
}

beforeEach(() => {
  get.mockReset().mockResolvedValue({ status: "ok" });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("服务不可达时允许重试并提示恢复", async () => {
  get.mockRejectedValueOnce(new Error("unavailable")).mockResolvedValue({ status: "ok" });
  renderStatus();

  expect(await screen.findByRole("alert")).toHaveTextContent("无法连接知流服务");
  await userEvent.click(screen.getByRole("button", { name: "立即重试" }));
  expect(await screen.findByRole("status")).toHaveTextContent("连接已恢复");
  expect(get).toHaveBeenCalledWith("/api/health");
});

it("浏览器离线时等待网络自动恢复", async () => {
  vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(false);
  renderStatus();

  expect(await screen.findByRole("alert")).toHaveTextContent("网络已断开");
  expect(screen.queryByRole("button", { name: "立即重试" })).not.toBeInTheDocument();
  expect(get).not.toHaveBeenCalled();
});
