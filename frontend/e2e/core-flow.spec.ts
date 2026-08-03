import { expect, test, type Page, type TestInfo } from "@playwright/test";

async function assertNoOverflow(page: Page) {
  const hasOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasOverflow).toBe(false);
}

async function capture(page: Page, testInfo: TestInfo, name: string) {
  await assertNoOverflow(page);
  await page.screenshot({ path: testInfo.outputPath(`${name}.png`), fullPage: true });
}

test("阅读情报并触发订阅", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "今日情报" })).toBeVisible();
  await capture(page, testInfo, "home");

  await page.getByRole("link", { name: "情报", exact: true }).click();
  const readButton = page.getByRole("button", { name: "标记已读" }).first();
  if (await readButton.isVisible()) await readButton.click();
  await capture(page, testInfo, "feed");

  await page.getByRole("link", { name: "报告", exact: true }).click();
  await expect(page.getByRole("heading", { name: "定期报告" })).toBeVisible();
  await capture(page, testInfo, "reports");

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
  await page.getByRole("button", { name: `立即执行${subscriptionName}` }).click();
  await expect(page.getByText(`${subscriptionName}已加入任务队列`)).toBeVisible();
  await page.getByRole("link", { name: "任务记录" }).click();
  await expect(page.getByText(/已排队|执行中|已完成/).first()).toBeVisible();
  await capture(page, testInfo, "tasks");
});

test("报告来源可以追溯到Hermes处理链路", async ({ page }, testInfo) => {
  await page.goto("/reports");
  await page.getByRole("link", { name: /AI热点日报/ }).click();
  await expect(page.getByRole("heading", { name: "来源情报" })).toBeVisible();
  await expect(page.getByRole("link", { name: "查看生成链路" })).toBeVisible();
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
