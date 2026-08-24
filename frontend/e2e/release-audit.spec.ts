import { expect, test, type Page } from "@playwright/test";

const routes = [
  "/",
  "/feed",
  "/reports",
  "/quality",
  "/settings",
  "/settings?view=runtime",
  "/tasks",
  "/search?q=Agent",
  "/items/1",
  "/reports/1",
  "/tasks/1",
  "/traces/1",
];

async function auditPage(page: Page, route: string) {
  await page.goto(route);
  await expect(page.locator("#main-content")).toBeVisible();
  await expect(page.locator(".topbar h1")).toHaveCount(1);

  const result = await page.evaluate(() => {
    const visible = (element: Element) => {
      const style = getComputedStyle(element);
      const box = element.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && box.width > 0 && box.height > 0;
    };
    const controls = Array.from(document.querySelectorAll<HTMLElement>("button, input:not([type='hidden']), select, textarea, summary"))
      .filter(visible)
      .filter((element) => !(element instanceof HTMLInputElement && (element.type === "checkbox" || element.type === "radio")));
    const unnamed = controls.filter((element) => {
      const labelledBy = element.getAttribute("aria-labelledby");
      const labelledText = labelledBy?.split(/\s+/).map((id) => document.getElementById(id)?.textContent ?? "").join(" ") ?? "";
      return !(element.getAttribute("aria-label") || labelledText.trim() || element.textContent?.trim() || element.getAttribute("title"));
    }).map((element) => element.outerHTML.slice(0, 160));
    const undersized = controls.filter((element) => {
      const box = element.getBoundingClientRect();
      return box.height < 43.5;
    }).map((element) => `${element.tagName.toLowerCase()}[${element.getAttribute("aria-label") ?? element.textContent?.trim() ?? ""}]=${element.getBoundingClientRect().height.toFixed(1)}px`);
    const ids = Array.from(document.querySelectorAll<HTMLElement>("[id]")).map((element) => element.id);
    const duplicateIds = ids.filter((id, index) => ids.indexOf(id) !== index);
    return {
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      unnamed,
      undersized,
      duplicateIds: [...new Set(duplicateIds)],
    };
  });

  expect(result.overflow, `${route}存在横向溢出`).toBeLessThanOrEqual(1);
  expect(result.unnamed, `${route}存在无名称控件`).toEqual([]);
  expect(result.undersized, `${route}存在不足44px的控件`).toEqual([]);
  expect(result.duplicateIds, `${route}存在重复id`).toEqual([]);
}

test("主要页面满足发布候选结构和触控基线", async ({ page }) => {
  for (const route of routes) await auditPage(page, route);
});

test("减少动态效果时加载骨架保持静态", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/items/1", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.continue();
  });
  await page.goto("/items/1");
  const skeleton = page.locator(".detail-skeleton");
  await expect(skeleton).toBeVisible();
  await expect(skeleton).toHaveCSS("animation-name", "none");
});
