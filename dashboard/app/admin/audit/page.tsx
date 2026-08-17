import { AuditFilterBar } from "@/components/admin/AuditFilterBar";
import { PageHeader } from "@/components/ui/Header";
import { listAuditLog } from "@/lib/db/auditLog";

export const dynamic = "force-dynamic";

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" });
}

function fmtDetails(metadataJson: string | null): string {
  if (!metadataJson) return "--";
  try {
    return JSON.stringify(JSON.parse(metadataJson));
  } catch {
    return metadataJson;
  }
}

function firstParam(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}

/** Append-only by construction: lib/db/auditLog.ts exports no
 * update/delete, and every row here only ever comes from a completed,
 * successful admin mutation -- attempts that failed authorization or
 * validation return an error response before recordAuditLog() is ever
 * called, so "Result" is always Success. */
export default async function AdminAuditPage(props: PageProps<"/admin/audit">) {
  const params = await props.searchParams;
  const entries = listAuditLog({ search: firstParam(params.search), limit: 200 });

  return (
    <div>
      <PageHeader title="Audit Log" description={`${entries.length} recent admin action${entries.length === 1 ? "" : "s"}.`} />
      <AuditFilterBar />

      <div className="overflow-x-auto rounded-[var(--radius-card)] border border-border bg-bg-panel">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-border text-[10px] uppercase tracking-wide text-text-faint">
              <th className="px-3 py-2 font-medium">Timestamp</th>
              <th className="px-3 py-2 font-medium">Admin</th>
              <th className="px-3 py-2 font-medium">Action</th>
              <th className="px-3 py-2 font-medium">Target</th>
              <th className="px-3 py-2 font-medium">Result</th>
              <th className="px-3 py-2 font-medium">Details</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id} className="border-b border-border-subtle last:border-0 hover:bg-bg-panel-raised">
                <td className="px-3 py-2 text-text-muted">{fmtDateTime(entry.created_at)}</td>
                <td className="px-3 py-2 text-text">{entry.actor_label}</td>
                <td className="px-3 py-2 text-text">{entry.action}</td>
                <td className="px-3 py-2 text-text-muted">{entry.target_type ? `${entry.target_type}:${entry.target_id}` : "--"}</td>
                <td className="px-3 py-2 text-green">Success</td>
                <td className="max-w-xs truncate px-3 py-2 text-text-faint" title={fmtDetails(entry.metadata_json)}>
                  {fmtDetails(entry.metadata_json)}
                </td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-text-faint">
                  No audit entries match this search.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
