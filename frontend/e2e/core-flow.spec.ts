import { expect, test, type Page, type TestInfo } from "@playwright/test";

async function assertNoOverflow(page: Page) {
  const hasOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasOverflow).toBe(false);
}

async function capture(page: Page, testInfo: TestInfo, name: string, fullPage = true) {
  await assertNoOverflow(page);
  await page.screenshot({ path: testInfo.outputPath(`${name}.png`), fullPage });
}

test("首次使用时从微信指令开始", async ({ page, context }, testInfo) => {
  await page.route("**/api/dashboard", (route) => route.fulfill({
    json: {
      unreadCount: 0,
      savedCount: 0,
      activeSubscriptions: 0,
      failedRuns: 0,
      topItems: [],
      latestBriefing: null,
      recentRuns: [],
    },
  }));
  await page.route("**/api/integrations/hermes", (route) => route.fulfill({
    json: {
      baseUrl: "http://hermes:8642",
      apiKeyConfigured: true,
      apiKeyHint: "••••1234",
      status: "connected",
      message: "连接正常",
      checkedAt: "2026-08-03T10:00:00Z",
      version: "1.0.0",
    },
  }));
  await page.goto("/");
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: new URL(page.url()).origin });

  await expect(page.getByRole("heading", { name: "从微信发出第一条知流指令" })).toBeVisible();
  await page.getByRole("button", { name: "复制示例指令" }).click();
  await expect(page.getByRole("button", { name: "已复制，去微信发送" })).toBeVisible();
  await capture(page, testInfo, "first-use");
});

test("阅读情报并触发订阅", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "今日情报" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "需要处理" })).toBeVisible();
  await expect(page.getByRole("link", { name: /查看异常任务/ })).toBeVisible();
  await capture(page, testInfo, "home");

  await page.getByRole("link", { name: "情报", exact: true }).click();
  const readButton = page.getByRole("button", { name: "标记已读" }).first();
  if (await readButton.isVisible()) await readButton.click();
  await capture(page, testInfo, "feed");

  const search = page.getByRole("searchbox", { name: "搜索情报" });
  await search.fill("RAG");
  await expect(page).toHaveURL(/q=RAG/);
  await expect(page).toHaveTitle("情报流 · 知流");
  await expect(page.getByRole("heading", { name: "开源RAG评测工具发布新版本" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "代码Agent开始强调仓库级上下文" })).toBeHidden();
  await capture(page, testInfo, "feed-search", false);
  await page.getByRole("button", { name: "清除搜索" }).click();
  await expect(search).toHaveValue("");
  await expect(page.getByRole("heading", { name: "代码Agent开始强调仓库级上下文" })).toBeVisible();
  await page.getByRole("button", { name: "批量选择" }).click();
  await page.getByRole("checkbox", { name: /选择开源RAG评测工具发布新版本/ }).check();
  await capture(page, testInfo, "feed-bulk-selection", false);
  await page.getByRole("button", { name: "收藏所选" }).click();
  await expect(page.getByText(/^已处理\d+条/)).toBeVisible();
  await page.getByRole("button", { name: "退出批量" }).click();

  await page.getByRole("link", { name: "报告", exact: true }).click();
  await expect(page.getByRole("heading", { name: "定期报告" })).toBeVisible();
  await capture(page, testInfo, "reports");
  const reportSearch = page.getByRole("searchbox", { name: "搜索报告" });
  await reportSearch.fill("Agent");
  await expect(page).toHaveURL(/q=Agent/);
  await expect(page.getByRole("link", { name: /Agent论文周报/ })).toBeVisible();
  await capture(page, testInfo, "reports-search", false);
  await page.getByRole("button", { name: "清除报告搜索" }).click();
  await expect.poll(() => new URL(page.url()).searchParams.has("q")).toBe(false);

  await page.getByRole("link", { name: "设置", exact: true }).click();
  await expect(page.getByRole("button", { name: "新建订阅" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hermes连接" })).toBeVisible();
  await expect(page.getByRole("button", { name: "测试连接" })).toBeVisible();
  await capture(page, testInfo, "subscriptions");
  const subscriptionName = `E2E测试订阅-${testInfo.project.name}`;
  await page.getByRole("button", { name: "新建订阅" }).click();
  await page.getByLabel("订阅名称").fill(subscriptionName);
  await page.getByLabel("关键词").fill("测试");
  await page.getByLabel("Hermes任务说明").fill("执行E2E测试任务");
  await page.getByRole("button", { name: "保存订阅" }).click();
  await expect(page.getByText("订阅已创建")).toBeVisible();
  const subscriptionSearch = page.getByRole("searchbox", { name: "搜索订阅" });
  await subscriptionSearch.fill(subscriptionName);
  await expect(page.getByText(subscriptionName)).toBeVisible();
  await capture(page, testInfo, "subscriptions-search");
  await page.getByTitle("暂停订阅").click();
  await expect(page.getByRole("alertdialog", { name: `暂停${subscriptionName}` })).toBeVisible();
  await capture(page, testInfo, "subscription-pause-confirm");
  await page.getByRole("button", { name: "继续订阅" }).click();
  await page.getByRole("button", { name: "清除订阅搜索" }).click();
  await page.getByRole("button", { name: `立即执行${subscriptionName}` }).click();
  await expect(page.getByText(`${subscriptionName}已加入任务队列`)).toBeVisible();
  await page.getByRole("link", { name: "任务记录" }).click();
  await expect(page.getByText(/已受理|处理中|已完成/).first()).toBeVisible();
  await capture(page, testInfo, "tasks");
  await page.locator(".task-row-link").first().click();
  await expect(page.getByRole("heading", { name: /E2E测试订阅/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "当前阶段" })).toBeVisible();
  await capture(page, testInfo, "task-detail");
  await page.getByRole("link", { name: "返回上一列表" }).click();
  await page.getByRole("link", { name: /AI工程岗位/ }).click();
  await expect(page.getByRole("link", { name: "检查订阅与Hermes连接" })).toBeVisible();
  await capture(page, testInfo, "task-detail-failed");
});

test("报告来源可以追溯到Hermes处理链路", async ({ page, context }, testInfo) => {
  await page.goto("/reports");
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: new URL(page.url()).origin });
  await page.getByRole("link", { name: /AI热点日报/ }).click();
  await expect(page).toHaveTitle("报告详情 · 知流");
  await expect(page.getByRole("link", { name: "返回上一列表" })).toHaveAttribute("href", "/reports");
  await expect(page.getByRole("heading", { name: "来源情报" })).toBeVisible();
  await expect(page.getByRole("link", { name: "查看生成链路" })).toBeVisible();
  await page.getByRole("button", { name: "复制摘要" }).click();
  await expect(page.getByText("报告摘要已复制")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出Markdown" }).click();
  await download;
  await expect(page.getByText("Markdown报告已导出")).toBeVisible();
  await capture(page, testInfo, "report-detail-with-sources");

  await page.getByRole("link", { name: "Hermes Agent增加异步Run接口" }).click();
  await expect(page.getByRole("heading", { name: "写入记录" })).toBeVisible();
  await capture(page, testInfo, "item-detail-with-lineage");

  await page.getByRole("link", { name: "查看完整链路" }).click();
  await expect(page.getByRole("heading", { name: "完整处理链路" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "定时订阅输入" })).toBeVisible();
  await expect(page.getByText("demo-hermes-news")).toBeVisible();
  await expect(page.getByRole("heading", { name: "报告生成" })).toBeVisible();
  await capture(page, testInfo, "trace-detail");
});

test("维护情报并保留修改记录", async ({ page }, testInfo) => {
  await page.goto("/reports");
  await page.getByRole("link", { name: /AI热点日报/ }).click();
  await page.getByRole("link", { name: "Hermes Agent增加异步Run接口" }).click();

  await page.getByRole("button", { name: "编辑内容" }).click();
  await expect(page.getByRole("dialog", { name: "编辑情报" })).toBeVisible();
  await capture(page, testInfo, "item-edit-dialog");
  await page.getByLabel("摘要").fill("经人工核对：外部系统现已支持创建、跟踪和停止长时间Agent任务。");
  await page.getByRole("button", { name: "保存修改" }).click();
  await expect(page.getByText("内容已更新，修改记录已保留")).toBeVisible();
  await expect(page.getByText("编辑内容").last()).toBeVisible();

  await page.getByRole("button", { name: "标记无效" }).click();
  await expect(page.getByText("已标记无效", { exact: true }).last()).toBeVisible();
  await page.getByRole("button", { name: "恢复有效" }).click();
  await expect(page.getByText("已恢复有效", { exact: true }).last()).toBeVisible();

  await page.getByRole("button", { name: "合并重复" }).click();
  await expect(page.getByRole("dialog", { name: "合并重复情报" })).toBeVisible();
  await capture(page, testInfo, "item-merge-dialog");
});

test("网络中断后提示并自动恢复", async ({ page, context }, testInfo) => {
  await page.goto("/");
  await context.setOffline(true);
  await page.evaluate(() => window.dispatchEvent(new Event("offline")));
  await expect(page.getByRole("alert")).toContainText("网络已断开");
  await capture(page, testInfo, "offline-status", false);

  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.getByRole("status")).toContainText("连接已恢复");
});
