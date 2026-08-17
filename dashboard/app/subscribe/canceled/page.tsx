import { requireAuth } from "@/lib/auth/guards";

export const dynamic = "force-dynamic";

const CTA_LINK_CLASS =
  "inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-control)] px-4 py-2 text-sm font-semibold text-white transition-colors duration-150 bg-accent hover:bg-accent-hover";

export default async function SubscribeCanceledPage() {
  await requireAuth("/subscribe/canceled");

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-bg px-6 text-center">
      <h1 className="text-xl font-semibold text-text">Checkout Canceled</h1>
      <p className="max-w-sm text-sm text-text-muted">Checkout was canceled. No subscription changes were made.</p>
      <a href="/pricing" className={CTA_LINK_CLASS}>
        Return to Pricing
      </a>
    </div>
  );
}
