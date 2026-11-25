import { test, expect, type Page } from "@playwright/test";

async function signIn(page: Page, role: "landlord" | "tenant" | "admin") {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(`${role}@example.com`);
  await page.getByLabel("Password", { exact: true }).fill("LocalBrowserTest123!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/${role}$`));
}

test("review the signed-in experience across all three roles", async ({ page }, info) => {
  test.setTimeout(120_000);
  for (const role of ["landlord", "tenant", "admin"] as const) {
    await signIn(page, role);
    await expect(page.locator("h1")).toBeVisible();
    await expect(page.getByRole("main")).toHaveCount(1);
    await expect(page.getByRole("button", { name: "Sign out", exact: true })).toHaveCount(1);
    await page.screenshot({ path: info.outputPath(`${role}-dashboard.png`), fullPage: true });
    for (const view of role === "tenant" ? ["leads", "reports"] : ["leads", "verification", "reports"]) {
      await page.goto(`/${role}/${view}`);
      await expect(page.locator("h1")).toBeVisible();
      await expect(page.getByText(/^Loading /)).toHaveCount(0);
      await expect(page.getByRole("navigation", { name: `${role} navigation`, exact: true })).toBeVisible();
      await expect(page.getByRole("main")).toHaveCount(1);
      await expect(page.locator("h1")).toHaveCount(1);
      await expect(page.getByRole("button", { name: "Sign out", exact: true })).toHaveCount(1);
      if (view === "reports" && role !== "admin") {
        await expect(page.getByText(`Room Rentals · ${role === "landlord" ? "Landlord" : "Tenant"} reports`, { exact: true })).toBeVisible();
      }
      await page.screenshot({ path: info.outputPath(`${role}-${view}.png`), fullPage: true });
    }
  }
});

test("landlord navigation preserves the selected section and the right conversation", async ({ page }) => {
  await signIn(page, "landlord");
  await page.getByRole("button", { name: "Listings", exact: true }).click();
  await expect(page).toHaveURL(/\/landlord\?view=listings$/);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Your listings", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Lead management", exact: true }).click();
  const enquiry = page.locator('[data-lead-id="1"]');
  await expect(enquiry.getByRole("heading", { name: "Garden room", exact: true })).toBeVisible();
  await expect(enquiry.getByText(/Tenant Example/)).toBeVisible();
  await enquiry.getByRole("link", { name: "Open messages" }).click();
  await expect(page).toHaveURL(/\/conversations\?request=1$/);
  await expect(page.locator('.conversation-list-item[aria-current="true"]')).toContainText("Enquiry request #1");
  await page.getByRole("button", { name: /Enquiry request #4/ }).click();
  await expect(page).toHaveURL(/\/conversations\?request=4$/);
  await page.reload();
  await expect(page.locator('.conversation-list-item[aria-current="true"]')).toContainText("Enquiry request #4");
  await page.goto("/conversations?request=999999");
  await expect(page.getByText(/This enquiry's conversation is unavailable/)).toBeVisible();
  await expect(page.locator('.conversation-list-item[aria-current="true"]')).toHaveCount(0);
});

test("wrong-role pages preserve the signed-in workspace instead of showing login", async ({ page }) => {
  await signIn(page, "landlord");
  for (const path of ["/admin", "/admin/reports", "/tenant", "/tenant/leads"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "landlord navigation", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in", exact: true })).toHaveCount(0);
  }
});

test("landlord and tenant see the same room name and accepted enquiry response", async ({ page }) => {
  await signIn(page, "landlord");
  await page.goto("/landlord?view=enquiries");
  const enquiry = page.locator(".landlord-contact-request").filter({ has: page.getByRole("heading", { name: "Garden room", exact: true }) });
  await enquiry.getByRole("button", { name: "Accept enquiry", exact: true }).click();
  await expect(enquiry.locator(".listing-status")).toHaveText("Accepted");
  await signIn(page, "tenant");
  const request = page.locator(".tenant-request-item").filter({ has: page.getByRole("link", { name: "Garden room", exact: true }) });
  await expect(request.getByText("Accepted", { exact: true })).toBeVisible();
  await request.getByRole("link", { name: "Open messages", exact: true }).click();
  await expect(page.locator('.conversation-list-item[aria-current="true"]')).toContainText("Enquiry request #1");
});
