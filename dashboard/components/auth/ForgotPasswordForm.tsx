"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";

import { PrimaryButton } from "@/components/ui/Button";

import { AUTH_INPUT_CLASS, AUTH_LABEL_CLASS } from "./AuthCard";
import { DevLinkNotice } from "./DevLinkNotice";

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [devResetLink, setDevResetLink] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const body = await res.json();
      setMessage(body.message ?? "If an account exists for that email, a reset link has been sent.");
      setDevResetLink(body.devResetLink ?? null);
    } catch {
      setMessage("Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (message) {
    return (
      <div>
        <p className="mb-4 text-sm text-text">{message}</p>
        {devResetLink && <DevLinkNotice label="Reset your password:" link={devResetLink} />}
        <Link href="/login" className="text-xs text-accent hover:text-accent-hover">
          ← Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <p className="mb-4 text-xs text-text-faint">Enter your account email and we&apos;ll send a password reset link.</p>
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
      <PrimaryButton type="submit" disabled={submitting} className="w-full py-2 text-sm">
        {submitting ? "Sending..." : "Send reset link"}
      </PrimaryButton>
      <p className="mt-4 text-center text-xs text-text-faint">
        <Link href="/login" className="text-accent hover:text-accent-hover">
          ← Back to sign in
        </Link>
      </p>
    </form>
  );
}
