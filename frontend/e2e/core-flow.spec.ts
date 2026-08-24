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

test("Hermes暂时离线时首页保持内容优先", async ({ page }, testInfo) => {
  await page.route("**/api/integrations/hermes", (route) => route.fulfill({
    json: {
      baseUrl: "http://hermes:8642",
      apiKeyConfigured: true,
      apiKeyHint: "••••1234",
      status: "unreachable",
      message: "连接超时",
      checkedAt: "2026-08-03T10:00:00Z",
      version: null,
    },
  }));

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "优先阅读" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Hermes离线" })).toHaveAttribute("href", "/settings?view=runtime");
  await expect(page.locator(".home-connection-note")).toHaveCount(0);
  await capture(page, testInfo, "home-hermes-offline");
});

test("阅读情报并触发订阅", async ({ page }, testInfo) => {
  if (testInfo.project.name === "mobile") await page.setViewportSize({ width: 320, height: 740 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "今日情报" })).toBeVisible();
  await expect(page.getByRole("region", { name: "需要处理" })).toBeVisible();
  await expect(page.getByRole("link", { name: /查看异常任务/ })).toBeVisible();
  if (testInfo.project.name === "mobile") {
    const priorityHeading = await page.getByRole("heading", { name: "优先阅读" }).boundingBox();
    expect(priorityHeading).not.toBeNull();
    expect(priorityHeading!.y).toBeLessThan(740);
  }
  const briefingPanel = await page.locator(".home-briefing").boundingBox();
  const briefingCard = await page.locator(".home-briefing .briefing-card").boundingBox();
  expect(briefingPanel).not.toBeNull();
  expect(briefingCard).not.toBeNull();
  expect(briefingPanel!.height - briefingCard!.height).toBeLessThanOrEqual(90);
  await capture(page, testInfo, "home");

  await page.getByRole("link", { name: "情报", exact: true }).click();
  await expect(page.getByRole("button", { name: "招聘" })).toBeVisible();
  const sortFilter = page.getByRole("combobox", { name: "情报排序" });
  const stateFilter = page.getByRole("combobox", { name: "情报状态" });
  const timeFilter = page.getByRole("combobox", { name: "情报时间" });
  const sourceFilter = page.getByRole("combobox", { name: "情报来源" });
  await expect(sortFilter).toBeVisible();
  await expect(stateFilter).toBeVisible();
  await expect(timeFilter).toBeVisible();
  await expect(sourceFilter).toBeVisible();
  const sortFilterBox = await sortFilter.boundingBox();
  const stateFilterBox = await stateFilter.boundingBox();
  const timeFilterBox = await timeFilter.boundingBox();
  const sourceFilterBox = await sourceFilter.boundingBox();
  expect(sortFilterBox).not.toBeNull();
  expect(stateFilterBox).not.toBeNull();
  expect(timeFilterBox).not.toBeNull();
  expect(sourceFilterBox).not.toBeNull();
  expect(sourceFilterBox!.x + sourceFilterBox!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  if (testInfo.project.name === "mobile") {
    expect(Math.abs(sortFilterBox!.y - stateFilterBox!.y)).toBeLessThan(2);
    expect(sortFilterBox!.x + sortFilterBox!.width).toBeLessThanOrEqual(stateFilterBox!.x);
    expect(timeFilterBox!.y).toBeGreaterThan(sortFilterBox!.y);
    expect(Math.abs(timeFilterBox!.y - sourceFilterBox!.y)).toBeLessThan(2);
    expect(timeFilterBox!.x + timeFilterBox!.width).toBeLessThanOrEqual(sourceFilterBox!.x);
    await expect(page.locator(".item-card").first().getByText("收藏", { exact: true })).toBeVisible();
    await expect(page.locator(".item-card").first().getByText("原文", { exact: true })).toBeVisible();
  }
  await stateFilter.selectOption("");
  await sourceFilter.selectOption("arXiv");
  await expect(page).toHaveURL(/source=arXiv/);
  await expect(page.getByRole("heading", { name: "Reliable Tool Use for Language Model Agents" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "开源RAG评测工具发布新版本" })).toBeHidden();
  await sourceFilter.selectOption("");
  const readButton = page.getByRole("button", { name: "标记已读" }).first();
  if (await readButton.isVisible()) await readButton.click();
  await capture(page, testInfo, "feed");
  await page.getByRole("button", { name: "忽略" }).first().click();
  await expect(page.getByRole("status")).toContainText("已忽略，可随时撤销");
  await page.getByRole("button", { name: "撤销忽略" }).click();
  await expect(page.getByRole("status")).toContainText("已取消忽略");

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
  if (testInfo.project.name === "mobile") {
    const bulkToolbarBox = await page.getByRole("group", { name: "批量操作" }).boundingBox();
    expect(bulkToolbarBox).not.toBeNull();
    expect(bulkToolbarBox!.height).toBeLessThanOrEqual(110);
    await expect(page.getByRole("button", { name: "标记所选已读" })).toContainText("已读");
    const selectedCardBox = await page.locator(".item-card.selected").boundingBox();
    expect(selectedCardBox).not.toBeNull();
    expect(selectedCardBox!.height).toBeLessThanOrEqual(250);
  }
  await capture(page, testInfo, "feed-bulk-selection", false);
  await page.getByRole("button", { name: "收藏所选" }).click();
  await expect(page.getByText(/^已处理\d+条/)).toBeVisible();
  await page.getByRole("button", { name: "退出批量" }).click();

  await page.getByRole("link", { name: "报告", exact: true }).click();
  await expect(page.getByRole("heading", { name: "报告" })).toBeVisible();
  if (testInfo.project.name === "mobile") {
    const reportSearchBox = await page.getByRole("searchbox", { name: "搜索报告" }).boundingBox();
    const reportPeriodBox = await page.getByRole("combobox", { name: "报告时间" }).boundingBox();
    expect(reportSearchBox).not.toBeNull();
    expect(reportPeriodBox).not.toBeNull();
    expect(Math.abs(reportSearchBox!.y - reportPeriodBox!.y)).toBeLessThanOrEqual(2);
    expect(reportPeriodBox!.x + reportPeriodBox!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  }
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
  await expect(page.getByRole("heading", { name: "Hermes连接" })).toHaveCount(0);
  if (testInfo.project.name === "mobile") {
    const subscriptionSearchBox = await page.getByRole("searchbox", { name: "搜索订阅" }).boundingBox();
    const subscriptionStatusBox = await page.getByRole("combobox", { name: "订阅状态" }).boundingBox();
    expect(subscriptionSearchBox).not.toBeNull();
    expect(subscriptionStatusBox).not.toBeNull();
    expect(Math.abs(subscriptionSearchBox!.y - subscriptionStatusBox!.y)).toBeLessThanOrEqual(2);
    expect(subscriptionStatusBox!.x + subscriptionStatusBox!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
    const firstSubscriptionBox = await page.locator(".subscription-row").first().boundingBox();
    expect(firstSubscriptionBox).not.toBeNull();
    expect(firstSubscriptionBox!.y).toBeLessThan(page.viewportSize()!.height);
  }
  await capture(page, testInfo, "subscriptions");
  await page.getByRole("link", { name: "Hermes与运行" }).click();
  await expect(page).toHaveURL(/\/settings\?view=runtime$/);
  await expect(page.getByRole("heading", { name: "Hermes连接" })).toBeVisible();
  await expect(page.getByRole("button", { name: "测试连接" })).toBeVisible();
  await capture(page, testInfo, "runtime-settings");
  await page.getByRole("link", { name: "订阅" }).click();
  await expect(page).toHaveURL(/\/settings$/);
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
  await page.locator(".task-row.failed", { hasText: "AI工程岗位" }).click();
  await expect(page.getByRole("link", { name: "检查订阅与Hermes连接" })).toBeVisible();
  await capture(page, testInfo, "task-detail-failed");
  await page.getByRole("button", { name: "重新执行" }).click();
  await expect(page).toHaveURL(/\/tasks\/\d+$/);
  await expect(page.getByText("重试来源")).toBeVisible();
  await expect(page.getByRole("link", { name: /任务#/ })).toBeVisible();
});

test("中等宽度下情报筛选保持完整", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "由桌面项目覆盖中等宽度");
  await page.setViewportSize({ width: 900, height: 800 });
  await page.goto("/feed");

  const sourceFilter = page.getByRole("combobox", { name: "情报来源" });
  await expect(sourceFilter).toBeVisible();
  const box = await sourceFilter.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x + box!.width).toBeLessThanOrEqual(900);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(900);
});

test("识别并筛选可能过期、低优先级和原文失效内容", async ({ page }, testInfo) => {
  await page.route("**/api/items?*", (route) => {
    const state = new URL(route.request().url()).searchParams.get("state");
    const low = state === "low";
    const sourceUnavailable = state === "source-unavailable";
    return route.fulfill({ json: {
      items: [{
        id: sourceUnavailable ? 992 : low ? 991 : 990, subscriptionId: 1, kind: "news", title: sourceUnavailable ? "原始页面已经删除" : low ? "尚待观察的边缘线索" : "三十天前的产品公告",
        summary: sourceUnavailable ? "保留摘要和处理链路，等待替代来源。" : low ? "当前证据有限，保留供后续核验。" : "这条热点已超过30天，需要重新核对现状。", url: sourceUnavailable ? "https://example.com/deleted" : low ? "https://example.com/low" : "https://example.com/old-news",
        source: "Example", publishedAt: "2026-07-01T00:00:00Z", keywords: ["产品公告"],
        reason: low ? "重要性较低" : "可能已有后续变化", importance: low ? 0.2 : 0.6, isRead: false, isSaved: false,
        isIgnored: false, isInvalid: false, isStale: !low && !sourceUnavailable, sourceUnavailable, mergedIntoId: null,
        createdAt: "2026-07-01T00:00:00Z",
      }],
      total: 1, limit: 20, offset: 0,
    } });
  });
  await page.goto("/feed?state=stale");

  await expect(page.getByRole("combobox", { name: "情报状态" })).toHaveValue("stale");
  await expect(page.locator(".stale-tag", { hasText: "可能过期" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "三十天前的产品公告" })).toBeVisible();
  await capture(page, testInfo, "feed-stale");

  await page.getByRole("combobox", { name: "情报状态" }).selectOption("low");
  await expect(page).toHaveURL(/state=low/);
  await expect(page.getByRole("heading", { name: "尚待观察的边缘线索" })).toBeVisible();
  await expect(page.locator(".importance")).toHaveText("低优先级");
  await capture(page, testInfo, "feed-low-priority");

  await page.getByRole("combobox", { name: "情报状态" }).selectOption("source-unavailable");
  await expect(page).toHaveURL(/state=source-unavailable/);
  await expect(page.getByRole("heading", { name: "原始页面已经删除" })).toBeVisible();
  await expect(page.locator(".source-failed-tag")).toHaveText("原文失效");
  await expect(page.getByLabel("原文已标记失效")).toBeVisible();
  await capture(page, testInfo, "feed-source-unavailable");
});

test("所选情报可以创建专题报告任务", async ({ page }, testInfo) => {
  await page.goto("/feed");
  await page.getByRole("button", { name: "批量选择" }).click();
  await page.getByRole("checkbox", { name: /^选择/ }).first().check();
  await page.getByRole("button", { name: "生成报告" }).click();
  await expect(page.getByRole("dialog", { name: /用1条情报生成报告/ })).toBeVisible();
  await page.getByRole("textbox", { name: "整理要求" }).fill("比较关键变化并说明研究影响");
  if (testInfo.project.name === "mobile") {
    await assertNoOverflow(page);
    const dialogBox = await page.getByRole("dialog").boundingBox();
    expect(dialogBox).not.toBeNull();
    expect(dialogBox!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  }
  await capture(page, testInfo, "report-create-dialog", false);
  await page.getByRole("button", { name: "交给Hermes" }).click();

  await expect(page).toHaveURL(/\/tasks\/\d+$/);
  await expect(page.getByRole("heading", { name: "生成专题报告" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "报告要求" })).toBeVisible();
  await expect(page.getByText("比较关键变化并说明研究影响")).toBeVisible();
  await capture(page, testInfo, "report-task-created", false);
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

  const itemDetailPath = new URL(page.url()).pathname;
  await page.getByRole("link", { name: "查看完整链路" }).click();
  await expect(page.getByRole("heading", { name: "完整处理链路" })).toBeVisible();
  await expect(page.getByRole("link", { name: "返回上一列表" })).toHaveAttribute("href", itemDetailPath);
  await expect(page.getByRole("link", { name: "返回内容详情" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "定时订阅输入" })).toBeVisible();
  await expect(page.getByText("demo-hermes-news")).toBeVisible();
  await expect(page.getByRole("heading", { name: "报告生成" })).toBeVisible();
  await capture(page, testInfo, "trace-detail");
});

test("维护情报并保留修改记录", async ({ page }, testInfo) => {
  await page.route("**/api/preferences", async (route) => {
    const payload = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      json: {
        id: 901, ...payload, active: true,
        createdAt: "2026-08-24T00:00:00Z", updatedAt: "2026-08-24T00:00:00Z",
      },
    });
  });
  await page.goto("/reports");
  await page.getByRole("link", { name: /AI热点日报/ }).click();
  await page.getByRole("link", { name: "Hermes Agent增加异步Run接口" }).click();

  await expect(page.getByRole("button", { name: "编辑内容" })).toBeVisible();
  await expect(page.getByText("更多维护")).toBeVisible();
  await expect(page.getByRole("button", { name: "标记无效" })).toBeHidden();
  await capture(page, testInfo, "item-maintenance-collapsed");

  await page.getByRole("button", { name: "编辑内容" }).click();
  await expect(page.getByRole("dialog", { name: "编辑情报" })).toBeVisible();
  await capture(page, testInfo, "item-edit-dialog");
  await page.getByLabel("摘要").fill("经人工核对：外部系统现已支持创建、跟踪和停止长时间Agent任务。");
  await page.getByRole("button", { name: "保存修改" }).click();
  await expect(page.getByText("内容已更新，修改记录已保留")).toBeVisible();
  await expect(page.getByText("编辑内容").last()).toBeVisible();

  await page.getByText("更多维护").click();
  await page.getByRole("button", { name: "少看此来源" }).click();
  await expect(page.getByText(/已记住：以后减少来自/)).toBeVisible();
  await capture(page, testInfo, "item-source-preference");

  await page.getByRole("button", { name: "标记原文失效" }).click();
  await expect(page.locator(".source-failed-tag")).toHaveText("原文失效");
  await expect(page.getByText("原文已标记失效", { exact: true }).last()).toBeVisible();
  await capture(page, testInfo, "item-source-unavailable");
  await page.getByRole("button", { name: "恢复原文" }).click();
  await expect(page.getByText("已恢复原文链接", { exact: true })).toBeVisible();
  await expect(page.locator(".source-failed-tag")).toHaveCount(0);

  await page.getByRole("button", { name: "标记无效" }).click();
  await expect(page.getByText("已标记无效", { exact: true }).last()).toBeVisible();
  await page.getByRole("button", { name: "恢复有效" }).click();
  await expect(page.getByText("已恢复有效", { exact: true }).last()).toBeVisible();

  const revisionToggle = page.getByRole("button", { name: /查看全部\d+条/ });
  await expect(revisionToggle).toBeVisible();
  await expect(page.locator(".revision-row")).toHaveCount(3);
  await capture(page, testInfo, "item-revisions-collapsed");
  await revisionToggle.click();
  expect(await page.locator(".revision-row").count()).toBeGreaterThanOrEqual(5);

  await page.getByRole("button", { name: "合并重复" }).click();
  await expect(page.getByRole("dialog", { name: "合并重复情报" })).toBeVisible();
  await expect(page.getByText("未发现高相似度的重复情报")).toBeVisible();
  await capture(page, testInfo, "item-merge-dialog");
});

test("搜索知流并管理Hermes偏好", async ({ page }, testInfo) => {
  if (testInfo.project.name === "mobile") await page.setViewportSize({ width: 320, height: 740 });
  await page.goto("/");
  await page.getByRole("link", { name: "搜索知流" }).click();
  await page.getByRole("textbox", { name: "搜索情报和报告" }).fill("Agent");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page).toHaveURL(/\/search\?q=Agent/);
  await expect(page.getByText(/条结果$/)).toBeVisible();
  await expect(page.getByRole("link", { name: /Hermes Agent增加异步Run接口/ })).toBeVisible();
  if (testInfo.project.name === "mobile") {
    const searchFormBox = await page.getByRole("search").boundingBox();
    expect(searchFormBox).not.toBeNull();
    expect(searchFormBox!.height).toBeLessThanOrEqual(60);
  }
  await capture(page, testInfo, "global-search");

  await page.goto("/settings?view=runtime");
  await expect(page.getByRole("heading", { name: "Hermes偏好" })).toBeVisible();
  await page.getByRole("button", { name: "新增偏好" }).click();
  await page.getByRole("combobox", { name: "作用对象" }).selectOption("source");
  await page.getByRole("combobox", { name: "处理方式" }).selectOption("avoid");
  await page.getByRole("textbox", { name: "偏好内容" }).fill(`低质量来源-${testInfo.project.name}`);
  await page.getByRole("button", { name: "保存偏好" }).click();
  await expect(page.getByText("偏好已保存，Hermes后续整理会遵循它")).toBeVisible();
  await expect(page.getByText(`低质量来源-${testInfo.project.name}`)).toBeVisible();
  await capture(page, testInfo, "hermes-preferences");
});

test("查看质量记录和订阅健康", async ({ page }, testInfo) => {
  await page.goto("/quality");
  await expect(page.getByRole("heading", { name: "内容质量", level: 1 })).toBeVisible();
  await expect(page.getByText(/质量检查并写入/).first()).toBeVisible();
  const contentStatus = page.getByRole("navigation", { name: "内容状态概览" });
  await expect(contentStatus.getByRole("link", { name: /可能过期/ })).toHaveAttribute("href", "/feed?state=stale");
  await expect(contentStatus.getByRole("link", { name: /低优先级/ })).toHaveAttribute("href", "/feed?state=low");
  await expect(contentStatus.getByRole("link", { name: /原文失效/ })).toHaveAttribute("href", "/feed?state=source-unavailable");
  if (testInfo.project.name === "mobile") {
    await expect(page.getByRole("navigation", { name: "主导航" }).getByRole("link", { name: "质量" })).toHaveAttribute("aria-current", "page");
  }
  await page.getByRole("group", { name: "质量概览" }).getByRole("button", { name: /已恢复/ }).click();
  await expect(page).toHaveURL(/action=restored/);
  await expect(page.getByText("还没有恢复记录")).toBeVisible();
  const emptyStatus = page.getByRole("status", { name: "还没有恢复记录" });
  const emptyStatusBox = await emptyStatus.boundingBox();
  expect(emptyStatusBox).not.toBeNull();
  expect(emptyStatusBox!.height).toBeLessThanOrEqual(64);
  await expect(page.getByRole("button", { name: "查看全部" })).toBeVisible();
  await expect(page.getByRole("group", { name: "质量记录筛选" })).toHaveCount(0);
  if (testInfo.project.name === "mobile") {
    const metricsBox = await page.getByRole("group", { name: "质量概览" }).boundingBox();
    const statusBox = await contentStatus.boundingBox();
    expect(metricsBox).not.toBeNull();
    expect(statusBox).not.toBeNull();
    expect(metricsBox!.height).toBeLessThanOrEqual(90);
    expect(statusBox!.height).toBeLessThanOrEqual(72);
  }
  await capture(page, testInfo, "quality-center");
  await page.goto("/settings?view=runtime");
  await expect(page.getByRole("heading", { name: "订阅健康" })).toBeVisible();
  await expect(page.getByText(/条产出/).first()).toBeVisible();
  await capture(page, testInfo, "subscription-health");
});

test("任务列表限制长错误摘要高度", async ({ page }, testInfo) => {
  const longError = "Hermes返回连接错误：" + "上游服务暂时不可用，正在等待网络恢复。".repeat(20);
  await page.route("**/api/runs?*", (route) => route.fulfill({
    json: {
      items: [{
        id: 901,
        subscriptionId: 1,
        retryOfId: null,
        subscriptionName: "长错误测试",
        topic: "失败任务",
        hermesRunId: null,
        traceId: null,
        origin: "subscription-hermes",
        status: "failed",
        stage: "failed",
        resultSummary: null,
        startedAt: "2026-08-24T08:00:00Z",
        finishedAt: "2026-08-24T08:00:03Z",
        durationMs: 3000,
        errorMessage: longError,
        publicationId: null,
        briefingId: null,
        retryCount: 2,
      }],
      total: 1,
      limit: 20,
      offset: 0,
    },
  }));

  await page.goto("/tasks?status=failed");
  const failedCard = page.locator(".task-row.failed");
  await expect(failedCard).toBeVisible();
  const cardBox = await failedCard.boundingBox();
  expect(cardBox).not.toBeNull();
  expect(cardBox!.height).toBeLessThanOrEqual(160);
  await capture(page, testInfo, "task-long-error", false);
});

test("筛选无结果状态保持紧凑", async ({ page }, testInfo) => {
  await page.route("**/api/items?*", (route) => route.fulfill({
    json: { items: [], total: 0, limit: 20, offset: 0 },
  }));

  await page.goto("/feed?state=saved");
  const emptyStatus = page.getByRole("status", { name: "当前筛选下没有情报" });
  await expect(emptyStatus).toBeVisible();
  await expect(page.getByRole("button", { name: "清除筛选" })).toBeVisible();
  const box = await emptyStatus.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.height).toBeLessThanOrEqual(72);
  await capture(page, testInfo, "feed-empty-filter", false);
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
