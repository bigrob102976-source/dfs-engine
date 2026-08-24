import { NextResponse } from "next/server";

import { getDatabaseReadiness, getObjectStorageReadiness } from "@/lib/systemReadiness";

import packageJson from "../../../package.json";

export const dynamic = "force-dynamic";

function toHealthStatus(ok: boolean): "healthy" | "unhealthy" {
  return ok ? "healthy" : "unhealthy";
}

/** Milestone 33.2.2 hotfix: PUBLIC, unauthenticated health endpoint --
 * exempted from dashboard/proxy.ts's session-cookie gate (see that
 * file's PUBLIC_PATH_PREFIXES) because a load balancer / hosting
 * platform's health check has no session cookie to send. Reuses the
 * SAME SAFE-only readiness functions the admin-only System page already
 * calls (lib/systemReadiness.ts::getDatabaseReadiness/
 * getObjectStorageReadiness) -- no new database/storage logic, no
 * credential ever passes through either function (confirmed by their
 * own docstrings/tests), and this route additionally never forwards
 * their `detail` string (which can legitimately contain a raw error
 * message, e.g. a failed connection's hostname) -- only the already-
 * sanitized status/backend enum values reach the response. A dependency
 * reported unhealthy returns HTTP 503 (still with a fully sanitized
 * body), never a 200 masking a real outage, and never a stack trace
 * even on a genuinely unexpected internal error. */
export async function GET() {
  try {
    const [database, storage] = await Promise.all([getDatabaseReadiness(), getObjectStorageReadiness()]);
    const databaseHealthy = database.status === "CONNECTED";
    const storageHealthy = storage.status === "CONNECTED";
    const healthy = databaseHealthy && storageHealthy;

    return NextResponse.json(
      {
        status: toHealthStatus(healthy),
        database: { status: toHealthStatus(databaseHealthy), backend: database.kind },
        storage: { status: toHealthStatus(storageHealthy), backend: storage.backend },
        version: packageJson.version,
        timestamp: new Date().toISOString(),
      },
      { status: healthy ? 200 : 503 },
    );
  } catch {
    // Defense in depth -- getDatabaseReadiness()/getObjectStorageReadiness()
    // already catch everything internally and return a structured
    // ERROR/NOT_CONFIGURED result rather than throwing, but this route
    // must never let an unexpected error escape as a raw stack trace to
    // an unauthenticated caller either way.
    return NextResponse.json({ status: "unhealthy" }, { status: 503 });
  }
}
