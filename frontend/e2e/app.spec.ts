import { expect, test } from "@playwright/test";

const ADMIN_PASSWORD = "test-admin-password";
const GENRE_NAME = "E2E Genre";

/**
 * The suite runs against a freshly migrated compose stack with an empty
 * database. Mutating steps must stay in this single test so retries and
 * re-runs never depend on data from a previous attempt.
 */
test("public radio and studio flows work end to end", async ({ page }) => {
  // Keep the run offline: the app loads fonts and the YouTube iframe API,
  // neither of which should gate the smoke test.
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.hostname === "127.0.0.1" || url.hostname === "localhost") {
      return route.continue();
    }
    return route.abort();
  });

  await test.step("homepage loads on an empty station", async () => {
    await page.goto("/");

    await expect(
      page.getByRole("banner").getByText("Nakout Radio"),
    ).toBeVisible();
    const schedule = page.getByRole("region", { name: "Today's schedule" });
    await expect(schedule).toBeVisible();
    await expect(schedule).toContainText("No schedule slots yet.");
    await expect(page.getByRole("button", { name: "Tune in" })).toBeDisabled();
    await expect(page.getByText("1 listening")).toBeVisible({ timeout: 15_000 });
  });

  await test.step("wrong password is rejected", async () => {
    await page.goto("/studio");

    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page.getByRole("alert")).toBeVisible();
  });

  await test.step("admin signs in and creates a genre", async () => {
    await page.getByLabel("Password").fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(
      page.getByRole("tablist", { name: "Studio sections" }),
    ).toBeVisible();

    await page.getByRole("tab", { name: /Genres/ }).click();
    await page.getByLabel("Genre name").fill(GENRE_NAME);
    await expect(page.getByLabel("Genre slug")).toHaveValue("e2egenre");
    await page.getByRole("button", { name: "Add genre" }).click();
    await expect(page.getByRole("status")).toContainText(`${GENRE_NAME} added`);
  });

  await test.step("genre is scheduled every day", async () => {
    await page.getByRole("tab", { name: /Schedule/ }).click();
    await page.getByRole("button", { name: "Add the first slot" }).click();

    const form = page.getByTestId("slot-form");
    await form.getByRole("radio", { name: GENRE_NAME }).click();
    await form.getByRole("button", { name: "Every day" }).click();
    await expect(form.getByTestId("sentence")).toContainText(GENRE_NAME);
    await form.getByRole("button", { name: "Add slot" }).click();
    await expect(form).toBeHidden();
    await expect(page.getByText(GENRE_NAME).first()).toBeVisible();
  });

  await test.step("public schedule shows the new genre", async () => {
    await page.goto("/");
    await expect(
      page.getByRole("region", { name: "Today's schedule" }),
    ).toContainText(GENRE_NAME);
  });

  await test.step("logout returns to the login screen", async () => {
    await page.goto("/studio");
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page.getByLabel("Password")).toBeVisible();
  });
});
