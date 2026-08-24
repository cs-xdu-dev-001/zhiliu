import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { FeedbackPanel } from "./FeedbackPanel";

const { get, patch, post } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), post: vi.fn() }));
vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  api: { get, patch, post },
}));

const feedback = {
  id: 7, itemId: 1, briefingId: null, topicId: null, preferenceId: null,
  feedbackType: "summary_wrong" as const, impactScope: "current" as const,
  note: "遗漏了发布时间", active: true, version: 1,
  createdAt: "2026-08-24T08:00:00Z", updatedAt: "2026-08-24T08:00:00Z", revokedAt: null,
};

beforeEach(() => {
  get.mockReset().mockResolvedValue({ items: [] });
  post.mockReset().mockResolvedValue(feedback);
  patch.mockReset().mockResolvedValue({ ...feedback, note: "遗漏发布时间和范围", version: 2 });
});

afterEach(cleanup);

function renderPanel() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <FeedbackPanel targetType="item" targetId={1} />
  </QueryClientProvider>);
}

it("展开后才查询历史并提交带说明的摘要修正", async () => {
  renderPanel();
  expect(get).not.toHaveBeenCalled();
  await userEvent.click(screen.getByText("反馈与修正"));
  expect(await screen.findByText("暂无反馈记录")).toBeVisible();
  expect(get).toHaveBeenCalledWith("/api/feedback?itemId=1");

  await userEvent.click(screen.getByRole("button", { name: "摘要有误" }));
  await userEvent.type(screen.getByRole("textbox", { name: "反馈说明" }), "遗漏了发布时间");
  await userEvent.click(screen.getByRole("button", { name: "确认反馈" }));

  expect(post).toHaveBeenCalledWith("/api/feedback", expect.objectContaining({
    targetType: "item", targetId: 1, feedbackType: "summary_wrong",
    note: "遗漏了发布时间", applyLongTerm: false, idempotencyKey: expect.any(String),
  }));
  expect(await screen.findByRole("status")).toHaveTextContent("仅当前内容");
});

it("只有显式勾选才形成Hermes长期偏好", async () => {
  post.mockResolvedValue({ ...feedback, feedbackType: "follow_up", impactScope: "long_term", preferenceId: 12 });
  renderPanel();
  await userEvent.click(screen.getByText("反馈与修正"));
  await screen.findByText("暂无反馈记录");
  await userEvent.click(screen.getByRole("button", { name: "持续关注" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "同时形成Hermes长期偏好" }));
  await userEvent.click(screen.getByRole("button", { name: "确认反馈" }));

  expect(post).toHaveBeenCalledWith("/api/feedback", expect.objectContaining({ feedbackType: "follow_up", applyLongTerm: true }));
  expect(await screen.findByRole("status")).toHaveTextContent("Hermes长期偏好");
});

it("报告反馈不提供长期偏好开关", async () => {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <FeedbackPanel targetType="briefing" targetId={2} />
  </QueryClientProvider>);
  await userEvent.click(screen.getByText("反馈与修正"));
  await screen.findByText("暂无反馈记录");
  await userEvent.click(screen.getByRole("button", { name: "持续关注" }));
  expect(screen.queryByRole("checkbox", { name: "同时形成Hermes长期偏好" })).not.toBeInTheDocument();
});

it("历史反馈可修改并撤销", async () => {
  get.mockResolvedValue({ items: [feedback] });
  post
    .mockResolvedValueOnce({ ...feedback, active: false, version: 2, revokedAt: "2026-08-24T09:00:00Z" })
    .mockResolvedValueOnce({ ...feedback, active: true, version: 3 });
  renderPanel();
  await userEvent.click(screen.getByText("反馈与修正"));
  expect(await screen.findByText("遗漏了发布时间")).toBeVisible();

  await userEvent.click(screen.getByRole("button", { name: "修改" }));
  await userEvent.clear(screen.getByRole("textbox", { name: "修改反馈说明" }));
  await userEvent.type(screen.getByRole("textbox", { name: "修改反馈说明" }), "遗漏发布时间和范围");
  await userEvent.click(screen.getByRole("button", { name: "保存" }));
  expect(patch).toHaveBeenCalledWith("/api/feedback/7", { version: 1, note: "遗漏发布时间和范围" });

  await userEvent.click(screen.getByRole("button", { name: "撤销" }));
  expect(post).toHaveBeenCalledWith("/api/feedback/7/revoke", { version: 1 });
});

it("已撤销反馈可以恢复", async () => {
  const revoked = { ...feedback, active: false, version: 2, revokedAt: "2026-08-24T09:00:00Z" };
  get.mockResolvedValue({ items: [revoked] });
  post.mockResolvedValue({ ...revoked, active: true, version: 3, revokedAt: null });
  renderPanel();
  await userEvent.click(screen.getByText("反馈与修正"));
  await userEvent.click(await screen.findByRole("button", { name: "恢复" }));
  expect(post).toHaveBeenCalledWith("/api/feedback/7/restore", { version: 2 });
  expect(await screen.findByRole("status")).toHaveTextContent("反馈已恢复");
});
