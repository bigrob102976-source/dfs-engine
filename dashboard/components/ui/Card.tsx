import type { ReactNode } from "react";

/** Base surface every card-like component in the app builds on: 16px
 * radius, soft shadow, thin low-contrast border -- no harsh outlines. */
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-[var(--radius-card)] border border-border bg-bg-panel shadow-[var(--shadow-card)] ${className}`}>
      {children}
    </div>
  );
}

/** A single headline metric (Games, Players, Slate Status, ...) --
 * the dashboard's top-row building block. */
export function MetricCard({
  label,
  value,
  trend,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  trend?: ReactNode;
  tone?: "neutral" | "positive" | "negative";
}) {
  const toneClass = tone === "positive" ? "text-green" : tone === "negative" ? "text-red" : "text-text";
  return (
    <Card className="p-4">
      <div className="text-[11px] uppercase tracking-wide text-text-faint">{label}</div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className={`text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</span>
        {trend}
      </div>
    </Card>
  );
}

/** A titled content region (used for Top Pitchers / Top Hitters / Top
 * Stacks / Alerts / Weather / Vegas dashboard tiles, and anywhere else
 * a labeled block of data needs a consistent frame). */
export function DataCard({
  title,
  action,
  children,
  className = "",
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={`p-4 ${className}`}>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted">{title}</h3>
        {action}
      </div>
      {children}
    </Card>
  );
}
