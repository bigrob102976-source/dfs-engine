import fs from "node:fs";
import path from "node:path";

import { NextResponse } from "next/server";

import { ARTIFACT_DIRS, artifactPath } from "@/lib/artifactRoot";

export const dynamic = "force-dynamic";

// Only ever serves a file that (a) resolves inside the lineups/ artifact
// directory and (b) matches the exact filename shape
// optimizer/persistence.py::save_lineup_set_csv() produces -- a
// browser-supplied `path` query value can never read anything outside
// that directory or with any other name (blocks `..` traversal and any
// attempt to read an arbitrary file on disk).
const CSV_NAME_PATTERN = /^dk_lineups_\d{8}T\d{6}\.csv$/;

/** Downloads a lineup set's already-persisted CSV (the same file
 * optimizer/persistence.py::save_lineup_set_csv wrote at build time) --
 * this is the project's existing normalized optimizer CSV format, not a
 * verified DraftKings bulk-upload template. */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const requested = url.searchParams.get("path");
  if (!requested) {
    return NextResponse.json({ error: "\"path\" query parameter is required." }, { status: 400 });
  }

  const lineupsRoot = path.resolve(artifactPath(ARTIFACT_DIRS.lineups));
  const resolved = path.resolve(requested);
  const relative = path.relative(lineupsRoot, resolved);
  const withinLineupsRoot = relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative);

  if (!withinLineupsRoot || !CSV_NAME_PATTERN.test(path.basename(resolved))) {
    return NextResponse.json({ error: "Not a valid lineup export path." }, { status: 400 });
  }

  let contents: Buffer;
  try {
    contents = fs.readFileSync(resolved);
  } catch {
    return NextResponse.json({ error: "Export file not found." }, { status: 404 });
  }

  return new NextResponse(new Uint8Array(contents), {
    status: 200,
    headers: {
      "Content-Type": "text/csv",
      "Content-Disposition": `attachment; filename="${path.basename(resolved)}"`,
    },
  });
}
