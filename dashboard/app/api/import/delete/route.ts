import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { deleteProjectionImport } from "@/lib/csvImport";

export const dynamic = "force-dynamic";

/** Deletes a CSV-imported baseline snapshot. The underlying script
 * refuses to delete anything outside external_projection_snapshots/ or
 * not tagged source == "csv_import" (see
 * external_projections/csv_import/history.py::_validate_owned_path) --
 * this route just surfaces that result. Milestone 29: admin-only. */
export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const path = (body as { path?: unknown })?.path;
  if (typeof path !== "string" || !path) {
    return NextResponse.json({ error: "`path` is required." }, { status: 400 });
  }

  const result = await deleteProjectionImport(path);
  if ("error" in result) {
    return NextResponse.json(result, { status: 400 });
  }
  return NextResponse.json(result);
}
