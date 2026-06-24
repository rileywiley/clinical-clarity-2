/**
 * Phase 5 manual-smoke driver (Playwright + REAL Claude API).
 *
 * Seeds an org and a site, then drives the trial setup wizard end-to-end:
 *   1. Sign in
 *   2. Open /trials/new
 *   3. Fill Basics → save
 *   4. Upload a real protocol PDF → poll until succeeded
 *   5. Screenshot the review table (real confidence bands)
 *   6. Touch any red rows + Confirm
 *   7. Assign the site in Sites step
 *   8. Skip pricing (no edits needed for smoke)
 *   9. Pick Standard attrition
 *  10. Activate the trial → screenshot success
 *
 * Requires:
 *   - ANTHROPIC_API_KEY set in the worker process (loaded from .env)
 *   - PROTOCOL_PDF_PATH env var pointing at a real PDF
 */

import * as fs from "node:fs";
import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:15174";
const API = process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:18000";
const PDF_PATH = process.env.PROTOCOL_PDF_PATH ?? "/Users/rickydelemos/Desktop/protocol.pdf";

const TS = Date.now();
const ORG_NAME = `P5Smoke-${TS}`;
const ADMIN_EMAIL = `p5-${TS}@example.com`;
const ADMIN_PASS = "correct-horse-battery-staple";

async function seed(request: APIRequestContext): Promise<{ orgId: string; siteId: string }> {
  const signupRes = await request.post(`${API}/orgs`, {
    data: {
      org_name: ORG_NAME,
      default_timezone: "America/New_York",
      admin_email: ADMIN_EMAIL,
      admin_password: ADMIN_PASS,
      admin_name: "P5 Smoke",
    },
  });
  expect(signupRes.status()).toBe(201);
  const org = await signupRes.json();

  await request.post(`${API}/auth/login`, {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASS, org_id: org.id },
  });

  const site = await (
    await request.post(`${API}/sites`, {
      data: {
        name: "Smoke Site",
        timezone: "America/New_York",
        operating_weekdays: [0, 1, 2, 3, 4],
        hours_per_day: 10,
        rooms: 2,
      },
    })
  ).json();

  return { orgId: org.id, siteId: site.id };
}

async function browserLogin(page: Page, orgId: string) {
  await page.goto(BASE + "/login");
  await page.getByPlaceholder("Org ID (UUID)").fill(orgId);
  await page.getByPlaceholder("Email").fill(ADMIN_EMAIL);
  await page.getByPlaceholder("Password").fill(ADMIN_PASS);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(BASE + "/");
}

// Real Claude call on a multi-MB PDF can run well past the default 60s timeout.
test.setTimeout(360_000);

test("phase 5 — wizard + real Claude SoA parse", async ({ browser, request }) => {
  expect(fs.existsSync(PDF_PATH), `PDF must exist at ${PDF_PATH}`).toBe(true);

  const { orgId, siteId } = await seed(request);
  // Pre-confirm the site row exists.
  expect(siteId).toBeTruthy();

  const context = await browser.newContext();
  const page = await context.newPage();
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));

  await browserLogin(page, orgId);
  await expect(page.getByRole("heading", { name: /network forecast/i })).toBeVisible({
    timeout: 10000,
  });

  // --- 1. Open the wizard -------------------------------------------
  await page.getByTestId("new-trial-link").click();
  await page.waitForURL(/\/trials\/new/);
  await expect(page.getByRole("heading", { name: /set up a trial/i })).toBeVisible();
  await page.screenshot({
    path: "e2e/screenshots/p5-01-wizard-empty.png",
    fullPage: true,
  });

  // --- 2. Fill Basics + save ----------------------------------------
  await page.getByTestId("basics-name").fill("P5 Smoke Trial");
  await page.getByTestId("basics-fpfv").fill("2026-08-01");
  await page.getByTestId("basics-lpfv").fill("2027-08-01");
  await page.getByTestId("basics-lplv").fill("2028-08-01");
  await page.getByTestId("basics-save").click();

  // Wizard navigates to ?step=soa after save.
  await page.waitForURL(/step=soa/, { timeout: 10000 });
  await expect(page.getByRole("heading", { name: /schedule of activities/i })).toBeVisible();
  await page.screenshot({
    path: "e2e/screenshots/p5-02-soa-step.png",
    fullPage: true,
  });

  // --- 3. Upload the protocol PDF ----------------------------------
  await page.getByTestId("soa-file-input").setInputFiles(PDF_PATH);
  // The job row appears as soon as the upload returns.
  await expect(page.getByTestId("soa-job-status")).toBeVisible({ timeout: 30000 });
  await page.screenshot({
    path: "e2e/screenshots/p5-03-job-queued.png",
    fullPage: true,
  });

  // --- 4. Poll until succeeded (real Claude call — give it 3 minutes) ---
  // The frontend polls every 2s; we just wait for the review table to render.
  await expect(page.getByTestId("soa-review-table")).toBeVisible({
    timeout: 180_000,
  });
  await page.screenshot({
    path: "e2e/screenshots/p5-04-review-table.png",
    fullPage: true,
  });

  // --- 5. Touch any red rows so Confirm enables -------------------
  const redRows = page.locator('[data-original-band="red"]');
  const redCount = await redRows.count();
  for (let i = 0; i < redCount; i++) {
    // Touch by typing one space then deleting it in the name field (counts as a touch).
    const row = redRows.nth(i);
    const name = row.locator('[data-testid$="-name"]');
    const current = await name.inputValue();
    await name.fill(current + " ");
    await name.fill(current);
  }
  await expect(page.getByTestId("soa-confirm-button")).toBeEnabled();
  await page.screenshot({
    path: "e2e/screenshots/p5-05-after-touching-red.png",
    fullPage: true,
  });

  // --- 6. Confirm — writes Visit rows ------------------------------
  await page.getByTestId("soa-confirm-button").click();
  // Wizard moves to ?step=sites after apply.
  await page.waitForURL(/step=sites/, { timeout: 30000 });
  await page.screenshot({
    path: "e2e/screenshots/p5-06-sites-step.png",
    fullPage: true,
  });

  // --- 7. Assign the seeded site -----------------------------------
  await page.getByTestId("sites-picker").selectOption(siteId);
  await page.getByTestId("sites-assign").click();
  // Wait for the row to appear in the assigned table.
  await expect(page.getByText("Smoke Site")).toBeVisible({ timeout: 10000 });
  await page.getByTestId("sites-continue").click();
  await page.waitForURL(/step=pricing/);

  // --- 8. Pricing — skip without edits -----------------------------
  await page.getByTestId("pricing-continue").click();
  await page.waitForURL(/step=attrition/);
  await page.screenshot({
    path: "e2e/screenshots/p5-07-attrition-step.png",
    fullPage: true,
  });

  // --- 9. Attrition — pick the first preset (Standard is default) -
  // The radio is already pre-selected (from trial defaults); click Continue.
  await page.getByTestId("attrition-continue").click();
  await page.waitForURL(/step=activate/);

  // --- 10. Activate ------------------------------------------------
  await page.getByTestId("activate-button").click();
  await expect(page.getByTestId("activate-success")).toBeVisible({ timeout: 15000 });
  await page.screenshot({
    path: "e2e/screenshots/p5-08-activated.png",
    fullPage: true,
  });

  await context.close();
});
