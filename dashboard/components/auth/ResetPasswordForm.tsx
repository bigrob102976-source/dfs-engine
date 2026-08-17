"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";

import { PrimaryButton } from "@/components/ui/Button";

import { AUTH_INPUT_CLASS, AUTH_LABEL_CLASS } from "./AuthCard";

export function ResetPasswordForm({ token }: { token: string | null }) {
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) {
      setError("This reset link is missing its token.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token, newPassword }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.error ?? "Something went wrong. Please try again.");
        setSubmitting(false);
        return;
      }
      setDone(true);
    } catch {
      setError("Something went wrong. Please try again.");
      setSubmitting(false);
    }
  }

  if (!token) {
    return <p className="text-sm text-red">This reset link is missing its token. Request a new one from the Forgot Password page.</p>;
  }

  if (done) {
    return (
      <div>
        <p className="mb-4 text-sm text-text">Your password has been reset. You&apos;ve been signed out everywhere for security -- sign in with your new password.</p>
        <Link href="/login" className="text-xs text-accent hover:text-accent-hover">
          Continue to sign in →
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <label className={AUTH_LABEL_CLASS} htmlFor="newPassword">
        New password
      </label>
      <input
        id="newPassword"
        type="password"
        required
        minLength={8}
        autoFocus
        autoComplete="new-password"
        value={newPassword}
        onChange={(e) => setNewPassword(e.target.value)}
        className={AUTH_INPUT_CLASS}
      />
      {error && <p className="mb-4 text-xs text-red">{error}</p>}
      <PrimaryButton type="submit" disabled={submitting} className="w-full py-2 text-sm">
        {submitting ? "Resetting..." : "Reset password"}
      </PrimaryButton>
    </form>
  );
}
