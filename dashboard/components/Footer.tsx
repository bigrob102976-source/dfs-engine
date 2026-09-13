import Link from "next/link";

/** Legal/trust links, added Launch Blocker Sprint 1 (2026-09-13). Rendered
 * inside every shell that reaches an anonymous visitor -- Sidebar.tsx
 * (both /dashboard/* and /nfl/*, which is intentionally public), AuthCard
 * (/login, /signup, /forgot-password, /reset-password, /verify-email),
 * and the public /pricing page -- so Terms/Privacy/Responsible Play/
 * Support are reachable from wherever a visitor actually lands, not
 * bolted onto a page nobody without an account ever sees. */
const LEGAL_LINKS = [
  { href: "/terms", label: "Terms" },
  { href: "/privacy", label: "Privacy" },
  { href: "/responsible-play", label: "Responsible Play" },
  { href: "/support", label: "Support" },
] as const;

export function Footer({ compact = false }: { compact?: boolean }) {
  const year = new Date().getFullYear();
  return (
    <footer className={`shrink-0 border-t border-border-subtle ${compact ? "px-2 py-2" : "px-4 py-3"}`}>
      <div className={`flex ${compact ? "flex-col items-center gap-1" : "flex-wrap items-center justify-between gap-2"}`}>
        <nav aria-label="Legal" className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {LEGAL_LINKS.map((link) => (
            <Link key={link.href} href={link.href} className="text-[11px] text-text-faint hover:text-text hover:underline">
              {link.label}
            </Link>
          ))}
        </nav>
        <p className="text-[11px] text-text-faint">© {year} Big Money DFS</p>
      </div>
    </footer>
  );
}
