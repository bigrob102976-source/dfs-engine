"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

// Milestone 30.1: a single URL-param-driven dropdown for the pitcher/
// hitter pages' eligibility filter (lib/eligibilityFilter.ts) -- mirrors
// components/admin/UsersFilterBar.tsx's "filters live in the URL, page.tsx
// stays the single source of truth" pattern, just for one param instead
// of several.
export function EligibilityFilterSelect({
  paramName,
  value,
  options,
}: {
  paramName: string;
  value: string;
  options: Array<{ value: string; label: string }>;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function onChange(next: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set(paramName, next);
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2.5 py-1.5 text-xs text-text outline-none focus:border-accent"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
