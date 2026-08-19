import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { importDkContestResults } from "@/lib/contestResultsImport";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Imports a real, official DraftKings contest-standings CSV (Milestone
 * 27, Part 4) -- actual ownership, contest score, rank, winning score,
 * and field size for a completed slate. Purely a postgame import: never
 * required to calculate a player's actual DK fantasy points (that comes
 * from results/<date>/*.json via the existing MLB Stats-based pipeline
 * regardless of whether a contest CSV is ever imported). Milestone 29:
 * admin-only, another backend-data upload action. */
export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ error: "Request must be multipart/form-data." }, { status: 400 });
  }

  const file = form.get("file");
  const date = form.get("date");
  const slateId = form.get("slateId");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "Missing CSV file." }, { status: 400 });
  }
  if (!file.name.toLowerCase().endsWith(".csv")) {
    return NextResponse.json({ error: "Only .csv files are supported." }, { status: 400 });
  }
  if (typeof date !== "string" || !DATE_RE.test(date)) {
    return NextResponse.json({ error: "Invalid slate date." }, { status: 400 });
  }

  const bytes = Buffer.from(await file.arrayBuffer());
  const result = await importDkContestResults(bytes, date, typeof slateId === "string" && slateId ? slateId : null);
  return NextResponse.json(result, { status: result.status === "ready" ? 200 : 422 });
}
