import { NextResponse } from "next/server";

import packageJson from "../../../package.json";

export const dynamic = "force-dynamic";

/** Milestone 30: PUBLIC, unauthenticated health endpoint -- deliberately
 * minimal (status/version/timestamp only, nothing about the database,
 * storage, job queue, or any provider). A load balancer / hosting
 * platform's health check hits this; it must never leak infrastructure
 * detail to an unauthenticated caller. The deeper, credential-free-but-
 * still-admin-only readiness view (Database/Object Storage/Job Queue/
 * Worker/SportsGameOdds/Stripe) is the existing Admin System page
 * (app/admin/system/page.tsx, gated by requireAdmin()), extended in this
 * milestone with lib/systemReadiness.ts's new cards -- not duplicated
 * here as a second API route no UI calls. */
export async function GET() {
  return NextResponse.json({
    status: "ok",
    version: packageJson.version,
    timestamp: new Date().toISOString(),
  });
}
