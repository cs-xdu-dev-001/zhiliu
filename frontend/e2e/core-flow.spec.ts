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

  await page.getByRole("link", { name: "情报" }).first().click();
  await expect(page.getByText(/条情报/)).toBeVisible();
  const readButton = page.getByRole("button", { name: "标记已读" }).first();
  if (await readButton.isVisible()) await readButton.click();
  await capture(page, testInfo, "feed");

  await page.getByRole("link", { name: "报告" }).first().click();
  await expect(page.getByRole("heading", { name: "定期报告" })).toBeVisible();
  await capture(page, testInfo, "reports");

  await page.getByRole("link", { name: "设置" }).first().click();
  await expect(page.getByRole("button", { name: "新建订阅" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hermes连接" })).toBeVisible();
  await expect(page.getByRole("button", { name: "测试连接" })).toBeVisible();
  await capture(page, testInfo, "subscriptions");
  await page.getByRole("button", { name: "立即执行" }).first().click();
  await page.getByRole("link", { name: "任务记录" }).click();
  await expect(page.getByText(/已排队|执行中|已完成/).first()).toBeVisible();
  await capture(page, testInfo, "tasks");
});
