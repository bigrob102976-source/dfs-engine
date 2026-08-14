import type { ButtonHTMLAttributes } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement>;

const BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-control)] px-3.5 py-2 text-xs font-semibold " +
  "transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50";

/** The one blue call-to-action button -- reserve for the single primary
 * action in a given context (Build Lineups, Sign in, Refresh). */
export function PrimaryButton({ className = "", ...props }: ButtonProps) {
  return <button className={`${BASE} bg-accent text-white hover:bg-accent-hover ${className}`} {...props} />;
}

/** Neutral action button -- everything that isn't the primary CTA or a
 * destructive action. */
export function SecondaryButton({ className = "", ...props }: ButtonProps) {
  return (
    <button
      className={`${BASE} border border-border bg-bg-panel-raised text-text-muted hover:border-accent hover:text-text ${className}`}
      {...props}
    />
  );
}

/** Destructive action button (Exclude, Delete, Discard). */
export function DangerButton({ className = "", ...props }: ButtonProps) {
  return <button className={`${BASE} bg-red text-white hover:bg-red/85 ${className}`} {...props} />;
}
