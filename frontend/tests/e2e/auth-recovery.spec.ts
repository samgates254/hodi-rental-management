import { expect, test } from "@playwright/test";

test("password recovery request gives the same safe confirmation", async ({ page }) => {
  await page.route(/\/api\/v1\/accounts\/password-reset\/?$/, route => route.fulfill({
    status: 202,
    contentType: "application/json",
    body: JSON.stringify({ detail: "If an active account uses that email, reset instructions will be sent." }),
  }));

  await page.goto("/signin");
  await page.getByRole("link", { name: "Forgot password?" }).click();
  await expect(page).toHaveURL(/\/password-reset$/);
  await page.getByLabel("Email address").fill("tenant@example.com");
  await page.getByRole("button", { name: "Send reset instructions" }).click();
  await expect(page.getByRole("status")).toContainText("If an active account uses that email");
});

test("password reset link fills secure values and submits a new password", async ({ page }) => {
  let submitted: unknown;
  await page.route(/\/api\/v1\/accounts\/password-reset\/confirm\/?$/, async route => {
    submitted = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Your password has been reset. Please log in again." }),
    });
  });

  await page.goto("/password-reset/confirm#uid=encoded-user&token=one-time-token");
  await expect(page.getByLabel("Reset user code")).toHaveValue("encoded-user");
  await expect(page.getByLabel("Reset token")).toHaveValue("one-time-token");
  await page.getByLabel("New password").fill("a-strong-new-password-123");
  await page.getByLabel("Confirm new password").fill("a-strong-new-password-123");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByRole("status")).toContainText("Your password has been reset");
  expect(submitted).toMatchObject({ uid: "encoded-user", token: "one-time-token" });
});
