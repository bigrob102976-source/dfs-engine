// One-off, idempotent audit record for the 2026-09-08 serving-backend
// entitlement-gate bypass (lib/servingBackend/config.ts::
// userCanUseCanonicalServing).
//
// WHY THIS SCRIPT EXISTS: the 2026-09-03 flip of
// mlb.canonical_postgres_serving to PRODUCTION was made with no audit
// trail. Because resolveServingBackend() also required an explicit
// request param that no customer-facing page ever sent, that flip
// silently did nothing for real traffic, and every member kept being
// served by the abandoned LegacyR2ServingBackend for five days. Nobody
// could see the change had happened, which is most of why it took days
// to find. This records the follow-up change so the next person reading
// admin_audit_log sees WHAT changed, WHEN, and WHAT MUST BE UNDONE.
//
// Safe to run more than once: hasAuditAction() makes it a no-op if the
// row already exists (the same "fires exactly once, ever" guard the
// admin-bootstrap path uses). actorUserId is null because this is a
// deploy-time configuration change, not a human clicking an admin UI --
// exactly the system-initiated case recordAuditLog documents.
//
// Run against production once, after deploying:
//   npx tsx scripts/record-serving-gate-audit.ts

import { hasAuditAction, recordAuditLog } from "../lib/db/auditLog.ts";

const ACTION = "serving_backend.entitlement_gate_bypassed";

async function main(): Promise<void> {
  if (await hasAuditAction(ACTION)) {
    console.log(JSON.stringify({ status: "already_recorded", action: ACTION }));
    return;
  }

  const entry = await recordAuditLog({
    actorUserId: null,
    actorLabel: "system (deploy 2026-09-08)",
    action: ACTION,
    targetType: "feature_flag",
    targetId: "mlb.canonical_postgres_serving",
    metadata: {
      change:
        "userCanUseCanonicalServing() no longer requires a per-user entitlement on BETA/PRODUCTION; " +
        "any authenticated user is served CANONICAL_POSTGRES.",
      reason:
        "Free beta by design -- the subscriptions table is intentionally empty and billing comes later. " +
        "Requiring an entitlement pinned all members to LegacyR2ServingBackend, broken/empty since 2026-09-03.",
      must_be_restored_when: "paid subscriptions launch",
      restore_by:
        "Reverting userCanUseCanonicalServing() to isFeatureVisibleToUser(user, CANONICAL_SERVING_FLAG_KEY), " +
        "or an equivalent that consults entitlements.",
      unaffected_gates: ["mlb.big_money_ml_optimizer", "mlb.bluecollar_optimizer"],
      kill_switch: "Unchanged: set the flag DISABLED to revert every user to legacy with no code change.",
      related_undocumented_change: "2026-09-03 flip of this flag to PRODUCTION, which had no audit row.",
    },
  });

  console.log(JSON.stringify({ status: "recorded", id: entry.id, action: ACTION, created_at: entry.created_at }));
}

main().catch((error) => {
  console.error(`[record-serving-gate-audit] failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
