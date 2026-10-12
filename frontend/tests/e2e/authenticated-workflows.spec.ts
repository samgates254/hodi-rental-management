import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";

type Fixture = {
  password: string;
  users: Record<string, string>;
  tokens: Record<string, string>;
  organization_id: number;
  other_organization_id: number;
  maintenance_request_id: number;
  quotation_id: number;
  quotation_line_id: number;
  supplier_id: number;
  listing_id: number;
  property_listing_id: string;
  no_photo_listing_id: string;
};
const fixturePath = process.env.HODI_E2E_CREDENTIAL_FILE;
if (!fixturePath) throw new Error("Run this suite through backend/tests/e2e/run_local.py.");
const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8")) as Fixture;

async function signIn(page: Page, who: keyof Fixture["users"], kind: "tenant" | "landlord" = "landlord", throughUi = true) {
  if (!throughUi) {
    await page.goto("/");
    await page.evaluate(token => sessionStorage.setItem("hodi_api_token", token), fixture.tokens[who]);
    return;
  }
  await page.goto(`/signin?type=${kind}`);
  await page.locator('input[name="username"]').fill(fixture.users[who]);
  await page.locator('input[name="password"]').fill(fixture.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForURL(kind === "tenant" ? /\/clients/ : who === "accountant" ? /\/accountants/ : /\/landlords/);
  await expect(page.evaluate(() => sessionStorage.getItem("hodi_api_token"))).resolves.toBeTruthy();
}

async function authenticateWithRealApi(page: Page, who: keyof Fixture["users"]) {
  await page.goto("/");
  const result = await page.evaluate(async ({ username, password }) => {
    const response = await fetch("/api/v1/accounts/login/", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    return { status: response.status, body: await response.json() as {
      token?: string; account_type?: string; memberships?: unknown[]; first_name?: string;
      last_name?: string; email?: string; phone_number?: string;
    } };
  }, { username: fixture.users[who], password: fixture.password });
  expect(result.status).toBe(200);
  expect(result.body.token).toBeTruthy();
  await page.evaluate(auth => {
    sessionStorage.setItem("hodi_api_token", auth.token!);
    sessionStorage.setItem("hodi_account_type", auth.account_type ?? "");
    sessionStorage.setItem("hodi_memberships", JSON.stringify(auth.memberships ?? []));
    sessionStorage.setItem("hodi_first_name", auth.first_name ?? "");
    sessionStorage.setItem("hodi_last_name", auth.last_name ?? "");
    sessionStorage.setItem("hodi_email", auth.email ?? "");
    sessionStorage.setItem("hodi_phone_number", auth.phone_number ?? "");
  }, result.body);
}

async function api(page: Page, path: string, method = "GET", body?: unknown) {
  return page.evaluate(async ({ path, method, body }) => {
    const token = sessionStorage.getItem("hodi_api_token");
    const response = await fetch(path, {
      method,
      headers: { ...(token ? { Authorization: `Token ${token}` } : {}), ...(body ? { "Content-Type": "application/json" } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const text = await response.text();
    let payload: unknown = text;
    try { payload = text ? JSON.parse(text) : null; } catch { /* retain raw response */ }
    return { status: response.status, payload };
  }, { path, method, body });
}

test("role navigation and public listing photos work at desktop and mobile sizes", async ({ browser, baseURL }) => {
  const tenant = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await signIn(tenant, "tenant", "tenant");
  const more = tenant.locator(".portal-nav-more > summary");
  await more.click();
  const livingLink = tenant.getByRole("link", { name: "HODI Living", exact: true });
  await expect(livingLink).toHaveAttribute("href", "/living");
  await expect(tenant.getByRole("link", { name: "Utilities", exact: true })).toHaveAttribute("href", "/utilities");
  await expect(tenant.getByRole("link", { name: "Marketplace", exact: true })).toHaveAttribute("href", "/marketplace");
  await livingLink.click();
  await expect(tenant).toHaveURL(/\/living$/);
  await expect(tenant.getByRole("heading", { name: "Services and household goods" })).toBeVisible();

  const owner = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await signIn(owner, "owner", "landlord");
  const landlordNav = owner.getByRole("navigation", { name: "Landlord dashboard" });
  await expect(landlordNav.getByRole("link", { name: "Accountants" })).toHaveAttribute("href", "/accountants");
  await expect(landlordNav.getByRole("link", { name: "Utilities" })).toHaveAttribute("href", "#utilities");
  const portfolio = owner.getByRole("region", { name: "Portfolio summary" });
  await expect(portfolio).toBeVisible();
  await expect(portfolio.locator(".landlord-metric-card--accent")).toContainText("25,000");
  const managedPhotoRow = owner.locator("#marketplace tbody tr").filter({ hasText: "E2E Photo Listing" });
  const managedPhoto = managedPhotoRow.getByRole("img", { name: "E2E property exterior photo", exact: true });
  await expect(managedPhoto).toBeVisible();
  await managedPhoto.scrollIntoViewIfNeeded();
  await expect.poll(() => managedPhoto.evaluate(image => {
    const element = image as HTMLImageElement;
    return element.complete && element.naturalWidth > 0;
  })).toBe(true);
  await owner.setViewportSize({ width: 390, height: 844 });
  await expect(landlordNav).toBeVisible();
  await expect(landlordNav.getByRole("link", { name: "Properties" })).toBeVisible();
  await expect(landlordNav.getByRole("link", { name: "Accountants" })).toBeVisible();
  await expect.poll(() => landlordNav.evaluate(nav => nav.scrollWidth > nav.clientWidth)).toBe(true);
  const viewportWidth = await owner.evaluate(() => window.innerWidth);
  const documentWidth = await owner.evaluate(() => document.documentElement.scrollWidth);
  expect(documentWidth, "landlord dashboard should not widen the mobile viewport").toBeLessThanOrEqual(viewportWidth);

  const publicPage = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await publicPage.goto(`${baseURL}/marketplace`);
  const photoCard = publicPage.locator(`a[href="/marketplace/${fixture.property_listing_id}"]`);
  await expect(photoCard).toContainText("E2E Photo Listing");
  const photo = photoCard.locator('img[alt="E2E property exterior photo"]');
  await expect(photo).toBeVisible();
  await expect.poll(() => photo.evaluate(image => {
    const element = image as HTMLImageElement;
    return element.complete && element.naturalWidth > 0 && element.naturalHeight > 0;
  })).toBe(true);
  const photoBounds = await photo.boundingBox();
  expect(photoBounds).not.toBeNull();
  const cardPhotoRatio = photoBounds!.width / photoBounds!.height;
  expect(cardPhotoRatio).toBeGreaterThan(1.55);
  expect(cardPhotoRatio).toBeLessThan(1.65);
  await photoCard.click();
  await expect(publicPage.getByRole("heading", { name: "E2E Photo Listing" })).toBeVisible();
  const detailPhotoCaptions = await publicPage.evaluate(async listingId => {
    const response = await fetch(`/api/v1/marketplace/listings/${listingId}/`);
    const payload = await response.json() as { photos?: Array<{ caption: string; url: string }> };
    return { status: response.status, photos: payload.photos?.map(item => item.caption) };
  }, fixture.property_listing_id);
  console.log("Public detail photo captions:", detailPhotoCaptions);
  const gallery = publicPage.locator("main");
  const secondPhoto = gallery.getByRole("button", { name: "E2E interior photo" });
  await expect(secondPhoto).toBeVisible();
  await secondPhoto.click();
  await gallery.getByRole("button", { name: "Open photo: E2E interior photo" }).click();
  await expect(publicPage.getByRole("dialog", { name: "Photo gallery" }).getByRole("img", { name: "E2E interior photo" })).toBeVisible();
  await expect.poll(() => publicPage.getByRole("dialog", { name: "Photo gallery" }).getByRole("img", { name: "E2E interior photo" }).evaluate(image => {
    const element = image as HTMLImageElement;
    return element.complete && element.naturalWidth > 0;
  })).toBe(true);

  await publicPage.goto(`${baseURL}/marketplace`);
  const noPhotoCard = publicPage.locator(`a[href="/marketplace/${fixture.no_photo_listing_id}"]`);
  await expect(noPhotoCard).toContainText("No listing photo");
  await noPhotoCard.click();
  await expect(publicPage.getByRole("img", { name: "No listing photos available for E2E No Photo Listing" })).toBeVisible();
  await Promise.all([tenant.close(), owner.close(), publicPage.close()]);
});

test("tenant requests persist, utilities are scoped, and seller status changes persist", async ({ browser, baseURL }) => {
  const tenant = await browser.newPage();
  await signIn(tenant, "tenant", "tenant");
  await tenant.goto(`${baseURL}/living`);
  await expect(tenant.getByRole("heading", { name: "Services and household goods" })).toBeVisible();
  const listing = tenant.locator("article").filter({ has: tenant.getByRole("heading", { name: "E2E Cleaning Service" }) });
  await expect(listing).toContainText("KES");
  await listing.getByLabel("Request details").fill("E2E browser request");
  await listing.getByRole("button", { name: "Request", exact: true }).click();
  await expect(tenant.getByRole("status")).toContainText("request was sent");
  await expect(tenant.getByText("Payment: not processed (NOT_INTEGRATED)")).toBeVisible();
  await tenant.reload();
  await expect(tenant.getByText("REQUESTED", { exact: false }).last()).toBeVisible();
  const ownOrders = await api(tenant, "/api/v1/marketplace/commerce/orders/");
  expect(ownOrders.status).toBe(200);
  expect(ownOrders.payload).toHaveLength(1);
  const orderId = (ownOrders.payload as Array<{ id: number }>)[0].id;

  await tenant.goto(`${baseURL}/utilities`);
  await expect(tenant.getByRole("heading", { name: "Utilities for your tenancy" })).toBeVisible();
  await expect(tenant.getByText("WATER")).toBeVisible();
  await expect(tenant.getByText("PRIVATE-LANDLORD-REF")).toHaveCount(0);
  await expect(tenant.getByText("LANDLORD-SECRET")).toHaveCount(0);
  await expect(tenant.getByText("E2E Water Utility")).toHaveCount(0);
  const utilities = await api(tenant, "/api/v1/utilities/me/");
  expect(utilities.status).toBe(200);
  expect(utilities.payload).toHaveLength(1);
  expect(JSON.stringify(utilities.payload)).not.toContain("PRIVATE");
  expect((await api(tenant, "/api/v1/utilities/me/", "PATCH", { amount_minor: 1 })).status).toBe(405);

  const otherTenant = await browser.newPage();
  await signIn(otherTenant, "other_tenant", "tenant", false);
  const privateOrders = await api(otherTenant, "/api/v1/marketplace/commerce/orders/");
  expect(privateOrders.status).toBe(200);
  expect(privateOrders.payload).toHaveLength(0);
  await otherTenant.goto(`${baseURL}/living`);
  await expect(otherTenant.getByText("E2E browser request")).toHaveCount(0);
  await otherTenant.goto(`${baseURL}/utilities`);
  await expect(otherTenant.getByText("KES 2,750")).toBeVisible();
  await expect(otherTenant.getByText("KES 1,845")).toHaveCount(0);
  const otherUtilities = await api(otherTenant, "/api/v1/utilities/me/");
  expect(otherUtilities.status).toBe(200);
  expect(otherUtilities.payload).toHaveLength(1);
  expect(JSON.stringify(otherUtilities.payload)).not.toContain("PRIVATE");

  const owner = await browser.newPage();
  await authenticateWithRealApi(owner, "owner");
  await owner.goto(`${baseURL}/landlords`);
  await expect(owner.getByText("Suppliers, listings and requests")).toBeVisible();
  const requestCard = owner.getByRole("heading", { name: "Provider requests" }).locator("xpath=following-sibling::article[1]");
  await expect(requestCard).toContainText("E2E Cleaning Service");
  await expect(requestCard).toContainText("REQUESTED");
  await requestCard.getByRole("button", { name: "ACCEPTED" }).click();
  await expect(requestCard).toContainText("ACCEPTED");
  await owner.reload();
  const persistedRequest = owner.getByRole("heading", { name: "Provider requests" }).locator("xpath=following-sibling::article[1]");
  await expect(persistedRequest).toContainText("ACCEPTED");

  const otherOwner = await browser.newPage();
  await signIn(otherOwner, "other_owner", "landlord", false);
  expect((await api(otherOwner, `/api/v1/marketplace/commerce/orders/${orderId}/`, "PATCH", { status: "REJECTED" })).status).toBe(404);
  expect((await api(otherOwner, `/api/v1/marketplace/commerce/listings/${fixture.listing_id}/`, "PATCH", { is_published: false })).status).toBe(404);
  await Promise.all([tenant.close(), otherTenant.close(), owner.close(), otherOwner.close()]);
});

test("purchase, price history and receipt acknowledgement enforce ownership and separation of duties", async ({ browser, baseURL }) => {
  const owner = await browser.newPage();
  await signIn(owner, "owner", "landlord", false);
  const key = crypto.randomUUID();
  const recorded = await api(owner, `/api/v1/maintenance/requests/${fixture.maintenance_request_id}/purchases/`, "POST", {
    quotation_id: fixture.quotation_id,
    quotation_line_id: fixture.quotation_line_id,
    supplier_name: "HODI E2E Home Services",
    supplier_profile: fixture.supplier_id,
    supplier_reference: "E2E-REC-1",
    quantity: "2.000",
    unit_price_cents: 100000,
    purchase_date: new Date().toISOString().slice(0, 10),
    idempotency_key: key,
  });
  expect(recorded.status, JSON.stringify(recorded.payload)).toBe(201);
  const purchase = (recorded.payload as { purchase: { id: number; purchase_total_cents: number; quotation_line: number; supplier_profile: number } }).purchase;
  expect(purchase.purchase_total_cents).toBe(200000);
  expect(purchase.quotation_line).toBe(fixture.quotation_line_id);
  expect(purchase.supplier_profile).toBe(fixture.supplier_id);
  const replay = await api(owner, `/api/v1/maintenance/requests/${fixture.maintenance_request_id}/purchases/`, "POST", {
    quotation_id: fixture.quotation_id, quotation_line_id: fixture.quotation_line_id,
    supplier_name: "HODI E2E Home Services", supplier_profile: fixture.supplier_id, supplier_reference: "E2E-REC-1",
    quantity: "2.000", unit_price_cents: 100000, purchase_date: new Date().toISOString().slice(0, 10), idempotency_key: key,
  });
  expect(replay.status).toBe(200);
  expect((replay.payload as { idempotent_replay: boolean }).idempotent_replay).toBe(true);
  expect((await api(owner, `/api/v1/maintenance/requests/${fixture.maintenance_request_id}/purchases/${purchase.id}/receipts/`, "POST", {
    quantity: "2.000", evidence_reference: "E2E test receipt", idempotency_key: crypto.randomUUID(),
  })).status).toBe(403);

  const caretaker = await browser.newPage();
  await signIn(caretaker, "caretaker", "landlord", false);
  const receipt = await api(caretaker, `/api/v1/maintenance/requests/${fixture.maintenance_request_id}/purchases/${purchase.id}/receipts/`, "POST", {
    quantity: "2.000", evidence_reference: "E2E test receipt", idempotency_key: crypto.randomUUID(),
  });
  expect(receipt.status).toBe(201);
  const price = await api(owner, "/api/v1/maintenance/price-history/?item=E2E%20copper%20pipe&unit=metre");
  expect(price.status).toBe(200);
  expect(price.payload).toEqual(expect.arrayContaining([expect.objectContaining({ unit_price_cents: 100000 })]));
  const isolated = await api(caretaker, "/api/v1/maintenance/price-history/?item=E2E%20copper%20pipe&unit=metre");
  expect(isolated.status).toBe(200);
  expect(isolated.payload).toHaveLength(0);
  await owner.close();
  await caretaker.close();
  void baseURL;
});

test("accountant invitation acceptance is identity-bound, reports real client data, and revocation removes access", async ({ browser, baseURL }) => {
  const owner = await browser.newPage();
  await signIn(owner, "owner", "landlord", false);
  const invited = await api(owner, "/api/v1/organizations/accountant-invitations/", "POST", {
    organization: fixture.organization_id,
    email: "accountant@hodi-e2e.invalid",
  });
  expect(invited.status).toBe(201);
  const invitationId = (invited.payload as { id: number }).id;

  const impostor = await browser.newPage();
  await signIn(impostor, "impostor", "landlord", false);
  expect((await api(impostor, `/api/v1/organizations/accountant-invitations/${invitationId}/accept/`, "POST", {})).status).toBe(404);
  await impostor.close();

  const accountant = await browser.newPage();
  await signIn(accountant, "accountant");
  await accountant.goto(`${baseURL}/accountants`);
  await expect(accountant.getByRole("heading", { name: "Accountant workspace" })).toBeVisible();
  await expect(accountant.getByText("Invitation to HODI E2E Demo Organisation")).toBeVisible();
  await accountant.getByRole("button", { name: "Accept" }).click();
  await expect(accountant.getByLabel("Client organisation")).toContainText("HODI E2E Demo Organisation");
  await expect(accountant.getByText("Invoices", { exact: true })).toBeVisible();
  await expect(accountant.getByRole("heading", { name: "KES 25,000" })).toBeVisible();
  const invoices = await api(accountant, `/api/v1/billing/invoices/?organization=${fixture.organization_id}`);
  expect(invoices.status).toBe(200);
  expect(invoices.payload).toHaveLength(1);
  const otherClientInvoices = await api(accountant, `/api/v1/billing/invoices/?organization=${fixture.other_organization_id}`);
  expect(otherClientInvoices.status).toBe(200);
  expect((otherClientInvoices.payload as Array<{ organization: number }>).every(row => row.organization !== fixture.other_organization_id)).toBe(true);
  expect((await api(accountant, `/api/v1/organizations/accountant-invitations/${invitationId}/accept/`, "POST", {})).status).toBe(200);

  expect((await api(owner, `/api/v1/organizations/accountant-invitations/${invitationId}/revoke/`, "POST", {})).status).toBe(200);
  await accountant.reload();
  await expect(accountant.getByText("No active client access or pending invitations")).toBeVisible();
  expect((await api(accountant, `/api/v1/billing/invoices/?organization=${fixture.organization_id}`)).status).toBe(403);
  await owner.close();
  await accountant.close();
});
