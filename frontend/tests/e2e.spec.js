const { test, expect } = require("@playwright/test");
const path = require("path");
const fs = require("fs");

const FIXTURE_PDF = path.join(__dirname, "fixtures", "sample_2page.pdf");

test.describe("PDFText Pro E2E", () => {
  test("full user workflow: register, upload, view pages, download, delete, logout, mobile", async ({ page }) => {
    const consoleErrors = [];
    const failedResponses = [];

    page.on("pageerror", (err) => consoleErrors.push(err.message));
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("response", (res) => {
      if (res.status() >= 500) {
        failedResponses.push(`${res.status()} ${res.url()}`);
      }
    });

    // 1. Desktop viewport & Landing page
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page.locator(".brand")).toHaveText("PDFText Pro");

    // 2. Register new user
    const email = `pw_${Date.now()}@example.com`;
    await page.getByRole("button", { name: "Create Account" }).click();
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("Password123!");
    await page.locator("form").getByRole("button", { name: "Create Account" }).click();

    await expect(page.getByText(email)).toBeVisible({ timeout: 10000 });

    // 3. Session persistence across reload
    await page.reload();
    await expect(page.getByText(email)).toBeVisible();

    // 4. Upload real 2-page PDF
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(FIXTURE_PDF);

    // Wait for document to appear and complete processing
    await expect(page.locator(".doc-item").first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator(".badge.completed").first()).toBeVisible({ timeout: 30000 });
    await expect(page.locator(".doc-item").first()).toContainText("2/2 pages (100%)");

    // 5. View extracted text & navigate pages
    await expect(page.locator(".viewer-text")).toContainText("Playwright QA Page 1");
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.locator(".viewer-text")).toContainText("Playwright QA Page 2");
    await page.getByRole("button", { name: "Previous" }).click();
    await expect(page.locator(".viewer-text")).toContainText("Playwright QA Page 1");

    // 6. Download TXT
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Download .TXT" }).click(),
    ]);
    const dlPath = await download.path();
    const dlContent = fs.readFileSync(dlPath, "utf-8");
    expect(dlContent).toContain("--- Page 1 ---");
    expect(dlContent).toContain("--- Page 2 ---");

    // 7. Mobile viewport layout check (no horizontal overflow)
    await page.setViewportSize({ width: 390, height: 844 });
    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth
    );
    expect(hasOverflow).toBe(false);

    // 8. Delete document
    await page.locator(".doc-item").first().getByRole("button", { name: "Delete" }).click();
    await expect(page.getByText("No documents uploaded yet.")).toBeVisible({ timeout: 10000 });

    // 9. Logout & protected UI
    await page.getByRole("button", { name: "Logout" }).click();
    await expect(page.locator("form").getByRole("button", { name: "Sign In" })).toBeVisible();

    expect(consoleErrors).toEqual([]);
    expect(failedResponses).toEqual([]);
  });
});
