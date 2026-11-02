import { test, expect, type Page } from "@playwright/test";

async function mockWorkspace(page: Page, theme = "light", role = "admin") {
  const state = { status: "processing", progress: 42 };
  await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (!["localhost", "127.0.0.1"].includes(url.hostname) || (url.port !== "8000" && !url.pathname.startsWith("/api/"))) return route.continue();
    const path = url.pathname.replace(/^\/api/, "");
    let body: unknown;
    if (path === "/auth/me") body = { user: { id: "demo", email: "demo@example.com", name: "Demo user" }, csrf_token: "ui-test-only" };
    else if (path === "/workspaces") body = [{ id: "demo", name: "Research workspace", role }];
    else if (path.endsWith("/documents")) body = [{ id: "history", name: "historyofanimals.pdf", version: 1, chunk_count: 1006, original_available: true, job_status: state.status, progress: state.progress, error: state.status === "failed" ? "OCR service unavailable. Retry indexing." : null }];
    else if (path.endsWith("/jobs") || path.endsWith("/conversations")) body = [];
    else return route.fulfill({ status: 404, json: { detail: "Unexpected test request" } });
    return route.fulfill({ json: body, headers: { "Access-Control-Allow-Origin": "http://127.0.0.1:3100", "Access-Control-Allow-Credentials": "true" } });
  });
  return state;
}

for (const theme of ["light", "dark"]) {
  test(`document progress, actions and contrast in ${theme} theme`, async ({ page }) => {
    const state = await mockWorkspace(page, theme);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/");
    const card = page.getByRole("listitem", { name: "Document historyofanimals.pdf" });
    const progress = card.getByRole("progressbar");
    await expect(progress).toHaveAttribute("aria-valuenow", "42");
    await expect(card).toContainText("42%");
    await expect(card).toContainText("Version 1");
    await expect(card).toContainText("1,006 passages");
    await expect(card.getByRole("button", { name: "Manage access" })).toBeVisible();
    await expect(card.getByRole("button", { name: "Upload new version" })).toBeVisible();
    await expect(card.getByRole("button", { name: "View PDF" })).toHaveCSS("cursor", "pointer");
    const contrast = await card.evaluate((element) => {
      const rgb = (color: string) => color.match(/[\d.]+/g)!.slice(0, 3).map(Number);
      const luminance = (color: string) => rgb(color).map((v) => { const c = v / 255; return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4; }).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
      const background = luminance(getComputedStyle(element).backgroundColor);
      return [".document-name", ".document-metadata", ".document-action", ".document-view"].map((selector) => {
        const target = element.querySelector(selector)!; const css = getComputedStyle(target);
        const text = luminance(css.color); const bg = css.backgroundColor === "rgba(0, 0, 0, 0)" ? background : luminance(css.backgroundColor);
        return (Math.max(text, bg) + .05) / (Math.min(text, bg) + .05);
      });
    });
    for (const ratio of contrast) expect(ratio).toBeGreaterThanOrEqual(4.5);
    if (process.env.CAPTURE_README === "1") await page.screenshot({ path: `../docs/images/workspace-${theme}.png`, fullPage: true });
    state.status = "ready"; state.progress = 100;
    await page.getByRole("button", { name: "Refresh library" }).click();
    await expect(progress).toHaveAttribute("aria-valuenow", "100");
    await expect(card).toContainText("Indexed");
  });
}

test("queued and failed states retain meaningful progress and the active version", async ({ page }) => {
  const state = await mockWorkspace(page);state.status = "queued";state.progress = 95;
  await page.setViewportSize({ width: 1440, height: 1000 });await page.goto("/");
  const card = page.getByRole("listitem", { name: "Document historyofanimals.pdf" });
  await expect(card.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  await expect(card).toContainText("Queued for indexing");
  state.status = "failed";state.progress = 58;
  await page.getByRole("button", { name: "Refresh library" }).click();
  await expect(card.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "58");
  await expect(card.getByRole("alert")).toContainText("previous version is still searchable");
  await expect(card.getByRole("button", { name: "View PDF" })).toBeEnabled();
});

test("mobile document cards fit and reader actions stay scoped", async ({ page }) => {
  await mockWorkspace(page, "dark", "reader");
  await page.setViewportSize({ width: 390, height: 844 });await page.goto("/");
  await page.getByRole("button", { name: "Documents", exact: true }).click();
  const card = page.getByRole("listitem", { name: "Document historyofanimals.pdf" });
  await expect(card).toBeVisible();
  await expect(card.getByRole("button", { name: "Manage access" })).toHaveCount(0);
  await expect(card.getByRole("button", { name: "Upload new version" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("login validation and password visibility", async ({ page }) => {
  await page.route("**/auth/me", (route) => route.fulfill({ status: 401, json: { detail: "Sign in" } }));
  await page.route("**/auth/options", (route) => route.fulfill({ json: { sso_enabled: false } }));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await page.getByLabel("Password", { exact: true }).fill("not-a-real-password");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Create an account" }).click();
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Full name" })).toBeVisible();
});
