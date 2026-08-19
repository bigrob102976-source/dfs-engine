import { SecondaryButton } from "@/components/ui/Button";
import { requireAuth } from "@/lib/auth/guards";

export const dynamic = "force-dynamic";

/** Milestone 30: shown instead of the member dashboard when
 * PRIVATE_BETA=true and this user has no beta grant yet
 * (app/dashboard/layout.tsx redirects here via hasProductAccess()).
 * Still requires a real session (requireAuth()) -- this is not a public
 * marketing page, just the logged-in "not yet" state. */
export default async function BetaAccessRequiredPage() {
  const user = await requireAuth();

  return (
    <div className="flex min-h-screen w-full flex-col items-center justify-center gap-4 bg-bg px-4 text-center">
      <h1 className="text-lg font-semibold text-text">Big Money DFS is in private beta</h1>
      <p className="max-w-md text-sm text-text-muted">
        Your account ({user.email}) does not have beta access yet. If you were invited, ask the person who invited you to
        approve your account, or check back soon.
      </p>
      <form action="/api/auth/logout" method="post">
        <SecondaryButton type="submit">Sign out</SecondaryButton>
      </form>
    </div>
  );
}
