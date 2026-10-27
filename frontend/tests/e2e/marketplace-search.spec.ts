import { expect, test, type Page } from "@playwright/test";

function listing(id: string, title: string) {
  return {
    id,
    title,
    description: "A bright home near local services.",
    monthly_rent_minor: 4_500_000,
    currency: "KES",
    bedrooms: 1,
    bathrooms: 1,
    floor: null,
    size_sqm: null,
    furnished: false,
    amenities: ["Parking", "Water"],
    area: "Kilimani",
    city: "Nairobi",
    country: "Kenya",
    property_name: "Kilimani Garden Court",
    unit_label: "A-01",
    available: true,
    published_at: "2026-10-14T08:00:00Z",
    photos: [],
  };
}

async function mockMarketplace(page: Page, responseFor: (url: URL) => object) {
  await page.route(/\/api\/v1\/marketplace\/listings\/?(?:\?.*)?$/, async route => {
    const url = new URL(route.request().url());
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(responseFor(url)) });
  });
}

test("property search keeps filters and pagination in the shareable URL", async ({ page }) => {
  await mockMarketplace(page, url => {
    const pageNumber = Number(url.searchParams.get("page") ?? "1");
    const filtered = url.searchParams.has("q");
    return {
      count: filtered ? 1 : 25,
      next: pageNumber < (filtered ? 1 : 3) ? `http://127.0.0.1:8766/api/v1/marketplace/listings/?page=${pageNumber + 1}` : null,
      previous: pageNumber > 1 ? `http://127.0.0.1:8766/api/v1/marketplace/listings/?page=${pageNumber - 1}` : null,
      results: [listing(pageNumber === 2 ? "listing-2" : "listing-1", pageNumber === 2 ? "Second page home" : "Kilimani garden home")],
    };
  });

  await page.goto("/marketplace");
  await expect(page.getByRole("heading", { name: "Kilimani garden home" })).toBeVisible();
  await page.getByLabel("Keywords").fill("Kilimani");
  await page.getByLabel("Location").fill("Nairobi");
  await page.getByLabel("Min rent (KES)").fill("10000");
  await page.getByLabel("Amenity").fill("Parking, Water");
  await page.getByRole("button", { name: "Search", exact: true }).click();

  await expect(page).toHaveURL(/\/marketplace\?q=Kilimani/);
  await expect(page).toHaveURL(/location=Nairobi/);
  await expect(page).toHaveURL(/min_rent=1000000/);
  await expect(page).toHaveURL(/amenity=Parking/);
  await expect(page.getByText("1 home found")).toBeVisible();

  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await expect(page).toHaveURL("/marketplace");
  await expect(page.getByText("25 homes found")).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.getByRole("heading", { name: "Second page home" })).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL("/marketplace");
  await expect(page.getByRole("heading", { name: "Kilimani garden home" })).toBeVisible();
});

test("marketplace shows a useful empty state and validation feedback", async ({ page }) => {
  await mockMarketplace(page, () => ({ count: 0, next: null, previous: null, results: [] }));
  await page.goto("/marketplace?q=unlikely");
  await expect(page.getByRole("heading", { name: "No listings match" })).toBeVisible();
  await expect(page.getByText(/Try changing or clearing them/)).toBeVisible();

  await page.getByLabel("Min rent (KES)").fill("20000");
  await page.getByLabel("Max rent (KES)").fill("10000");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("Maximum rent must be at least the minimum rent.")).toBeVisible();
});
