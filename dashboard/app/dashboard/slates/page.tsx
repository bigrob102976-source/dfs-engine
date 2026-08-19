import { PageHeader } from "@/components/ui/Header";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { getPublishedVersion } from "@/lib/db/slateStatus";
import { resolveSlateContext } from "@/lib/slateContext";

export const dynamic = "force-dynamic";

interface DataStatusRow {
  label: string;
  ready: boolean;
}

interface MemberSlateRow {
  slateId: string;
  slateName: string | null;
  lastUpdated: string | null;
  statuses: DataStatusRow[];
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** Milestone 29: member-facing Slate Manager -- read-only. No CSV
 * upload, no file picker, no admin actions; everything an admin can DO
 * with a slate now lives exclusively on /admin/slates (Slate
 * Operations). resolveSlateContext() already filters `slates` to
 * PUBLISHED-only for a non-admin viewer (lib/memberSlateVisibility.ts),
 * so this page can never show a draft/processing/unpublished slate --
 * for each one it displays exactly what the spec asks for: Sport /
 * Slate / Last Updated / Data Status, sourced from the PUBLISHED
 * version's own pinned snapshot paths (lib/db/slateStatus.ts::
 * getPublishedVersion) so "Last Updated" and "READY" here always match
 * what a member is actually seeing elsewhere in the dashboard, not
 * whatever an admin's in-progress refresh happens to be building. */
export default async function SlateManagerPage() {
  const date = getTodayChicagoDate();
  const ctx = await resolveSlateContext(date);

  const rows: MemberSlateRow[] = ctx.slates.map((s) => {
    const version = getPublishedVersion(date, s.slateId);
    return {
      slateId: s.slateId,
      slateName: s.slateName,
      lastUpdated: version?.publishedAt ?? null,
      statuses: [
        { label: "Lineups", ready: Boolean(version?.poolPath) },
        { label: "Vegas", ready: Boolean(version?.vegasSnapshotPath) },
        { label: "Native", ready: Boolean(version?.nativeSnapshotPath) },
        { label: "AI", ready: Boolean(version?.aiSnapshotPath) },
        { label: "Ownership", ready: Boolean(version?.ownershipPath) },
      ],
    };
  });

  return (
    <div>
      <PageHeader title="Slate Manager" description={`Published DraftKings slates for ${date}.`} />

      {rows.length === 0 ? (
        <p className="p-4 text-xs text-text-faint">
          No slates have been published yet for {date} -- check back soon, or contact an admin.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((r) => (
            <div key={r.slateId} className="rounded-[var(--radius-card)] border border-border bg-bg-panel p-4 shadow-[var(--shadow-card)]">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-text-faint">MLB</div>
              <div className="mb-3 text-sm font-semibold text-text">{r.slateName ?? r.slateId}</div>

              <div className="mb-3 text-[11px]">
                <span className="text-text-faint">Last Updated</span>{" "}
                <span className="text-text">{fmtDateTime(r.lastUpdated)}</span>
              </div>

              <dl className="grid grid-cols-2 gap-y-1 text-[11px]">
                {r.statuses.map((st) => (
                  <div key={st.label} className="col-span-2 flex items-center justify-between">
                    <dt className="text-text-faint">{st.label}</dt>
                    <dd className={`font-semibold uppercase tracking-wide ${st.ready ? "text-green" : "text-text-faint"}`}>
                      {st.ready ? "READY" : "--"}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
