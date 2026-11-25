import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontend = path.dirname(fileURLToPath(import.meta.url));
const backend = path.resolve(frontend, "../backend");
const python =
  process.platform === "win32"
    ? ".venv/Scripts/python.exe"
    : ".venv/bin/python";
const database = process.env.E2E_DATABASE_URL;
if (
  !database ||
  !/^postgresql(?:\+psycopg)?:\/\/[^@]+@127\.0\.0\.1:55433\/room_rental_frontend_e2e$/.test(
    database,
  )
) {
  throw new Error(
    "Set E2E_DATABASE_URL to the dedicated local browser-test database on port 55433. Production databases are refused.",
  );
}
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45_000,
  use: {
    ...devices["Desktop Chrome"],
    channel: "chrome",
    baseURL: "http://127.0.0.1:5187",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `"${path.join(backend, python)}" -m uvicorn app.main:app --host 127.0.0.1 --port 8017`,
      cwd: backend,
      url: "http://127.0.0.1:8017/health",
      reuseExistingServer: false,
      env: {
        DATABASE_URL: database,
        JWT_SECRET_KEY: "local-browser-test-signing-key-only-20261125",
        CORS_ALLOWED_ORIGINS: "http://127.0.0.1:5187",
      },
    },
    {
      command: "npm run dev -- --port 5187 --strictPort",
      cwd: frontend,
      url: "http://127.0.0.1:5187",
      reuseExistingServer: false,
      env: {
        VITE_API_BASE_URL: "http://127.0.0.1:8017",
        VITE_GOOGLE_MAPS_API_KEY: "",
      },
    },
  ],
});
