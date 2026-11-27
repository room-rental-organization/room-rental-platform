import { test, expect } from "@playwright/test";

test("new users verify email before login, then recover a forgotten password", async ({ page, request }) => {
  const suffix = String(Date.now());
  const email = `verified-browser-${suffix}@example.com`;
  const oldPassword = "LocalOldPassword123!";
  const newPassword = "LocalNewPassword123!";
  await page.goto("/register");
  await page.getByLabel("Full name", { exact: true }).fill("Verified Browser Tenant");
  await page.getByLabel("Phone number", { exact: true }).fill(`+2782${suffix.slice(-7)}`);
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(oldPassword);
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page).toHaveURL(/\/verify-email$/);
  const blocked = await request.post("http://127.0.0.1:8017/api/v1/auth/login", { data: { email, password: oldPassword } });
  expect(blocked.status()).toBe(403);
  await page.getByRole("link", { name: "Back to sign in" }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(oldPassword);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/verify-email$/);

  async function emailLink(fragment: string) {
    let link = "";
    await expect.poll(async () => {
      const messages = await (await request.get("http://127.0.0.1:8026/messages")).json();
      const message = messages.findLast((item: { to: string; body: string }) => item.to === email && item.body.includes(fragment));
      link = message?.body.match(/http[^\s]+/)?.[0] ?? "";
      return link;
    }).not.toBe("");
    return link;
  }
  const verificationLink = await emailLink("/verify-email#");
  await page.goto(verificationLink);
  await expect(page).toHaveURL(/\/verify-email$/); // Token removed from history.
  await page.getByRole("button", { name: "Verify email", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Your email is verified");
  await page.getByRole("link", { name: "Back to sign in" }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(oldPassword);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/tenant$/);
  const oldToken = await page.evaluate(() => sessionStorage.getItem("room-rental-access-token"));
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.goto("/login");
  await page.getByRole("link", { name: "Forgot password?", exact: true }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Send reset link", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("If an account matches");
  const resetLink = await emailLink("/reset-password#");
  await page.goto(resetLink);
  await page.getByLabel("New password", { exact: true }).fill(newPassword);
  await page.getByLabel("Confirm new password", { exact: true }).fill(newPassword);
  await page.getByRole("button", { name: "Reset password", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  const revoked = await request.get("http://127.0.0.1:8017/api/v1/users/me", { headers: { Authorization: `Bearer ${oldToken}` } });
  expect(revoked.status()).toBe(401);
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(newPassword);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/tenant$/);
  await page.goto(resetLink);
  await page.getByLabel("New password", { exact: true }).fill("AnotherPassword123!");
  await page.getByLabel("Confirm new password", { exact: true }).fill("AnotherPassword123!");
  await page.getByRole("button", { name: "Reset password", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("invalid or expired");
});
