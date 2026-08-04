import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { SubscriptionHealth } from "./SubscriptionHealth";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../api", () => ({ api: { get } }));
afterEach(cleanup);
beforeEach(() => get.mockReset().mockResolvedValue({ generatedAt: "2026-08-04T00:00:00Z", items: [{ subscriptionId: 7, name: "Agent日报", kind: "news", enabled: true, nextRunAt: null, lastSuccessAt: "2026-08-03T08:00:00Z", lastFailureAt: null, runCount: 10, successCount: 10, failedCount: 0, successRate: 1, consecutiveFailures: 0, averageDurationMs: 1200, producedItemCount: 16 }] }));

it("展示订阅成功率和产出量", async () => {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SubscriptionHealth /></QueryClientProvider>);
  expect(await screen.findByText("Agent日报")).toBeVisible();
  expect(screen.getByText("100%成功")).toBeVisible();
  expect(screen.getByText("16条产出")).toBeVisible();
});
