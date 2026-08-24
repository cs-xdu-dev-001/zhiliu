import { expect, test, type Page } from "@playwright/test";

async function expectNoHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
}

test("超长、空摘要和未标注来源保持可读", async ({ page }) => {
  await page.route(/\/api\/items\?/, async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    if (payload.items?.[0]) {
      payload.items[0].title = "这是一个用于验证窄屏布局不会被超长标题破坏的情报标题".repeat(4);
      payload.items[0].summary = "";
      payload.items[0].reason = "";
      payload.items[0].source = "";
    }
    if (payload.items?.[1]) payload.items[1].summary = "超长摘要内容".repeat(100);
    await route.fulfill({ response, json: payload });
  });

  await page.goto("/feed?state=all");
  await expect(page.getByText("来源未标注").first()).toBeVisible();
  await expect(page.getByText("暂无摘要").first()).toBeVisible();
  await expectNoHorizontalOverflow(page);
  const firstCard = page.locator(".item-card").first();
  expect((await firstCard.boundingBox())!.height).toBeLessThan(420);
});

test("大量报告来源不会破坏详情布局", async ({ page }) => {
  await page.route("**/api/briefings/1", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    const source = payload.sourceItems?.[0];
    if (source) {
      payload.sourceItems = Array.from({ length: 12 }, (_, index) => ({
        ...source,
        id: source.id + index + 1000,
        title: `${index + 1}号来源：${"很长的来源标题".repeat(8)}`,
        summary: index === 0 ? "" : source.summary,
        source: index === 0 ? "" : source.source,
        ordinal: index,
      }));
    }
    await route.fulfill({ response, json: payload });
  });

  await page.goto("/reports/1");
  await expect(page.getByText("12条")).toBeVisible();
  await expect(page.getByText("来源未标注")).toBeVisible();
  await expect(page.getByText("暂无摘要")).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test("报告创建超时后沿用同一请求标识重试", async ({ page }) => {
  const requestIds: string[] = [];
  let attempts = 0;
  await page.route("**/api/briefings/generate", async (route) => {
    attempts += 1;
    requestIds.push(route.request().postDataJSON().requestId);
    if (attempts === 1) {
      await route.fulfill({ status: 504, json: { detail: "Hermes响应超时" } });
      return;
    }
    await route.fulfill({ status: 202, json: { id: 9999 } });
  });

  await page.goto("/feed?state=all");
  await page.getByRole("button", { name: "批量选择" }).click();
  await page.locator(".item-select-control input").first().check();
  const trigger = page.getByRole("button", { name: "生成报告" });
  await trigger.click();
  await expect(page.getByRole("textbox", { name: "整理要求" })).toBeFocused();
  await page.getByRole("button", { name: "交给Hermes" }).click();
  await expect(page.getByText(/Hermes响应超时.*所选内容已保留/)).toBeVisible();
  await page.getByRole("button", { name: "重试创建" }).click();
  await expect(page).toHaveURL(/\/tasks\/9999$/);
  expect(requestIds).toHaveLength(2);
  expect(requestIds[1]).toBe(requestIds[0]);
});
