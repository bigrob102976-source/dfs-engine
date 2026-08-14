import { NextResponse } from "next/server";

import { saveProjectionCsvImport } from "@/lib/csvImport";
import { isKnownImportProvider } from "@/lib/csvImportProviders";

export const dynamic = "force-dynamic";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Saves an uploaded projection CSV as an immutable External Projection
 * baseline snapshot and runs the adjustment layer against it so the
 * Optimizer's projection source selector picks it up immediately. */
export async function POST(request: Request) {
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
  const result = await saveProjectionCsvImport(bytes, provider, date, file.name, mapping);
  const status = result.status === "ready" ? 200 : result.status === "no_players" ? 422 : 502;
  return NextResponse.json(result, { status });
}
