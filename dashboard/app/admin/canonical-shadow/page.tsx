import { PageHeader } from "@/components/ui/Header";
import { Card } from "@/components/ui/Card";
import { listIdentityReviewQueue, listShadowSlateStatuses } from "@/lib/db/canonicalShadowStatus";

export const dynamic = "force-dynamic";

function fmtAge(seconds: number | null): string {
  if (seconds === null) return "--";
  if (seconds < 90) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes}m`;
  return `${Math.round(minutes / 60)}h`;
}

function shortHash(hash: string | null): string {
  return hash ? hash.slice(0, 10) : "--";
}

/** M3J -- ADMIN-ONLY (gated by app/admin/layout.tsx's requireAdmin(),
 * same as every other /admin/* page), READ-ONLY observability over the
 * canonical shadow ingestion pipeline (M2/M3). This is NOT customer
 * functionality and exposes no controls -- no identity merge/edit/
 * approve action exists here (M3J's explicit scope boundary); it only
 * ever reads from lib/db/canonicalShadowStatus.ts, which itself never
 * touches a database URL, Railway variable, API key, or storage
 * credential. */
export default async function AdminCanonicalShadowPage() {
  const [slates, reviewQueue] = await Promise.all([
    listShadowSlateStatuses(),
    listIdentityReviewQueue("PENDING"),
  ]);

  return (
    <div>
      <PageHeader
        title="Canonical Shadow Ingestion"
        description="Read-only observability over the M2/M3 shadow pipeline (RAW/NORMALIZED R2 -> Postgres shadow CURRENT). Never affects the customer-facing legacy R2 serving path."
      />

      <Card className="overflow-x-auto p-4">
        <table className="w-full min-w-[1100px] text-left text-xs">
          <thead>
            <tr className="border-b border-border text-text-faint">
              <th className="p-2">Slate Date</th>
              <th className="p-2">Sport</th>
              <th className="p-2">Provider</th>
              <th className="p-2">DraftGroup</th>
              <th className="p-2">Slate Name</th>
              <th className="p-2">internalSlateId</th>
              <th className="p-2">Validation</th>
              <th className="p-2">Last Promoted</th>
              <th className="p-2">Age</th>
              <th className="p-2">Players</th>
              <th className="p-2">Resolved</th>
              <th className="p-2">Unresolved</th>
              <th className="p-2">Review</th>
              <th className="p-2">normalizedHash</th>
              <th className="p-2">Semantic Dup</th>
              <th className="p-2">Consecutive Failures</th>
              <th className="p-2">Last Error</th>
              <th className="p-2">RAW Path</th>
              <th className="p-2">NORMALIZED Path</th>
            </tr>
          </thead>
          <tbody>
            {slates.map((s) => (
              <tr key={s.internal_slate_id} className="border-b border-border/50 align-top">
                <td className="p-2 tabular-nums">{s.slate_date}</td>
                <td className="p-2">{s.sport}</td>
                <td className="p-2">{s.provider}</td>
                <td className="p-2">{s.provider_slate_id}</td>
                <td className="p-2">{s.slate_name ?? "--"}</td>
                <td className="p-2 font-mono text-[10px]">{s.internal_slate_id}</td>
                <td className="p-2">{s.validation_state}</td>
                <td className="p-2">{s.promoted_at ?? "--"}</td>
                <td className="p-2 tabular-nums">{fmtAge(s.ageSeconds)}</td>
                <td className="p-2 tabular-nums">{s.player_count ?? "--"}</td>
                <td className="p-2 tabular-nums">{s.resolved_identity_count ?? "--"}</td>
                <td className="p-2 tabular-nums">{s.unresolved_identity_count ?? "--"}</td>
                <td className="p-2 tabular-nums">{s.review_required_count ?? "--"}</td>
                <td className="p-2 font-mono text-[10px]">{shortHash(s.normalized_hash)}</td>
                <td className="p-2">{s.is_semantic_duplicate === 1 ? "yes" : s.is_semantic_duplicate === 0 ? "no" : "--"}</td>
                <td className={`p-2 tabular-nums ${s.consecutive_failures > 0 ? "text-red" : ""}`}>{s.consecutive_failures}</td>
                <td className="p-2 max-w-[220px] truncate" title={s.last_error_summary ?? undefined}>
                  {s.last_error_type ? `${s.last_error_type}: ${s.last_error_summary ?? ""}` : "--"}
                </td>
                <td className="p-2 max-w-[200px] truncate" title={s.current_raw_artifact_path ?? undefined}>{s.current_raw_artifact_path ?? "--"}</td>
                <td className="p-2 max-w-[200px] truncate" title={s.current_normalized_artifact_path ?? undefined}>{s.current_normalized_artifact_path ?? "--"}</td>
              </tr>
            ))}
            {slates.length === 0 && (
              <tr>
                <td colSpan={19} className="p-4 text-center text-text-faint">
                  No canonical shadow ingestion attempts recorded yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <div className="mt-6">
        <PageHeader title="Identity Review Queue (read-only)" description="Pending ambiguous identity matches -- no merge/edit/approve controls yet." />
        <Card className="overflow-x-auto p-4">
          <table className="w-full min-w-[900px] text-left text-xs">
            <thead>
              <tr className="border-b border-border text-text-faint">
                <th className="p-2">Sport</th>
                <th className="p-2">Provider</th>
                <th className="p-2">External ID</th>
                <th className="p-2">Player Name</th>
                <th className="p-2">Team</th>
                <th className="p-2">Reason</th>
                <th className="p-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {reviewQueue.map((q) => (
                <tr key={q.id} className="border-b border-border/50">
                  <td className="p-2">{q.sport}</td>
                  <td className="p-2">{q.provider}</td>
                  <td className="p-2">{q.external_id}</td>
                  <td className="p-2">{q.provider_player_name}</td>
                  <td className="p-2">{q.provider_team ?? "--"}</td>
                  <td className="p-2 max-w-[360px] truncate" title={q.reason}>{q.reason}</td>
                  <td className="p-2">{q.created_at}</td>
                </tr>
              ))}
              {reviewQueue.length === 0 && (
                <tr>
                  <td colSpan={7} className="p-4 text-center text-text-faint">
                    No pending identity review entries.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}
