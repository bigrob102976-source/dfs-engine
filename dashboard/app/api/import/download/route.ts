import fs from "node:fs";
import path from "node:path";

import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { resolveOwnedImportSnapshotPath } from "@/lib/csvImport";

export const dynamic = "force-dynamic";

/** Downloads the raw immutable snapshot JSON for a CSV-imported baseline
 * -- the one History action that reads the file directly instead of
 * going through a Python script, so the path is independently validated
 * here (see resolveOwnedImportSnapshotPath) before anything is read.
 * Milestone 29: admin-only, part of the admin Import history surface. */
export async function GET(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const rawPath = new URL(request.url).searchParams.get("path");
  if (!rawPath) {
    return NextResponse.json({ error: "Query param `path` is required." }, { status: 400 });
  }

  const resolved = resolveOwnedImportSnapshotPath(rawPath);
  if (!resolved) {
    return NextResponse.json({ error: "Not a downloadable CSV-imported snapshot." }, { status: 404 });
  }

  const content = fs.readFileSync(resolved, "utf-8");
  return new NextResponse(content, {
    headers: {
      "Content-Type": "application/json",
      "Content-Disposition": `attachment; filename="${path.basename(resolved)}"`,
    },
  });
}
