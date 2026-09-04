import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { validateDkCsvUpload } from "@/lib/adminCsvImport";

export const dynamic = "force-dynamic";

// BREAK-GLASS ADMIN CSV UPLOAD Phase 2/10/12: preview-only structural
// validation of a real DraftKings CSV, before the admin decides to
// import it. Never persists anything -- see lib/adminCsvImport.ts's own
// docstring. ADMIN only; MEMBER/unauthenticated get requireAdminApi()'s
// standard 403/redirect.
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024; // 10MB -- a real DK Classic export is a few hundred KB even at hundreds of players.

export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ status: "invalid", reason: "Request must be multipart/form-data." }, { status: 400 });
  }

  const file = form.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ status: "invalid", reason: "Missing CSV file." }, { status: 400 });
  }
  if (!file.name.toLowerCase().endsWith(".csv")) {
    return NextResponse.json({ status: "invalid", reason: "Only .csv files are supported." }, { status: 400 });
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return NextResponse.json({ status: "invalid", reason: `File is too large (${file.size} bytes) -- a real DraftKings CSV export never exceeds ${MAX_UPLOAD_BYTES} bytes.` }, { status: 413 });
  }

  const bytes = Buffer.from(await file.arrayBuffer());
  const result = await validateDkCsvUpload(bytes);
  return NextResponse.json(result, { status: result.status === "valid" ? 200 : 422 });
}
