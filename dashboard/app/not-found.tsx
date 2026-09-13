import Link from "next/link";

import { Footer } from "@/components/Footer";

// Launch Blocker Sprint 1 (2026-09-13): before this file, a missing
// route fell through to Next.js's generic, unbranded 404 page. This is
// intentionally minimal (no auth check, no data fetch, no sport-
// specific branching) since Next.js renders not-found.tsx for ANY
// unmatched route across the whole app, authenticated or not.
export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-faint">
          BIG MONEY <span className="text-gold">DFS</span>
        </p>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-text">Page not found</h1>
        <p className="mt-2 max-w-sm text-sm text-text-muted">
          The page you&apos;re looking for doesn&apos;t exist or may have moved.
        </p>
        <div className="mt-6 flex gap-3">
          <Link
            href="/nfl"
            className="rounded-[var(--radius-control)] bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-hover"
          >
            NFL Dashboard
          </Link>
          <Link
            href="/dashboard"
            className="rounded-[var(--radius-control)] border border-border px-4 py-2 text-sm font-semibold text-text hover:bg-bg-panel-raised"
          >
            MLB Dashboard
          </Link>
        </div>
      </div>
      <Footer />
    </div>
  );
}
