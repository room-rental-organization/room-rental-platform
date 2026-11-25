import { test, expect, type Page } from "@playwright/test";

async function signIn(page: Page, role: "tenant" | "landlord" | "admin") {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(`${role}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("LocalBrowserTest123!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/${role}$`));
}

test("landlord sees live business metrics and saves room availability", async ({
  page,
}, info) => {
  await signIn(page, "landlord");
  await expect(
    page.getByRole("heading", { name: "Rental performance", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Available rooms", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Enquiries over the last six months" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Rental conversions" }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("landlord-performance.png"),
    fullPage: true,
  });
  await page
    .locator(".landlord-sidebar-nav")
    .getByRole("button", { name: /Listings/ })
    .click();
  const room = page
    .locator("li")
    .filter({
      has: page.getByRole("heading", { name: "Garden room", exact: true }),
    });
  await room.getByLabel("Room availability").selectOption("reserved");
  await room.getByRole("button", { name: "Save availability" }).click();
  await expect(room.getByLabel("Room availability")).toHaveValue("reserved");
  await page.reload();
  await page
    .locator(".landlord-sidebar-nav")
    .getByRole("button", { name: /Listings/ })
    .click();
  await expect(room.getByLabel("Room availability")).toHaveValue("reserved");
  await room.getByLabel("Room availability").selectOption("available");
  await room.getByRole("button", { name: "Save availability" }).click();
  await expect(
    room.getByRole("button", { name: "Save availability" }),
  ).toBeDisabled();
});

test("landlord progresses an enquiry through viewing to a rental", async ({
  page,
}) => {
  await signIn(page, "landlord");
  await page
    .getByRole("link", { name: "Lead management", exact: true })
    .click();
  const lead = page
    .locator(".rental-records > li")
    .filter({
      has: page.getByRole("heading", { name: "Garden room", exact: true }),
    });
  for (const [stage, label] of [
    ["CONTACTED", "Contacted"],
    ["VIEWING_SCHEDULED", "Viewing scheduled"],
    ["VIEWING_COMPLETED", "Viewing completed"],
    ["INTERESTED", "Interested"],
    ["RENTED", "Rented"],
  ]) {
    await lead.getByRole("button", { name: "Edit progress", exact: true }).click();
    await lead.getByLabel("Next stage").selectOption(stage);
    await lead
      .getByLabel("Internal note (optional)")
      .fill("Synthetic browser test progress note.");
    await lead
      .getByRole("button", {
        name: stage === "RENTED" ? "Record rental" : "Update progress",
        exact: true,
      })
      .click();
    await expect(lead.locator(".rental-status")).toHaveText(label);
  }
  await expect(lead.getByLabel("Next stage")).toHaveCount(0);
  await lead.getByRole("button", { name: "View progress history" }).click();
  await expect(lead.locator(".rental-history li")).toHaveCount(6);
});

test("unsuccessful outcomes require a reason", async ({ page }) => {
  await signIn(page, "landlord");
  await page.goto("/landlord/leads");
  const lead = page
    .locator(".rental-records > li")
    .filter({
      has: page.getByRole("heading", { name: "Sunny room", exact: true }),
    });
  await lead.getByRole("button", { name: "Edit progress", exact: true }).click();
  await lead.getByLabel("Next stage").selectOption("UNSUCCESSFUL");
  await expect(
    lead.getByRole("button", { name: "Record unsuccessful outcome" }),
  ).toBeDisabled();
  await lead
    .getByLabel("Reason (required)")
    .fill("Tenant selected another room.");
  await lead
    .getByRole("button", { name: "Record unsuccessful outcome" })
    .click();
  await expect(lead.locator(".rental-status")).toHaveText("Unsuccessful");
  await expect(
    lead.getByText("Outcome reason: Tenant selected another room."),
  ).toBeVisible();
});

test("tenant disputes pause landlord updates and admin resolution restores progress", async ({
  page,
}) => {
  await signIn(page, "tenant");
  await page
    .getByRole("link", { name: "Enquiry progress", exact: true })
    .click();
  const enquiry = page
    .locator(".rental-records > li")
    .filter({
      has: page.getByRole("heading", { name: "Courtyard room", exact: true }),
    });
  await enquiry
    .getByRole("button", { name: "Report inaccurate progress" })
    .click();
  await enquiry
    .getByLabel("Explain what is inaccurate")
    .fill(
      "The recorded enquiry progress does not match our viewing discussion.",
    );
  await enquiry.getByRole("button", { name: "Submit dispute" }).click();
  await expect(
    enquiry.getByText("Dispute: open", { exact: true }),
  ).toBeVisible();
  await signIn(page, "landlord");
  await page.goto("/landlord/leads");
  const landlordLead = page
    .locator(".rental-records > li")
    .filter({
      has: page.getByRole("heading", { name: "Courtyard room", exact: true }),
    });
  await expect(
    landlordLead.getByText(/Progress updates are paused/),
  ).toBeVisible();
  await expect(landlordLead.getByLabel("Next stage")).toHaveCount(0);
  await signIn(page, "admin");
  await page.getByRole("link", { name: "Lead disputes", exact: true }).click();
  const dispute = page
    .locator(".rental-records > li")
    .filter({ hasText: "Courtyard room" });
  await expect(
    dispute.getByRole("button", { name: "Save dispute decision" }),
  ).toBeDisabled();
  await dispute.getByLabel("Confirmed stage").selectOption("CONTACTED");
  await dispute
    .getByLabel("Decision reason")
    .fill("Both parties confirmed contact. Progress corrected.");
  await dispute.getByRole("button", { name: "Save dispute decision" }).click();
  await expect(page.getByText("No open lead disputes.")).toBeVisible();
  await signIn(page, "tenant");
  await page.goto("/tenant/leads");
  await expect(enquiry.locator(".rental-status")).toHaveText("Contacted");
  await expect(
    enquiry.getByText("Dispute: resolved", { exact: true }),
  ).toBeVisible();
  await enquiry.getByRole("button", { name: "View progress history" }).click();
  await expect(
    enquiry.getByText("Both parties confirmed contact. Progress corrected."),
  ).toHaveCount(0);
});

test("admin can dismiss a dispute while preserving its conversion stage", async ({
  page,
}) => {
  await signIn(page, "tenant");
  await page.goto("/tenant/leads");
  const enquiry = page
    .locator(".rental-records > li")
    .filter({
      has: page.getByRole("heading", { name: "Quiet room", exact: true }),
    });
  await enquiry
    .getByRole("button", { name: "Report inaccurate progress" })
    .click();
  await enquiry
    .getByLabel("Explain what is inaccurate")
    .fill("Please review the recorded enquiry information for this room.");
  await enquiry.getByRole("button", { name: "Submit dispute" }).click();
  await expect(
    enquiry.getByText("Dispute: open", { exact: true }),
  ).toBeVisible();
  await signIn(page, "admin");
  await page.goto("/admin/disputes");
  const dispute = page
    .locator(".rental-records > li")
    .filter({ hasText: "Quiet room" });
  await dispute
    .getByRole("combobox", { name: "Decision", exact: true })
    .selectOption("dismiss");
  await expect(dispute.getByLabel("Confirmed stage")).toHaveCount(0);
  await dispute
    .getByLabel("Decision reason")
    .fill("The recorded stage was confirmed as accurate.");
  await dispute.getByRole("button", { name: "Save dispute decision" }).click();
  await expect(page.getByText("No open lead disputes.")).toBeVisible();
  await signIn(page, "tenant");
  await page.goto("/tenant/leads");
  await expect(enquiry.locator(".rental-status")).toHaveText("New enquiry");
  await expect(
    enquiry.getByText("Dispute: dismissed", { exact: true }),
  ).toBeVisible();
});

test("verification supports private evidence, resubmission and owner-only trust status", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await signIn(page, "landlord");
  await page
    .getByRole("link", { name: "Trust & verification", exact: true })
    .click();
  await page
    .getByLabel("Supporting statement", { exact: true })
    .fill("Private synthetic identity evidence for administrator review.");
  await page
    .getByRole("button", { name: "Request verification", exact: true })
    .click();
  await expect(
    page.getByText("Awaiting review", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Request verification", exact: true }),
  ).toBeDisabled();
  await signIn(page, "admin");
  await page
    .getByRole("link", { name: "Verification review", exact: true })
    .click();
  await expect(
    page.getByText(/Private synthetic identity evidence/),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Decision", exact: true })
    .selectOption("request_information");
  await page
    .getByLabel("Decision reason")
    .fill("Please provide a clearer statement of your identity.");
  await page
    .getByRole("button", { name: "Save verification decision" })
    .click();
  await expect(page.getByText("No requests match this status.")).toBeVisible();
  await signIn(page, "landlord");
  await page.goto("/landlord/verification");
  await expect(
    page.getByText("More information needed", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Updated supporting statement")
    .fill("Updated private identity evidence with the requested information.");
  await page.getByRole("button", { name: "Resubmit for review" }).click();
  await expect(
    page.getByText("Awaiting review", { exact: true }),
  ).toBeVisible();
  await signIn(page, "admin");
  await page.goto("/admin/verification");
  await page
    .getByLabel("Decision reason")
    .fill("Identity statement reviewed and approved.");
  await page
    .getByRole("button", { name: "Save verification decision" })
    .click();
  await expect(page.getByText("No requests match this status.")).toBeVisible();
  await page.getByLabel("Request status").selectOption("approved");
  await page.getByRole("button", { name: "View audit history" }).click();
  await expect(page.locator(".rental-history li")).toHaveCount(4);
  await page.goto("/listings/1");
  const trust = page.getByRole("region", {
    name: "Landlord and property trust",
    exact: true,
  });
  await expect(trust).toHaveCount(0);
  await expect(page.getByText(/Updated private identity evidence/)).toHaveCount(
    0,
  );
  await signIn(page, "landlord");
  await page.goto("/landlord/verification");
  await expect(trust.locator("dl > div").filter({ hasText: "Landlord identity" }).locator("dd")).toHaveText("Verified");
  await page
    .getByLabel("Verification type")
    .selectOption("property_authorization");
  await page
    .getByRole("combobox", { name: "Room", exact: true })
    .selectOption("1");
  await page
    .getByLabel("Supporting statement", { exact: true })
    .fill("Private synthetic evidence of authorization to rent this property.");
  await page
    .getByRole("button", { name: "Request verification", exact: true })
    .click();
  await expect(
    page.getByText("Awaiting review", { exact: true }),
  ).toBeVisible();
  await signIn(page, "admin");
  await page.goto("/admin/verification");
  await page
    .getByLabel("Decision reason")
    .fill("Property authorization reviewed and approved.");
  await page
    .getByRole("button", { name: "Save verification decision" })
    .click();
  await expect(page.getByText("No requests match this status.")).toBeVisible();
  await page.goto("/listings/1");
  await expect(trust).toHaveCount(0);
  await signIn(page, "landlord");
  await page.goto("/landlord/verification");
  await page.getByLabel("Property trust summary").selectOption("1");
  await expect(
    trust
      .locator("dl > div")
      .filter({ hasText: "Property authorization" })
      .locator("dd"),
  ).toHaveText("Verified");
});

test("trust summary is absent from public room pages for every viewer", async ({ page }) => {
  const trust = page.getByRole("region", { name: "Landlord and property trust", exact: true });
  await page.goto("/listings/1");
  await expect(page.getByRole("heading", { name: "Garden room", exact: true })).toBeVisible();
  await expect(trust).toHaveCount(0);
  for (const role of ["tenant", "admin", "landlord"] as const) {
    await signIn(page, role);
    await page.goto("/listings/1");
    await expect(page.getByRole("heading", { name: "Garden room", exact: true })).toBeVisible();
    await expect(trust).toHaveCount(0);
  }
});

test("failed API requests can be retried and tenant access is restricted", async ({
  page,
}) => {
  await signIn(page, "tenant");
  await page.route("**/api/v1/users/me/lead-enquiries", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "Enquiry progress is temporarily unavailable.",
      }),
    }),
  );
  await page.goto("/tenant/leads");
  await expect(page.getByRole("alert")).toHaveText(
    "Enquiry progress is temporarily unavailable.",
  );
  await page.unroute("**/api/v1/users/me/lead-enquiries");
  await page
    .getByRole("button", { name: "Refresh your enquiry progress" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Courtyard room", exact: true }),
  ).toBeVisible();
  await page.goto("/admin/verification");
  await expect(
    page.getByRole("heading", { name: "Access unavailable" }),
  ).toBeVisible();
});

test("new workspaces remain usable on a narrow screen", async ({
  page,
}, info) => {
  await signIn(page, "tenant");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tenant/leads");
  await expect(
    page.getByRole("heading", { name: "Your enquiry progress", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: info.outputPath("mobile-enquiry-progress.png"),
    fullPage: true,
  });
});

test("landlord reports support the new reasons and admin internal notes", async ({
  page,
}) => {
  await signIn(page, "landlord");
  await page
    .getByRole("link", { name: "Reports", exact: true })
    .click();
  await page.getByLabel("What are you reporting?").selectOption("user");
  await page.getByLabel("User account ID").fill("1");
  await page
    .getByRole("combobox", { name: "Reason", exact: true })
    .selectOption("harassment");
  const details =
    "Synthetic report to validate the landlord reporting workflow.";
  await page.getByLabel(/What happened/).fill(details);
  await page
    .getByRole("button", { name: "Submit report", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Your report was submitted.",
  );
  await signIn(page, "admin");
  await page
    .getByRole("link", { name: "Reports", exact: true })
    .first()
    .click();
  // Keep the report visible after assignment changes it from open to under review.
  await page.getByLabel("Filter reports").selectOption("all");
  const report = page.locator("li").filter({ hasText: details });
  await report.getByRole("button", { name: "Assign to me" }).click();
  await report
    .getByLabel("Resolution or dismissal note (optional)")
    .fill("Reviewed the synthetic conversation evidence.");
  await report.getByRole("button", { name: "Add internal note" }).click();
  await report
    .getByRole("button", { name: "View history", exact: true })
    .click();
  await expect(report.getByText("note added", { exact: true })).toBeVisible();
});
