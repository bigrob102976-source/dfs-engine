import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { analyzeProjectionCsv } from "@/lib/csvImport";
import { isKnownImportProvider } from "@/lib/csvImportProviders";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Analyzes an uploaded projection CSV without saving anything -- powers
 * the Import Projections wizard's Preview / Auto Detect / Manual Mapping
 * / Validation Summary steps. Safe for the client to call again on every
 * mapping edit. Milestone 29: admin-only (the whole Import wizard is an
 * admin data-source operation). */
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
  const provider = form.get("provider");
  const date = form.get("date");
  const mappingRaw = form.get("mapping");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "Missing CSV file." }, { status: 400 });
  }
  if (!file.name.toLowerCase().endsWith(".csv")) {
    return NextResponse.json({ error: "Only .csv files are supported." }, { status: 400 });
  }
  if (typeof provider !== "string" || !isKnownImportProvider(provider)) {
    return NextResponse.json({ error: "Unknown provider." }, { status: 400 });
  }
  if (typeof date !== "string" || !DATE_RE.test(date)) {
    return NextResponse.json({ error: "Invalid slate date." }, { status: 400 });
  }

  let mapping: Record<string, string | null> | undefined;
  if (typeof mappingRaw === "string" && mappingRaw.trim()) {
    try {
      mapping = JSON.parse(mappingRaw);
    } catch {
      return NextResponse.json({ error: "mapping must be valid JSON." }, { status: 400 });
    }
  }

  const bytes = Buffer.from(await file.arrayBuffer());
  const result = await analyzeProjectionCsv(bytes, provider, date, mapping);
  if ("error" in result) {
    return NextResponse.json(result, { status: 502 });
  }
  return NextResponse.json(result);
}
