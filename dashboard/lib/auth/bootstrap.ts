import { hasAuditAction, recordAuditLog } from "@/lib/db/auditLog";
import { updateUserRole } from "@/lib/db/users";

const BOOTSTRAP_ACTION = "admin_bootstrap";
const DEFAULT_BOOTSTRAP_EMAIL = "bigrob102976@gmail.com";

function getBootstrapEmail(): string {
  return (process.env.ADMIN_BOOTSTRAP_EMAIL || DEFAULT_BOOTSTRAP_EMAIL).toLowerCase();
}

/** Called once, immediately after a successful PASSWORD verification
 * during login (never at signup -- signup alone doesn't prove control
 * of the account). Promotes the configured bootstrap email to ADMIN
 * exactly once, system-wide, ever -- guarded by checking for a prior
 * `admin_bootstrap` audit row rather than any per-user flag, so it
 * can't accidentally re-fire even if this exact user is later demoted
 * back to MEMBER by another admin. Never trusts the browser: this only
 * ever runs server-side, driven entirely by the DB's own state. Returns
 * true if a promotion just happened (the caller should re-read the
 * user's role before finishing the login response/session). */
export async function maybeBootstrapAdmin(user: { id: string; email: string; role: string }): Promise<boolean> {
  if (user.email.toLowerCase() !== getBootstrapEmail()) return false;
  if (user.role !== "MEMBER") return false;
  if (await hasAuditAction(BOOTSTRAP_ACTION)) return false;

  await updateUserRole(user.id, "ADMIN");
  await recordAuditLog({
    actorUserId: null,
    actorLabel: "system",
    action: BOOTSTRAP_ACTION,
    targetType: "user",
    targetId: user.id,
    metadata: { email: user.email },
  });
  return true;
}
