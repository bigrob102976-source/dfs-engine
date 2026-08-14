import type { InputHTMLAttributes } from "react";

/** Consistent search/filter input used across tables and the global
 * search box. Just styling -- callers own value/onChange/debouncing. */
export function SearchInput({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type="search"
      className={`rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-3 py-1.5 text-xs text-text outline-none placeholder:text-text-faint focus:border-accent ${className}`}
      {...props}
    />
  );
}
