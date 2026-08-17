"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { PrimaryButton } from "@/components/ui/Button";

import { AUTH_INPUT_CLASS, AUTH_LABEL_CLASS } from "./AuthCard";

export function LoginForm({ next }: { next: string }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Something went wrong. Please try again.");
        setSubmitting(false);
        return;
      }
      router.push(next);
      router.refresh();
    } catch {
      setError("Something went wrong. Please try again.");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <label className={AUTH_LABEL_CLASS} htmlFor="email">
        Email
      </label>
      <input
        id="email"
        type="email"
        required
        autoFocus
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className={AUTH_INPUT_CLASS}
      />
      <label className={AUTH_LABEL_CLASS} htmlFor="password">
        Password
      </label>
      <input
        id="password"
        type="password"
        required
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="mb-2 w-full rounded border border-border bg-bg-panel-raised px-3 py-2 text-sm text-text outline-none focus:border-accent"
      />
      <div className="mb-4 text-right">
        <Link href="/forgot-password" className="text-[11px] text-accent hover:text-accent-hover">
          Forgot password?
        </Link>
      </div>
      {error && <p className="mb-4 text-xs text-red">{error}</p>}
      <PrimaryButton type="submit" disabled={submitting} className="w-full py-2 text-sm">
        {submitting ? "Signing in..." : "Sign in"}
      </PrimaryButton>
      <p className="mt-4 text-center text-xs text-text-faint">
        Don&apos;t have an account?{" "}
        <Link href="/signup" className="text-accent hover:text-accent-hover">
          Sign up
        </Link>
      </p>
    </form>
  );
}
