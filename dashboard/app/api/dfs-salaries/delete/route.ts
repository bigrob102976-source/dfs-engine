import { NextResponse } from "next/server";

import { deleteDraftKingsUpload } from "@/lib/draftKingsUpload";

export const dynamic = "force-dynamic";

/** Deletes a real DraftKings CSV upload (Milestone 19). The underlying
 * script refuses to delete anything outside
 * dfs_input/<date>/uploaded_dk_slates/ -- this route just surfaces that
 * result. */
export async function POST(request: Request) {
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

  const result = await deleteDraftKingsUpload(path);
  if ("error" in result) {
    return NextResponse.json(result, { status: 400 });
  }
  return NextResponse.json(result);
}
