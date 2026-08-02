import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { HermesConnection as HermesConnectionData } from "../types";
import { HermesConnection } from "./HermesConnection";

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("../api", () => ({ api: mocks }));

const connected: HermesConnectionData = {
  baseUrl: "http://hermes",
  apiKeyConfigured: true,
  apiKeyHint: "••••1234",
  status: "connected",
  message: "连接正常",
  checkedAt: "2026-01-01T00:00:00Z",
  version: "1.2.3",
};

afterEach(cleanup);
beforeEach(() => {
  mocks.get.mockReset().mockResolvedValue(connected);
  mocks.post.mockReset().mockResolvedValue(connected);
  mocks.put.mockReset().mockResolvedValue({
    ...connected,
    baseUrl: "http://new",
    apiKeyHint: "••••9999",
    status: "unauthorized",
    message: "密钥无效",
    version: null,
    checkedAt: null,
  });
});

function renderConnection() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <HermesConnection />
    </QueryClientProvider>,
  );
}

it("显示连接信息和掩码，不显示完整密钥", async () => {
  renderConnection();
  expect(await screen.findByText(/连接正常/)).toBeInTheDocument();
  expect(screen.getByText(/••••1234/)).toBeInTheDocument();
  expect(screen.getByText(/版本 1.2.3/)).toBeInTheDocument();
  expect(document.body.textContent).not.toContain("super-secret");
});

it("保存精确请求并显示未授权状态", async () => {
  renderConnection();
  await screen.findByText(/连接正常/);
  await userEvent.click(screen.getByRole("button", { name: "配置连接" }));
  await userEvent.clear(screen.getByLabelText("Hermes服务地址"));
  await userEvent.type(screen.getByLabelText("Hermes服务地址"), "http://new");
  await userEvent.type(screen.getByLabelText("Hermes API密钥"), "secret");
  await userEvent.click(screen.getByRole("button", { name: "保存并测试" }));
  expect(mocks.put).toHaveBeenCalledWith("/api/integrations/hermes", { baseUrl: "http://new", apiKey: "secret" });
  expect(await screen.findByText(/密钥无效/)).toBeInTheDocument();
});

it("测试已保存连接", async () => {
  renderConnection();
  await screen.findByText(/连接正常/);
  await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
  expect(mocks.post).toHaveBeenCalledWith("/api/integrations/hermes/test");
});

it("关闭重开后清空密钥并恢复触发按钮焦点", async () => {
  renderConnection();
  await screen.findByText(/连接正常/);
  const configure = screen.getByRole("button", { name: "配置连接" });
  await userEvent.click(configure);
  expect(screen.getByLabelText("Hermes服务地址")).toHaveFocus();
  await userEvent.type(screen.getByLabelText("Hermes API密钥"), "x");
  fireEvent.keyDown(document, { key: "Escape" });
  await waitFor(() => expect(configure).toHaveFocus());
  await userEvent.click(configure);
  expect(screen.getByLabelText("Hermes API密钥")).toHaveValue("");
});

it("空密钥按保留语义提交", async () => {
  renderConnection();
  await screen.findByText(/连接正常/);
  await userEvent.click(screen.getByRole("button", { name: "配置连接" }));
  await userEvent.click(screen.getByRole("button", { name: "保存并测试" }));
  expect(mocks.put).toHaveBeenCalledWith("/api/integrations/hermes", { baseUrl: "http://hermes", apiKey: "" });
});

it("以安全提示显示加载错误", async () => {
  mocks.get.mockRejectedValueOnce(new Error("secret-from-server"));
  renderConnection();
  expect(await screen.findByRole("alert")).toHaveTextContent("加载失败");
  expect(document.body.textContent).not.toContain("secret-from-server");
});

it("显示未配置状态", async () => {
  mocks.get.mockResolvedValueOnce({
    baseUrl: "",
    apiKeyConfigured: false,
    apiKeyHint: null,
    status: "unconfigured",
    message: "请配置",
    checkedAt: null,
    version: null,
  });
  renderConnection();
  expect(await screen.findByText(/未配置：请配置/)).toBeInTheDocument();
});

it("保存后从DOM移除输入过的密钥", async () => {
  mocks.put.mockResolvedValueOnce({ ...connected, apiKeyHint: "••••a9f2", checkedAt: null, version: null });
  renderConnection();
  await screen.findByText(/连接正常/);
  await userEvent.click(screen.getByRole("button", { name: "配置连接" }));
  await userEvent.type(screen.getByLabelText("Hermes API密钥"), "secret-a9f2");
  await userEvent.click(screen.getByRole("button", { name: "保存并测试" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(document.body.textContent).not.toContain("secret-a9f2");
  expect(screen.getByText(/••••a9f2/)).toBeInTheDocument();
});

it("点击遮罩关闭弹窗", async () => {
  renderConnection();
  await screen.findByText(/连接正常/);
  await userEvent.click(screen.getByRole("button", { name: "配置连接" }));
  const backdrop = document.querySelector(".dialog-backdrop")!;
  fireEvent.mouseDown(backdrop, { target: backdrop, currentTarget: backdrop });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("保存期间锁定操作并阻止Esc和遮罩关闭", async () => {
  let resolve!: (value: HermesConnectionData) => void;
  mocks.put.mockReturnValueOnce(new Promise<HermesConnectionData>((done) => { resolve = done; }));
  renderConnection();
  await screen.findByText(/连接正常/);
  await userEvent.click(screen.getByRole("button", { name: "配置连接" }));
  await userEvent.click(screen.getByRole("button", { name: "保存并测试" }));
  expect(screen.getByLabelText("Hermes服务地址")).toBeDisabled();
  expect(screen.getByLabelText("Hermes API密钥")).toBeDisabled();
  expect(screen.getByRole("button", { name: "关闭" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "测试连接" })).toBeDisabled();
  fireEvent.keyDown(document, { key: "Escape" });
  fireEvent.mouseDown(document.querySelector(".dialog-backdrop")!);
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  resolve(connected);
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

it("测试期间禁止打开配置和重复测试", async () => {
  let resolve!: (value: HermesConnectionData) => void;
  mocks.post.mockReturnValueOnce(new Promise<HermesConnectionData>((done) => { resolve = done; }));
  renderConnection();
  await screen.findByText(/连接正常/);
  await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
  expect(screen.getByRole("button", { name: "正在测试" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "配置连接" })).toBeDisabled();
  resolve(connected);
  await waitFor(() => expect(screen.getByRole("button", { name: "测试连接" })).toBeEnabled());
});

it("将键盘焦点限制在弹窗内", async () => {
  renderConnection();
  await screen.findByText(/连接正常/);
  await userEvent.click(screen.getByRole("button", { name: "配置连接" }));
  const close = screen.getByRole("button", { name: "关闭" });
  const save = screen.getByRole("button", { name: "保存并测试" });
  save.focus();
  await userEvent.tab();
  expect(close).toHaveFocus();
  await userEvent.tab({ shift: true });
  expect(save).toHaveFocus();
});

it("拒绝结构错误的接口响应", async () => {
  mocks.get.mockResolvedValueOnce({ status: "connected" });
  renderConnection();
  expect(await screen.findByRole("alert")).toHaveTextContent("加载失败");
  expect(document.body.textContent).not.toContain("undefined");
});

it("隐藏服务地址中的凭据并脱敏接口错误", async () => {
  mocks.get.mockResolvedValueOnce({ ...connected, baseUrl: "http://user:password@hermes.local:8642" });
  mocks.post.mockRejectedValueOnce(new Error("secret-api-key"));
  renderConnection();
  await screen.findByText(/连接正常/);
  expect(document.body.textContent).not.toContain("user:password");
  await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("连接测试失败");
  expect(document.body.textContent).not.toContain("secret-api-key");
});
