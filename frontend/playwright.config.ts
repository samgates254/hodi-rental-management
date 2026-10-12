import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  grep: process.env.HODI_E2E_GREP ? new RegExp(process.env.HODI_E2E_GREP) : undefined,
  reporter: "list",
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR ?? "test-results",
  use: {
    baseURL: process.env.HODI_E2E_BASE_URL ?? "http://127.0.0.1:8766",
    headless: true,
    launchOptions: {
      executablePath: process.env.CHROME_BIN ?? "/usr/bin/google-chrome",
      args: ["--no-sandbox"],
    },
  },
});
