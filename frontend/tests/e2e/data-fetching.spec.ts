import { test, expect, type Page } from "@playwright/test";

function room(id: number) {
  return { listing_id: id, area_id: 1, area_name: "Durban", title: `Test room ${id}`,
    description: "Full room description", room_type: "single_room", monthly_rent: "4200.00",
    deposit_amount: "4200.00", address: "Durban", date_available: "2026-12-01",
    status: "active", created_at: "2026-11-01T10:00:00", photos: [], amenities: [], has_map_location: false };
}

async function mockPublicReads(page: Page) {
  const counts = { pages: 0, details: 0, catalogs: 0 };
  await page.route(/\/api\/v1\/(areas|amenities)$/, route => {
    counts.catalogs++;
    return route.fulfill({ json: [] });
  });
  await page.route(/\/api\/v1\/interest-opportunities/, route => route.fulfill({ json: [] }));
  await page.route(/\/api\/v1\/listings\/\d+$/, route => {
    counts.details++;
    return route.fulfill({ json: room(Number(route.request().url().split("/").pop())) });
  });
  await page.route(/\/api\/v1\/listings\/search\?/, route => {
    counts.pages++;
    const offset = Number(new URL(route.request().url()).searchParams.get("offset"));
    return route.fulfill({ json: { items: Array.from({ length: offset ? 4 : 8 },
      (_, i) => room(offset + i + 1)), next_offset: offset ? null : 8 } });
  });
  return counts;
}

test("public navigation reuses pages and full details, and local controls do not refetch", async ({ page }) => {
  const counts = await mockPublicReads(page);
  await page.goto("/");
  await expect(page.locator(".room-card")).toHaveCount(8);
  await page.getByRole("button", { name: "Filters +", exact: true }).click();
  await page.getByRole("button", { name: "Map", exact: true }).click();
  await page.getByRole("button", { name: "List", exact: true }).click();
  expect(counts).toEqual({ pages: 1, details: 0, catalogs: 2 });
  await page.getByRole("link", { name: "View details for Test room 1", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Test room 1", exact: true })).toBeVisible();
  await page.getByRole("link", { name: /Back to rooms/ }).click();
  await expect(page.locator(".room-card")).toHaveCount(8);
  await page.getByRole("link", { name: "View details for Test room 1", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Test room 1", exact: true })).toBeVisible();
  expect(counts).toEqual({ pages: 1, details: 1, catalogs: 2 });
  console.log("Navigation and local controls: 1 listing-page request, 1 detail request, 2 catalog requests.");
});

test("load more adds a bounded page, and fast typing sends one debounced search", async ({ page }) => {
  const counts = await mockPublicReads(page);
  await page.goto("/");
  await expect(page.locator(".room-card")).toHaveCount(8);
  await page.getByRole("button", { name: "Load more rooms", exact: true }).click();
  await expect(page.locator(".room-card")).toHaveCount(12);
  await expect(page.getByRole("button", { name: "Load more rooms", exact: true })).toHaveCount(0);
  const input = page.getByLabel("Where would you like to live?");
  await input.fill("Dur");
  await input.fill("Durba");
  const request = page.waitForRequest(request => request.url().includes("search=durban"));
  await input.fill("Durban");
  await request;
  await expect(page.locator(".room-card")).toHaveCount(8);
  expect(counts.pages).toBe(3);
});

test("session changes remove private data and reject late results while retaining public data", async ({ page }) => {
  await mockPublicReads(page);
  await page.goto("/");
  await expect(page.locator(".room-card")).toHaveCount(8);
  const result = await page.evaluate(async () => {
    const modulePath = "/src/queryClient.ts";
    const { queryClient, setQuerySession, resourceOptions } = await import(modulePath);
    setQuerySession("first-test-session");
    const firstKey = resourceOptions("/api/v1/users/me/listings", "first-test-session").queryKey;
    queryClient.setQueryData(firstKey, [{ title: "Private owner room" }]);
    let finish: (value: unknown) => void = () => {};
    const pending = queryClient.fetchQuery({
      queryKey: [...firstKey, "slow"], queryFn: () => new Promise(resolve => { finish = resolve; }),
    }).then(() => "accepted", () => "cancelled");
    setQuerySession(null);
    finish([{ title: "Late private result" }]);
    const outcome = await pending;
    setQuerySession("second-test-session");
    const secondKey = resourceOptions("/api/v1/users/me/listings", "second-test-session").queryKey;
    return {
      outcome, privateCount: queryClient.getQueryCache().findAll({ queryKey: ["private"] }).length,
      publicCount: queryClient.getQueryCache().findAll({ queryKey: ["public"] }).length,
      distinct: JSON.stringify(firstKey) !== JSON.stringify(secondKey),
      noTokenInKeys: !JSON.stringify([firstKey, secondKey]).includes("test-session"),
    };
  });
  expect(result.outcome).toBe("cancelled");
  expect(result.privateCount).toBe(0);
  expect(result.publicCount).toBeGreaterThan(0);
  expect(result.distinct).toBe(true);
  expect(result.noTokenInKeys).toBe(true);
});

test("a frontend-first deployment can still browse rooms against the previous backend", async ({ page }) => {
  await mockPublicReads(page);
  let legacyRequests = 0;
  await page.route(/\/api\/v1\/listings$/, route => {
    legacyRequests++;
    return route.fulfill({ json: Array.from({ length: 12 }, (_, i) => room(i + 1)) });
  });
  await page.route(/\/api\/v1\/listings\/search\?/, route => route.fulfill({ status: 422,
    json: { detail: [{ loc: ["path", "listing_id"], type: "int_parsing", msg: "Input should be a valid integer" }] },
  }));
  await page.goto("/");
  await expect(page.locator(".room-card")).toHaveCount(8);
  await page.getByRole("button", { name: "Load more rooms", exact: true }).click();
  await expect(page.locator(".room-card")).toHaveCount(12);
  expect(legacyRequests).toBe(1);
});
