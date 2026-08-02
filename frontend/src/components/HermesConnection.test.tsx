import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { HermesConnection } from "./HermesConnection";
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("../api", () => ({ api: mocks }));
afterEach(cleanup);
beforeEach(() => { mocks.get.mockReset(); mocks.post.mockReset(); mocks.put.mockReset(); mocks.get.mockResolvedValue({ baseUrl:"http://hermes", apiKeyConfigured:true, apiKeyHint:"••••1234", status:"connected", message:"连接正常", checkedAt:"2026-01-01T00:00:00Z", version:"1.2.3" }); mocks.post.mockResolvedValue({ ...mocks.get.mock.results[0]?.value, status:"connected" }); mocks.put.mockResolvedValue({ baseUrl:"http://new", apiKeyConfigured:true, apiKeyHint:"••••9999", status:"unauthorized", message:"密钥无效", version:null, checkedAt:null }); });
function renderIt(){ return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><HermesConnection/></QueryClientProvider>); }
it("shows connected details without secret", async()=>{ renderIt(); expect(await screen.findByText(/连接正常/)).toBeInTheDocument(); expect(screen.getByText(/版本 1.2.3/)).toBeInTheDocument(); expect(document.body.textContent).not.toContain("super-secret"); });
it("saves exact body and displays unauthorized", async()=>{ renderIt(); await screen.findByText(/连接正常/); await userEvent.click(screen.getByRole("button",{name:"配置连接"})); await userEvent.clear(screen.getByLabelText("Hermes服务地址")); await userEvent.type(screen.getByLabelText("Hermes服务地址"),"http://new"); await userEvent.type(screen.getByLabelText("Hermes API密钥"),"secret"); await userEvent.click(screen.getByRole("button",{name:"保存并测试"})); expect(mocks.put).toHaveBeenCalledWith("/api/integrations/hermes",{baseUrl:"http://new",apiKey:"secret"}); expect(await screen.findByText(/密钥无效/)).toBeInTheDocument(); });
it("tests saved connection", async()=>{ renderIt(); await screen.findByText(/连接正常/); await userEvent.click(screen.getByRole("button",{name:"测试连接"})); expect(mocks.post).toHaveBeenCalledWith("/api/integrations/hermes/test"); });
it("clears key on reopen and supports escape", async()=>{ renderIt(); await screen.findByText(/连接正常/); await userEvent.click(screen.getByRole("button",{name:"配置连接"})); await userEvent.type(screen.getByLabelText("Hermes API密钥"),"x"); await userEvent.keyboard("{Escape}"); await userEvent.click(screen.getByRole("button",{name:"配置连接"})); expect(screen.getByLabelText("Hermes API密钥")).toHaveValue(""); });
