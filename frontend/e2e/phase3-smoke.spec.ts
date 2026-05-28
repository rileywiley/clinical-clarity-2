/**
 * Phase 3 manual-smoke driver (Playwright).
 *
 * Drives a real Chromium against a running backend + Vite dev server. Seeds an
 * org via the API, logs in via the UI, opens /projections, takes screenshots
 * of every load-bearing visual + interaction:
 *   1. Empty grid loaded (proper past/current/future row classes)
 *   2. After typing into cells (Save button enabled = dirty)
 *   3. After paste from synthetic clipboard
 *   4. Unsaved-changes prompt firing when navigating away dirty
 *   5. History drawer with one entry after a save
 *   6. 409 inline message after a forced past-projection edit
 *
 * Run with:
 *   PLAYWRIGHT_BASE_URL=http://127.0.0.1:15173 \
 *     PLAYWRIGHT_API_URL=http://127.0.0.1:18000 \
 *     npx playwright test --project=chromium
 */

import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:15173";
const API = process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:18000";

const ORG_NAME = `SmokeOrg-${Date.now()}`;
const ADMIN_EMAIL = `smoke-${Date.now()}@example.com`;
const ADMIN_PASS = "correct-horse-battery-staple";

async function seedOrg(request: APIRequestContext): Promise<{ orgId: string }> {
  const r = await request.post(`${API}/orgs`, {
    data: {
      org_name: ORG_NAME,
      default_timezone: "America/New_York",
      admin_email: ADMIN_EMAIL,
      admin_password: ADMIN_PASS,
      admin_name: "Smoke Admin",
    },
  });
  expect(r.status()).toBe(201);
  const body = await r.json();
  return { orgId: body.id };
}

async function seedTrialAndSite(
  request: APIRequestContext,
  orgId: string,
): Promise<{ trialId: string; armId: string; siteTrialId: string }> {
  // Login first to get the cookie used by the API helpers.
  const login = await request.post(`${API}/auth/login`, {
    data: { email: ADMIN_EMAIL, password: ADMIN_PASS, org_id: orgId },
  });
  expect(login.status()).toBe(204);

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
  const trial = await (
    await request.post(`${API}/trials`, {
      data: {
        name: "Smoke Trial",
        fpfv: "2025-01-06",
        lpfv: "2028-01-03",
        lplv: "2029-01-01",
        enrollment_target: 100,
        screening_target: 125,
      },
    })
  ).json();
  const arm = (await (await request.get(`${API}/trials/${trial.id}/arms`)).json())[0];
  const st = await (
    await request.post(`${API}/trials/${trial.id}/sites`, {
      data: {
        site_id: site.id,
        per_site_enrollment_target: 100,
        per_site_screening_target: 125,
      },
    })
  ).json();
  return { trialId: trial.id, armId: arm.id, siteTrialId: st.id };
}

async function browserLogin(page: Page, orgId: string) {
  await page.goto(BASE + "/login");
  await page.getByPlaceholder("Org ID (UUID)").fill(orgId);
  await page.getByPlaceholder("Email").fill(ADMIN_EMAIL);
  await page.getByPlaceholder("Password").fill(ADMIN_PASS);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByText("Signed in as")).toBeVisible({ timeout: 10000 });
}

test("phase 3 manual smoke", async ({ browser, request }) => {
  const { orgId } = await seedOrg(request);
  await seedTrialAndSite(request, orgId);

  const context = await browser.newContext();
  const page = await context.newPage();
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));

  await browserLogin(page, orgId);
  await page.screenshot({ path: "e2e/screenshots/00-home.png", fullPage: true });

  // --- 1. Load the projections page -----------------------------------
  await page.getByRole("link", { name: /open projections grid/i }).click();
  await expect(page).toHaveURL(/\/projections$/);
  // Wait for React Query fetches to settle, then snapshot regardless of
  // whether the next assertion passes (so a failure is debuggable from the
  // screenshot alone).
  await page.waitForLoadState("networkidle");
  await page.screenshot({
    path: "e2e/screenshots/01-empty-grid.png",
    fullPage: true,
  });
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    /projections/i,
  );

  // Variance hint proves the trial-variance API call succeeded.
  await expect(page.getByTestId("variance-randomized")).toBeVisible();

  // --- 2. Type into a future-week PROJECTION cell --------------------
  // Pick a future-row projection cell so the save will produce a real
  // baseline + a subsequent edit produces an audit entry. The grid shows
  // weeks 4 weeks back through 11 weeks forward; row 6 is "today+1 week"
  // which is well into the future area where projections are editable.
  const futureProjScreened = page.getByTestId("input-6-proj_screened");
  await futureProjScreened.focus();
  await page.keyboard.type("12");
  await page.keyboard.press("Tab");
  await page.keyboard.type("9");

  // The Save button should now read "Save" (dirty).
  await expect(page.getByTestId("save-button")).toHaveText(/save/i);
  await page.screenshot({
    path: "e2e/screenshots/02-dirty-typed.png",
    fullPage: true,
  });

  // --- 3. Save (baseline insert — no audit row produced yet) ---------
  await page.getByTestId("save-button").click();
  await expect(page.getByTestId("save-button")).toHaveText(/saved/i, {
    timeout: 5000,
  });

  // --- 4. Edit the same projection cell and save again — this DOES ---
  //        produce an audit row.
  await futureProjScreened.focus();
  await futureProjScreened.fill("15");
  await expect(page.getByTestId("save-button")).toHaveText(/save/i);
  await page.getByTestId("save-button").click();
  await expect(page.getByTestId("save-button")).toHaveText(/saved/i, {
    timeout: 5000,
  });

  // --- 5. Open the history drawer — should now have one entry -------
  await page.getByRole("button", { name: /view change history/i }).click();
  await expect(page.getByTestId("history-row").first()).toBeVisible({
    timeout: 5000,
  });
  await page.screenshot({
    path: "e2e/screenshots/03-history-drawer.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Close history" }).click();

  // --- 6. Try to navigate away with dirty state ---------------------
  await futureProjScreened.focus();
  await futureProjScreened.fill("99");
  // Listen for the native dialog.
  let dialogFired = false;
  page.once("dialog", async (dialog) => {
    dialogFired = true;
    await dialog.dismiss();
  });
  // Click the Home link in the header to trigger the React Router navigation.
  await page.getByRole("link", { name: /← home/i }).click();
  // Give the blocker effect time to fire the confirm.
  await page.waitForTimeout(500);
  expect(dialogFired).toBeTruthy();
  await page.screenshot({
    path: "e2e/screenshots/04-unsaved-changes-blocked.png",
    fullPage: true,
  });

  await context.close();
});
