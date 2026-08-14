"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/theme/ThemeToggle";

const POLL_INTERVAL_MS = 1500;

function RefreshButton() {
  const router = useRouter();
  const [running, setRunning] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  function poll() {
    fetch("/api/refresh")
      .then((res) => res.json())
      .then((data) => {
        const status = data?.run?.status;
        if (status === "running" || status === "needs_selection") return;
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
        setRunning(false);
        router.refresh();
      })
      .catch(() => {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
        setRunning(false);
      });
  }

  function handleClick() {
    setRunning(true);
    fetch("/api/refresh", { method: "POST" })
      .then(() => {
        if (!pollRef.current) pollRef.current = setInterval(poll, POLL_INTERVAL_MS);
      })
      .catch(() => setRunning(false));
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={running}
      aria-label="Refresh today's slate"
      title="Refresh today's slate"
      className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-control)] text-text-muted transition-colors duration-150 hover:bg-bg-panel-raised hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
    >
      <span className={running ? "animate-spin" : ""} aria-hidden="true">
        ⟳
      </span>
    </button>
  );
}

function NotificationsMenu() {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="Notifications"
        aria-expanded={open}
        className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-control)] text-text-muted transition-colors duration-150 hover:bg-bg-panel-raised hover:text-text"
      >
        🔔
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1 w-56 rounded-[var(--radius-control)] border border-border bg-bg-panel-raised p-3 text-xs text-text-faint shadow-[var(--shadow-popover)]"
        >
          No new notifications.
        </div>
      )}
    </div>
  );
}

function ProfileMenu() {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="Profile"
        aria-expanded={open}
        className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-dim text-xs font-semibold text-accent transition-colors duration-150 hover:brightness-110"
      >
        BM
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1 w-40 overflow-hidden rounded-[var(--radius-control)] border border-border bg-bg-panel-raised text-xs shadow-[var(--shadow-popover)]"
        >
          <form action="/api/session/sign-out" method="post">
            <button type="submit" role="menuitem" className="w-full px-3 py-2 text-left text-text-muted hover:bg-bg-panel hover:text-text">
              Sign out
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

/** Sticky top bar: current slate indicator, optional page-specific
 * controls (e.g. the Optimizer's Projection Source selector, passed via
 * `rightSlot`), global search, refresh, theme toggle, notifications, and
 * profile. Every dashboard route renders this once via
 * app/dashboard/layout.tsx. */
export function TopNavigation({ slateLabel, search, rightSlot }: { slateLabel: string; search?: ReactNode; rightSlot?: ReactNode }) {
  return (
    <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-bg-panel/95 px-4 py-2.5 backdrop-blur">
      <div className="flex items-center gap-1.5 rounded-[var(--radius-control)] border border-border bg-bg-panel-raised px-2.5 py-1.5 text-xs text-text-muted">
        <span aria-hidden="true">📅</span>
        <span>{slateLabel}</span>
      </div>

      {rightSlot}

      <div className="ml-auto flex items-center gap-2">
        {search}
        <RefreshButton />
        <ThemeToggle />
        <NotificationsMenu />
        <ProfileMenu />
      </div>
    </header>
  );
}
