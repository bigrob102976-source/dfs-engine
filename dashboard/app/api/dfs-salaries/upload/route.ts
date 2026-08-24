import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { recordAuditLog } from "@/lib/db/auditLog";
import { uploadDraftKingsCsv } from "@/lib/draftKingsUpload";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Uploads a real, official DraftKings salary-export CSV (Milestone
 * 19) -- the highest-priority DFS salary source (see
 * dfs/providers/config.py). Rejects a non-.csv file and a bad DK export
 * format immediately; a valid upload is picked up automatically on the
 * next "Refresh Today's Slate". Milestone 29: admin-only -- members
 * should never need to upload DraftKings salary CSV files. */
export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const admin = userOrRes;

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ error: "Request must be multipart/form-data." }, { status: 400 });
  }

  const file = form.get("file");
  const date = form.get("date");
  const slateLabel = form.get("slateLabel");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "Missing CSV file." }, { status: 400 });
  }
  if (!file.name.toLowerCase().endsWith(".csv")) {
    return NextResponse.json({ error: "Only .csv files are supported." }, { status: 400 });
  }
  if (typeof date !== "string" || !DATE_RE.test(date)) {
    return NextResponse.json({ error: "Invalid slate date." }, { status: 400 });
  }
  if (typeof slateLabel !== "string" || !slateLabel.trim()) {
    return NextResponse.json({ error: "A slate label (Main, Turbo, Night, ...) is required." }, { status: 400 });
  }

  const bytes = Buffer.from(await file.arrayBuffer());
  const result = await uploadDraftKingsCsv(bytes, date, slateLabel.trim(), file.name);
  if (result.status === "ready") {
    await recordAuditLog({
      actorUserId: admin.id, actorLabel: admin.email, action: "dk_csv_uploaded",
      targetType: "slate", targetId: date, metadata: { date, slateLabel: slateLabel.trim(), filename: file.name },
    });
  }
  return NextResponse.json(result, { status: result.status === "ready" ? 200 : 422 });
}
