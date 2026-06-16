/**
 * Phase 4 manual-smoke driver (Playwright).
 *
 * Seeds a multi-trial dataset, screenshots all 5 views:
 *   1. Network grid (PRD §8.1)
 *   2. Per-site chart (PRD §8.2) with Stack-by toggle
 *   3. Trial detail (PRD §8.3)
 *   4. Metrics (PRD §8.4)
 *   5. Calendar (PRD §8.5)
 */

import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:15174";
const API = process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:18000";

const TS = Date.now();
const ORG_NAME = `P4Org-${TS}`;
const ADMIN_EMAIL = `p4-${TS}@example.com`;
const ADMIN_PASS = "correct-horse-battery-staple";

function futureMonday(weeksAhead: number): string {
  const today = new Date();
  const dow = today.getUTCDay(); // 0=Sun..6=Sat
  const todayMonday = new Date(today);
  const delta = dow === 0 ? -6 : 1 - dow;
  todayMonday.setUTCDate(today.getUTCDate() + delta + weeksAhead * 7);
  return todayMonday.toISOString().slice(0, 10);
}

async function seed(request: APIRequestContext): Promise<{ orgId: string; trialIds: string[]; siteId: string }> {
  const signupRes = await request.post(`${API}/orgs`, {
    data: {
      org_name: ORG_NAME,
      default_timezone: "America/New_York",
      admin_email: ADMIN_EMAIL,
      admin_password: ADMIN_PASS,
      admin_name: "P4 Admin",
    },
  });
  expect(signupRes.status()).toBe(201);
  const org = await signupRes.json();

  await request.post(`${API}/auth/login`, {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASS, org_id: org.id },
  });

  // Two sites.
  const siteA = await (
    await request.post(`${API}/sites`, {
      data: {
        name: "Boston",
        timezone: "America/New_York",
        operating_weekdays: [0, 1, 2, 3, 4],
        hours_per_day: 10,
        rooms: 2,
      },
    })
  ).json();
  const siteB = await (
    await request.post(`${API}/sites`, {
      data: {
        name: "Los Angeles",
        timezone: "America/Los_Angeles",
        operating_weekdays: [0, 1, 2, 3, 4],
        hours_per_day: 10,
        rooms: 3,
      },
    })
  ).json();

  // Two trials.
  const trialIds: string[] = [];
  for (const [name, target] of [["Acme-001", 100], ["Beta-002", 80]] as const) {
    const trial = await (
      await request.post(`${API}/trials`, {
        data: {
          name,
          fpfv: "2025-01-06",
          lpfv: "2028-01-03",
          lplv: "2029-01-01",
          enrollment_target: target,
          screening_target: Math.floor(target * 1.25),
        },
      })
    ).json();
    trialIds.push(trial.id);
    const arm = (await (await request.get(`${API}/trials/${trial.id}/arms`)).json())[0];

    // Add a small SoA: screening, randomization, two follow-ups, priced.
    const soa = [
      { name: "Screen", visit_type: "screening", target_day_offset: -14, sort_order: 0, price: 200 },
      { name: "Rand", visit_type: "randomization", target_day_offset: 0, sort_order: 1, price: 500 },
      { name: "FU W2", visit_type: "follow_up", target_day_offset: 14, window_days: 3, sort_order: 2, price: 300 },
      { name: "FU W6", visit_type: "follow_up", target_day_offset: 42, window_days: 3, sort_order: 3, price: 300 },
    ];
    for (const v of soa) {
      await request.post(`${API}/arms/${arm.id}/visits`, { data: v });
    }

    // Assign both sites.
    for (const site of [siteA, siteB]) {
      const st = await (
        await request.post(`${API}/trials/${trial.id}/sites`, {
          data: {
            site_id: site.id,
            per_site_enrollment_target: Math.floor(target / 2),
            per_site_screening_target: Math.floor(target * 0.625),
          },
        })
      ).json();
      // Seed 4 future weeks of projections so the network grid has signal.
      const weeks = [0, 1, 2, 3].map((w) => ({
        week_start: futureMonday(w + 1),
        proj_screened: 6,
        proj_randomized: 4,
        actual_screened: null,
        actual_randomized: null,
      }));
      await request.put(`${API}/site-trials/${st.id}/enrollment-weeks`, {
        data: { arm_id: arm.id, weeks },
      });
    }

    // Activate the trial.
    await request.post(`${API}/trials/${trial.id}/activate`);
  }

  return { orgId: org.id, trialIds, siteId: siteA.id };
}

async function browserLogin(page: Page, orgId: string) {
  await page.goto(BASE + "/login");
  await page.getByPlaceholder("Org ID (UUID)").fill(orgId);
  await page.getByPlaceholder("Email").fill(ADMIN_EMAIL);
  await page.getByPlaceholder("Password").fill(ADMIN_PASS);
  await page.getByRole("button", { name: /sign in/i }).click();
}

test("phase 4 — all 5 views", async ({ browser, request }) => {
  const { orgId, trialIds, siteId } = await seed(request);

  const context = await browser.newContext();
  const page = await context.newPage();
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));

  await browserLogin(page, orgId);

  // --- 1. Network grid (now the landing page) ----------------------
  await page.waitForURL("**/");
  await expect(page.getByRole("heading", { name: /network forecast/i })).toBeVisible({
    timeout: 10000,
  });
  await expect(page.getByTestId("network-grid")).toBeVisible();
  await expect(page.getByTestId("kpi-strip")).toBeVisible();
  await page.screenshot({
    path: "e2e/screenshots/p4-01-network.png",
    fullPage: true,
  });

  // --- 2. Per-site chart -------------------------------------------
  await page.goto(`${BASE}/sites/${siteId}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({
    timeout: 10000,
  });
  await expect(page.getByTestId("chart-container")).toBeVisible();
  await expect(page.getByTestId("stack-toggle")).toBeVisible();
  await page.screenshot({
    path: "e2e/screenshots/p4-02-site-chart-by-trial.png",
    fullPage: true,
  });
  // Flip the toggle to visit_type.
  await page.getByRole("tab", { name: /visit type/i }).click();
  await page.waitForTimeout(300);
  await page.screenshot({
    path: "e2e/screenshots/p4-03-site-chart-by-type.png",
    fullPage: true,
  });

  // --- 3. Trial detail ---------------------------------------------
  await page.goto(`${BASE}/trials/${trialIds[0]}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({
    path: "e2e/screenshots/p4-04-trial-detail.png",
    fullPage: true,
  });

  // --- 4. Metrics --------------------------------------------------
  await page.goto(`${BASE}/metrics`);
  // Wait for at least one data row to appear — proves the dependent fetch
  // chain (trials → per-trial metrics) settled before screenshot.
  await expect(page.locator("[data-testid^='metrics-row-']").first()).toBeVisible({
    timeout: 15000,
  });
  await page.screenshot({
    path: "e2e/screenshots/p4-05-metrics.png",
    fullPage: true,
  });

  // --- 5. Calendar -------------------------------------------------
  await page.goto(`${BASE}/sites/${siteId}/calendar`);
  await expect(page.getByTestId("calendar-grid")).toBeVisible({ timeout: 10000 });
  // Wait for the first day button to render — proves the daily data fetched.
  await expect(page.locator("[data-testid^='day-']").first()).toBeVisible({
    timeout: 10000,
  });
  await page.screenshot({
    path: "e2e/screenshots/p4-06-calendar.png",
    fullPage: true,
  });

  await context.close();
});
